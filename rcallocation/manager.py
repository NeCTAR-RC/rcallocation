#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Business logic for allocation requests.

Views validate input and enforce policy, then call the manager, which
applies the state machine, keeps the history chain, maintains quotas and
sends notifications. Every public method runs in one database
transaction and commits before returning; notifications go out after the
commit so a mail problem can never undo a state change.
"""

from oslo_log import log as logging
import sqlalchemy as sa

from rcallocation import checkers
from rcallocation import choices
from rcallocation.common import exceptions
from rcallocation.extensions import db
from rcallocation import models
from rcallocation import notification
from rcallocation import urgency
from rcallocation import utils


LOG = logging.getLogger(__name__)

# Fields that only an admin may set directly; others setting them get 403
# (matching the old API's allocation_home handling).
GATED_FIELDS = ("national", "associated_site", "special_approval")

# Request body keys that are not columns on the allocation.
RELATION_FIELDS = (
    "bundle",
    "associated_site",
    "usage_types",
    "ardc_support",
    "ncris_facilities",
    "supported_organisations",
)
NESTED_FIELDS = ("quotas", "investigators", "grants", "publications")
CONTROL_FIELDS = ("ignore_warnings", "allocation_home")

#: Admin metadata whose edits do not count as a modification.
METADATA_FIELDS = {"notes"}


def _copy_attrs(source, target, exclude=()):
    for column in source.__table__.columns:
        name = column.name
        if name in exclude:
            continue
        setattr(target, name, getattr(source, name))


class Manager:
    def __init__(self, context=None):
        self.context = context

    @property
    def user_id(self):
        return getattr(self.context, "user_id", None)

    @property
    def user_name(self):
        return getattr(self.context, "user_name", None)

    # ------------------------------------------------------------------
    # history
    # ------------------------------------------------------------------

    def copy_allocation(self, allocation):
        """Create a history copy of ``allocation`` and its components.

        The copy keeps every column value (including the timestamps) and
        points at the live record through ``parent_request``. Quota
        groups, quotas, investigators, publications and grants are
        cloned; usage types, support programs, facilities and
        organisations are shared references. The copy is flushed but not
        committed.
        """
        db.session.flush()
        copy = models.AllocationRequest()
        _copy_attrs(allocation, copy, exclude=("id", "parent_request_id"))
        copy.parent_request_id = allocation.id
        db.session.add(copy)
        db.session.flush()

        for group in allocation.quota_groups:
            new_group = models.QuotaGroup(
                allocation_id=copy.id,
                zone_id=group.zone_id,
                service_type_id=group.service_type_id,
            )
            db.session.add(new_group)
            db.session.flush()
            for quota in group.quotas:
                db.session.add(
                    models.Quota(
                        group_id=new_group.id,
                        resource_id=quota.resource_id,
                        requested_quota=quota.requested_quota,
                        quota=quota.quota,
                    )
                )
        for inv in allocation.investigators:
            new_inv = models.ChiefInvestigator()
            _copy_attrs(inv, new_inv, exclude=("id", "allocation_id"))
            new_inv.allocation_id = copy.id
            db.session.add(new_inv)
        for pub in allocation.publications:
            new_pub = models.Publication()
            _copy_attrs(pub, new_pub, exclude=("id", "allocation_id"))
            new_pub.allocation_id = copy.id
            db.session.add(new_pub)
        for grant in allocation.grants:
            new_grant = models.Grant()
            _copy_attrs(grant, new_grant, exclude=("id", "allocation_id"))
            new_grant.allocation_id = copy.id
            db.session.add(new_grant)
        copy.usage_types = list(allocation.usage_types)
        copy.ncris_facilities = list(allocation.ncris_facilities)
        copy.ardc_support = list(allocation.ardc_support)
        copy.supported_organisations = list(allocation.supported_organisations)
        db.session.flush()
        db.session.expire(allocation)
        return copy

    # ------------------------------------------------------------------
    # field application
    # ------------------------------------------------------------------

    def _split(self, data):
        """Split a validated body into scalar, nested and control parts."""
        data = dict(data)
        nested = {k: data.pop(k) for k in NESTED_FIELDS if k in data}
        control = {k: data.pop(k) for k in CONTROL_FIELDS if k in data}
        return data, nested, control

    def _apply_allocation_home(self, data, compat, is_admin):
        if not is_admin:
            if compat or any(data.get(f) for f in GATED_FIELDS):
                raise exceptions.PermissionDenied()
        if compat:
            if data.get("associated_site") or data.get("national"):
                raise exceptions.ValidationError(
                    [
                        "Cannot use 'allocation_home' with 'national' or "
                        "'associated_site'"
                    ]
                )
            data.update(compat)
        return data

    def _check_project_name(self, allocation, data):
        if "project_name" not in data:
            return
        if not utils.is_project_name_available(
            data["project_name"], allocation
        ):
            raise exceptions.ValidationError(
                {"project_name": ["Project name already exists"]}
            )

    def _apply_fields(self, allocation, data):
        for key, value in data.items():
            setattr(allocation, key, value)

    def _apply_nested(self, allocation, nested, approving=False):
        if "investigators" in nested:
            self._replace_related(
                allocation,
                "investigators",
                models.ChiefInvestigator,
                nested["investigators"],
            )
        if "grants" in nested:
            self._replace_related(
                allocation, "grants", models.Grant, nested["grants"]
            )
        if "publications" in nested:
            self._replace_related(
                allocation,
                "publications",
                models.Publication,
                nested["publications"],
            )
        if "quotas" in nested:
            values = {}
            for item in nested["quotas"]:
                if approving:
                    value = item.get("quota", item.get("requested_quota"))
                else:
                    value = item.get("requested_quota", item.get("quota"))
                values[(item["resource"], item["zone"])] = value
            self.set_quotas(
                allocation, values, approving=approving, replace=True
            )

    def _replace_related(self, allocation, attr, model, items):
        """Full replacement of a related collection keyed by ``id``."""
        existing = {obj.id: obj for obj in getattr(allocation, attr)}
        keep = []
        for item in items:
            item = dict(item)
            ident = item.pop("id", None)
            obj = existing.get(ident) if ident else None
            if obj is None:
                obj = model(allocation_id=allocation.id)
                db.session.add(obj)
            for key, value in item.items():
                setattr(obj, key, value)
            keep.append(obj)
        setattr(allocation, attr, keep)
        db.session.flush()

    # ------------------------------------------------------------------
    # quotas
    # ------------------------------------------------------------------

    def set_quotas(self, allocation, values, approving=False, replace=False):
        """Apply quota values keyed by ``(resource, zone)``.

        ``resource`` is a codename or Resource; ``zone`` a zone name or
        Zone. A zero or empty value removes the quota row. On a bundle
        allocation only location specific service types keep overrides,
        exactly as the dashboard's quota form did. With ``replace`` the
        rows not mentioned are removed as well.
        """
        mentioned = set()
        for (resource_ref, zone_ref), value in values.items():
            resource = self._resource(resource_ref)
            zone = self._zone(zone_ref)
            if resource is None:
                raise exceptions.ValidationError(
                    {"quotas": [f"Unknown resource '{resource_ref}'"]}
                )
            if zone is None:
                raise exceptions.ValidationError(
                    {"quotas": [f"Unknown zone '{zone_ref}'"]}
                )
            mentioned.add((resource.id, zone.name))
            self._set_quota(allocation, resource, zone, value, approving)
        if replace:
            for quota in list(allocation.all_quotas()):
                key = (quota.resource_id, quota.group.zone_id)
                if key not in mentioned:
                    db.session.delete(quota)
        db.session.flush()
        self._delete_empty_groups(allocation)

    def _set_quota(self, allocation, resource, zone, value, approving):
        service_type = resource.service_type
        if allocation.bundle and not service_type.location_specific:
            # Bundle allocations cannot override single zone resources.
            for quota in list(allocation.all_quotas()):
                if quota.resource_id == resource.id:
                    db.session.delete(quota)
            db.session.flush()
            return
        group = None
        for candidate in allocation.quota_groups:
            if (
                candidate.zone_id == zone.name
                and candidate.service_type_id == service_type.catalog_name
            ):
                group = candidate
                break
        if value:
            # Purposely test for 0 or None which means the same thing
            entry = f"{resource.codename} in zone '{zone.name}'"
            self._check_quota_zone(resource, zone, entry)
            self._check_quota_unlimited(
                allocation,
                quota=value if approving else 0,
                requested_quota=0 if approving else value,
                entry=entry,
            )
            if group is None:
                group = models.QuotaGroup(
                    allocation_id=allocation.id,
                    zone_id=zone.name,
                    service_type_id=service_type.catalog_name,
                )
                db.session.add(group)
                db.session.flush()
                db.session.expire(allocation, ["quota_groups"])
            quota = None
            for candidate in group.quotas:
                if candidate.resource_id == resource.id:
                    quota = candidate
                    break
            if quota is None:
                quota = models.Quota(
                    group_id=group.id,
                    resource_id=resource.id,
                    requested_quota=0,
                    quota=0,
                )
                db.session.add(quota)
            if approving:
                quota.quota = value
            else:
                quota.requested_quota = value
            db.session.flush()
            db.session.expire(group, ["quotas"])
        elif group is not None:
            for quota in list(group.quotas):
                if quota.resource_id == resource.id:
                    db.session.delete(quota)
            db.session.flush()
            db.session.expire(group, ["quotas"])

    def _delete_empty_groups(self, allocation):
        db.session.expire(allocation, ["quota_groups"])
        for group in list(allocation.quota_groups):
            if len(group.quotas) < 1:
                db.session.delete(group)
        db.session.flush()
        db.session.expire(allocation, ["quota_groups"])

    @staticmethod
    def _quota_error(message, entry=None):
        """A quota ValidationError, keyed on ``quotas`` for nested writes.

        ``POST /quotas/`` (no ``entry``) returns a plain message list; a
        nested ``quotas`` entry is named and keyed on the ``quotas`` field.
        """
        if entry is None:
            return exceptions.ValidationError([message])
        return exceptions.ValidationError({"quotas": [f"{entry}: {message}"]})

    def _check_quota_zone(self, resource, zone, entry=None):
        if zone not in resource.service_type.zones:
            raise self._quota_error(
                "Resource not available in this zone", entry
            )

    def _check_quota_unlimited(
        self, allocation, quota=0, requested_quota=0, entry=None
    ):
        if not allocation.managed:
            return
        if quota == -1:
            raise self._quota_error(
                "Unlimited quota not allowed for managed allocation", entry
            )
        if requested_quota == -1:
            raise self._quota_error(
                "Unlimited requested quota not allowed for managed allocation",
                entry,
            )

    def _resource(self, ref):
        if isinstance(ref, models.Resource):
            return ref
        if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
            return db.session.get(models.Resource, int(ref))
        return models.Resource.by_codename(str(ref))

    def _zone(self, ref):
        if isinstance(ref, models.Zone):
            return ref
        return db.session.get(models.Zone, str(ref))

    def create_quota(self, data, is_write_admin):
        """Create a single quota row (``POST /quotas/``)."""
        Allocation = models.AllocationRequest
        query = db.session.query(Allocation).filter(
            Allocation.id == data["allocation"]
        )
        if not is_write_admin:
            query = query.filter(Allocation.contact_email == self.user_name)
        allocation = query.first()
        if allocation is None:
            raise exceptions.ValidationError(["Allocation does not exist"])
        if allocation.status not in choices.PENDING_STATUSES:
            raise exceptions.ValidationError(
                [
                    "Allocation quota in status "
                    f"'{allocation.status_display}' can not be updated"
                ]
            )
        resource = db.session.get(models.Resource, data["resource"])
        if resource is None:
            raise exceptions.ValidationError(
                {
                    "resource": [
                        f'Invalid pk "{data["resource"]}" - object '
                        'does not exist.'
                    ]
                }
            )
        zone = db.session.get(models.Zone, data["zone"])
        if zone is None:
            raise exceptions.ValidationError(["Zone does not exist"])
        self._check_quota_zone(resource, zone)
        group = None
        for candidate in allocation.quota_groups:
            if (
                candidate.zone_id == zone.name
                and candidate.service_type_id == resource.service_type_id
            ):
                group = candidate
        if group is not None and any(
            q.resource_id == resource.id for q in group.quotas
        ):
            raise exceptions.ValidationError(["Duplicate quota resource"])
        self._check_quota_unlimited(
            allocation,
            quota=data.get("quota", 0),
            requested_quota=data.get("requested_quota", 0),
        )
        if group is None:
            group = models.QuotaGroup(
                allocation_id=allocation.id,
                zone_id=zone.name,
                service_type_id=resource.service_type_id,
            )
            db.session.add(group)
            db.session.flush()
        quota = models.Quota(
            group_id=group.id,
            resource_id=resource.id,
            quota=data.get("quota", 0),
            requested_quota=data.get("requested_quota", 0),
        )
        db.session.add(quota)
        db.session.commit()
        return quota

    def delete_quota(self, quota):
        group = quota.group
        db.session.delete(quota)
        db.session.flush()
        db.session.expire(group, ["quotas"])
        if len(group.quotas) < 1:
            db.session.delete(group)
        db.session.commit()

    # ------------------------------------------------------------------
    # warnings
    # ------------------------------------------------------------------

    def _check_warnings(self, allocation, ignore_warnings, approving):
        if ignore_warnings:
            return
        db.session.flush()
        db.session.expire(allocation)
        values = checkers.values_from_allocation(allocation, approving)
        checker = checkers.QuotaSanityChecker(
            allocation=allocation,
            values=values,
            user_name=self.user_name,
            approving=approving,
        )
        warnings = checker.do_checks()
        if warnings:
            db.session.rollback()
            raise exceptions.WarningsError(checkers.as_dicts(warnings))

    def checks(self, allocation, approving=False):
        values = checkers.values_from_allocation(allocation, approving)
        warnings = checkers.QuotaSanityChecker(
            allocation=allocation,
            values=values,
            user_name=self.user_name,
            approving=approving,
        ).do_checks()
        nags = checkers.NagChecker(
            allocation=allocation, values=values, user_name=self.user_name
        ).do_checks()
        return {
            "warnings": checkers.as_dicts(warnings),
            "nags": checkers.as_dicts(nags),
        }

    # ------------------------------------------------------------------
    # allocation lifecycle
    # ------------------------------------------------------------------

    def create_allocation(self, data, is_admin):
        data, nested, control = self._split(data)
        data = self._apply_allocation_home(
            data, control.get("allocation_home"), is_admin
        )
        allocation = models.AllocationRequest()
        allocation.created_by = self.user_id
        if not data.get("contact_email"):
            data["contact_email"] = self.user_name
        self._check_project_name(None, data)
        self._apply_fields(allocation, data)
        now = models.utcnow()
        allocation.status = choices.SUBMITTED
        allocation.submit_date = now
        allocation.modified_time = now
        db.session.add(allocation)
        db.session.flush()
        self._apply_nested(allocation, nested)
        self._check_warnings(
            allocation, control.get("ignore_warnings", True), approving=False
        )
        db.session.commit()
        notification.send_notifications(allocation)
        return allocation

    def update_allocation(self, allocation, data, is_admin):
        """Plain PUT/PATCH: no history row, no transition, no email."""
        data, nested, control = self._split(data)
        data = self._apply_allocation_home(
            data, control.get("allocation_home"), is_admin
        )
        self._check_project_name(allocation, data)
        self._apply_fields(allocation, data)
        self._apply_nested(allocation, nested)
        if set(data) - METADATA_FIELDS or nested:
            allocation.modified_time = models.utcnow()
        db.session.commit()
        return allocation

    def submit(self, allocation, data, is_admin, editor_is_approver=False):
        """Edit and (re)submit a request, keeping history.

        Mirrors the dashboard's edit forms: snapshot, apply the changes,
        move declined requests back to pending, refresh the submission
        date and acknowledge by email.
        """
        data, nested, control = self._split(data)
        data = self._apply_allocation_home(
            data, control.get("allocation_home"), is_admin
        )
        self._check_project_name(allocation, data)
        self.copy_allocation(allocation)
        self._apply_fields(allocation, data)
        if allocation.status in (
            choices.UPDATE_PENDING,
            choices.UPDATE_DECLINED,
        ):
            allocation.status = choices.UPDATE_PENDING
        else:
            allocation.status = choices.SUBMITTED
        if editor_is_approver:
            allocation.approver_email = self.user_name
        else:
            allocation.contact_email = (
                allocation.contact_email or self.user_name
            )
        allocation.provisioned = False
        allocation.estimated_number_users = None
        now = models.utcnow()
        allocation.submit_date = now
        allocation.modified_time = now
        self._apply_nested(allocation, nested)
        self._check_warnings(
            allocation, control.get("ignore_warnings", True), approving=False
        )
        db.session.commit()
        notification.send_notifications(allocation)
        return allocation

    def approve(self, allocation, data=None):
        data, nested, control = self._split(data or {})
        # Approvers set admin fields; the gated-field check does not apply.
        associated_site = data.get(
            "associated_site", allocation.associated_site
        )
        if associated_site is None:
            raise exceptions.ActionError(
                "The associated_site attribute must be set before approving"
            )
        self.copy_allocation(allocation)
        self._apply_fields(allocation, data)
        self._apply_nested(allocation, nested, approving=True)
        allocation.status = choices.APPROVED
        allocation.provisioned = False
        allocation.approver_email = self.user_name
        allocation.modified_time = models.utcnow()
        self._check_warnings(
            allocation, control.get("ignore_warnings", True), approving=True
        )
        db.session.commit()
        return allocation

    def decline(self, allocation, status_explanation=None):
        self.copy_allocation(allocation)
        if allocation.status == choices.UPDATE_PENDING:
            allocation.status = choices.UPDATE_DECLINED
        else:
            allocation.status = choices.DECLINED
        if status_explanation is not None:
            allocation.status_explanation = status_explanation
        allocation.approver_email = self.user_name
        allocation.provisioned = False
        allocation.modified_time = models.utcnow()
        db.session.commit()
        notification.send_notifications(allocation)
        return allocation

    def amend(self, allocation, data=None, is_admin=False):
        data, nested, control = self._split(data or {})
        data = self._apply_allocation_home(
            data, control.get("allocation_home"), is_admin
        )
        self.copy_allocation(allocation)
        self._apply_fields(allocation, data)
        allocation.status = choices.UPDATE_PENDING
        allocation.provisioned = False
        if data or nested:
            now = models.utcnow()
            allocation.submit_date = now
            allocation.estimated_number_users = None
        allocation.modified_time = models.utcnow()
        self._apply_nested(allocation, nested)
        self._check_warnings(
            allocation, control.get("ignore_warnings", True), approving=False
        )
        db.session.commit()
        notification.send_notifications(allocation)
        return allocation

    def delete(self, allocation):
        # (Deleting an allocation is idempotent)
        if allocation.status != choices.DELETED:
            self.copy_allocation(allocation)
            allocation.status = choices.DELETED
            allocation.modified_time = models.utcnow()
            db.session.commit()
        return allocation

    def approver_info(self, allocation):
        if allocation.parent_request_id:
            raise exceptions.ActionError(
                "The allocation cannot be a history record"
            )
        u, e = urgency.get_urgency_info(allocation)
        if allocation.status not in [
            choices.NEW,
            choices.SUBMITTED,
            choices.UPDATE_PENDING,
        ]:
            u = "N/A"
        sites = [s.name for s in utils.get_interested_sites(allocation)]
        return {
            'approval_urgency': u,
            'expiry_state': e,
            'concerned_sites': sites,
        }

    # ------------------------------------------------------------------
    # related records
    # ------------------------------------------------------------------

    def _owned_pending_allocation(self, allocation_id, is_write_admin):
        Allocation = models.AllocationRequest
        query = db.session.query(Allocation).filter(
            Allocation.id == allocation_id
        )
        if not is_write_admin:
            query = query.filter(Allocation.contact_email == self.user_name)
        allocation = query.first()
        if allocation is None:
            raise exceptions.ValidationError(["Allocation does not exist"])
        if allocation.status not in choices.PENDING_STATUSES:
            raise exceptions.ValidationError(
                [
                    f"Allocation in status '{allocation.status_display}' "
                    "can not be updated"
                ]
            )
        return allocation

    def create_related(self, model, data, is_write_admin):
        data = dict(data)
        allocation = self._owned_pending_allocation(
            data.pop("allocation_id"), is_write_admin
        )
        obj = model(allocation_id=allocation.id)
        for key, value in data.items():
            setattr(obj, key, value)
        db.session.add(obj)
        db.session.commit()
        return obj

    def update_related(self, obj, data, is_write_admin):
        data = dict(data)
        allocation_id = data.pop("allocation_id", obj.allocation_id)
        self._owned_pending_allocation(obj.allocation_id, is_write_admin)
        if allocation_id != obj.allocation_id:
            self._owned_pending_allocation(allocation_id, is_write_admin)
            obj.allocation_id = allocation_id
        for key, value in data.items():
            setattr(obj, key, value)
        db.session.commit()
        return obj

    def delete_related(self, obj):
        db.session.delete(obj)
        db.session.commit()

    # ------------------------------------------------------------------
    # organisations
    # ------------------------------------------------------------------

    def _check_unique_proposal(self, data):
        Organisation = models.Organisation
        full_name = data.get('full_name')
        if full_name:
            existing = (
                db.session.query(Organisation)
                .filter(
                    sa.func.lower(Organisation.full_name) == full_name.lower()
                )
                .first()
            )
            if existing:
                raise exceptions.ValidationError(
                    {
                        'full_name': [
                            "An Organisation with this full name already "
                            "exists."
                            if existing.enabled
                            else "An Organisation with this full name has "
                            "already been rejected."
                        ]
                    }
                )
        url = data.get('url')
        if url:
            existing = (
                db.session.query(Organisation)
                .filter(sa.func.lower(Organisation.url) == url.lower())
                .first()
            )
            if existing:
                raise exceptions.ValidationError(
                    {
                        'url': [
                            "An Organisation with this url already exists."
                            if existing.enabled
                            else "An Organisation with this url has "
                            "already been rejected."
                        ]
                    }
                )

    def propose_organisation(self, data):
        self._check_unique_proposal(data)
        organisation = models.Organisation(
            full_name=data["full_name"],
            short_name=data["short_name"],
            url=data["url"],
            country=data["country"],
            ror_id="",
            vetted_by_id=None,
            proposed_by=self.user_id or "",
            enabled=True,
        )
        db.session.add(organisation)
        db.session.commit()
        return organisation

    def create_organisation(self, data):
        organisation = models.Organisation()
        self._apply_organisation(organisation, data)
        db.session.add(organisation)
        db.session.commit()
        return organisation

    def update_organisation(self, organisation, data):
        self._apply_organisation(organisation, data)
        db.session.commit()
        return organisation

    def _apply_organisation(self, organisation, data):
        data = dict(data)
        if "precedes" in data:
            organisation.precedes = data.pop("precedes")
        for key, value in data.items():
            setattr(organisation, key, value)

    def vet_organisation(self, organisation, enable):
        if organisation.ror_id:
            raise exceptions.ValidationError(
                {
                    'ror_id': [
                        "An Organisation from the ROR should not be vetted."
                    ]
                }
            )
        approver = (
            db.session.query(models.Approver)
            .filter_by(username=self.user_name)
            .first()
        )
        if approver is None:
            approver = (
                db.session.query(models.Approver)
                .filter_by(username='system')
                .first()
            )
        if approver is None:
            raise exceptions.ValidationError(
                [
                    "No Approver record exists for the caller and no "
                    "'system' approver is configured."
                ]
            )
        organisation.vetted_by = approver
        organisation.enabled = enable
        db.session.commit()
        return organisation

    # ------------------------------------------------------------------
    # reference data
    # ------------------------------------------------------------------

    def unique_check(self, model, field, value, exclude=None):
        """Reject a duplicate value with DRF's UniqueValidator wording."""
        column = getattr(model, field)
        query = db.session.query(model).filter(column == value)
        if exclude is not None:
            pk = model.__mapper__.primary_key[0]
            query = query.filter(pk != getattr(exclude, pk.name))
        if query.first() is not None:
            name = model.__name__
            if name == "ARDCSupport":
                name = "ARDC support"
            elif name == "NCRISFacility":
                name = "NCRIS facility"
            else:
                name = name.lower()
            raise exceptions.ValidationError(
                {
                    field: [
                        f"{name} with this {field.replace('_', ' ')} "
                        "already exists."
                    ]
                }
            )

    def unique_together_check(self, model, fields, values, exclude=None):
        """Reject duplicates across several columns (DRF wording)."""
        query = db.session.query(model)
        for field in fields:
            value = values[field]
            if hasattr(value, "__mapper__"):
                # A related object: compare its primary key column.
                pk = value.__mapper__.primary_key[0]
                query = query.filter(
                    getattr(model, f"{field}_id") == getattr(value, pk.name)
                )
            else:
                query = query.filter(getattr(model, field) == value)
        if exclude is not None:
            pk = model.__mapper__.primary_key[0]
            query = query.filter(pk != getattr(exclude, pk.name))
        if query.first() is not None:
            raise exceptions.ValidationError(
                {
                    "non_field_errors": [
                        f"The fields {', '.join(fields)} must make a unique "
                        "set."
                    ]
                }
            )

    def create_simple(self, model, data, unique=(), unique_together=()):
        for field in unique:
            if field in data:
                self.unique_check(model, field, data[field])
        for fields in unique_together:
            if all(field in data for field in fields):
                self.unique_together_check(model, fields, data)
        obj = model()
        for key, value in data.items():
            setattr(obj, key, value)
        db.session.add(obj)
        db.session.commit()
        return obj

    def update_simple(self, obj, data, unique=(), unique_together=()):
        for field in unique:
            if field in data:
                self.unique_check(type(obj), field, data[field], exclude=obj)
        for fields in unique_together:
            if any(field in data for field in fields):
                values = {
                    field: data.get(field, getattr(obj, field))
                    for field in fields
                }
                self.unique_together_check(
                    type(obj), fields, values, exclude=obj
                )
        for key, value in data.items():
            setattr(obj, key, value)
        db.session.commit()
        return obj

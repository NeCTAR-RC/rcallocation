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

"""Allocation request endpoints."""

import flask
import sqlalchemy as sa

from rcallocation.api.v1 import base
from rcallocation.api.v1 import filtering
from rcallocation.api.v1 import pagination
from rcallocation.api.v1.schemas import allocation as schemas
from rcallocation import choices
from rcallocation.common import exceptions
from rcallocation.common import policies
from rcallocation.common import projects
from rcallocation.extensions import db
from rcallocation import manager
from rcallocation import models


Allocation = models.AllocationRequest

blp = base.v1_blueprint(
    "allocations",
    __name__,
    "allocations",
    description="Allocation requests and their history",
)

TEXT_LOOKUPS = [
    "exact",
    "contains",
    "icontains",
    "startswith",
    "istartswith",
    "endswith",
    "iendswith",
    "regex",
]
DATE_LOOKUPS = ["exact", "lt", "gt", "gte", "lte", "year"]
DATETIME_LOOKUPS = ["exact", "lt", "gt", "gte", "lte", "date", "year"]


def _filter_allocation_home(query, lookup, value):
    if value == choices.ALLOC_HOME_NATIONAL:
        return query.filter(Allocation.national.is_(True))
    if value == choices.ALLOC_HOME_UNASSIGNED:
        return query.filter(
            Allocation.national.is_(False),
            Allocation.associated_site_id.is_(None),
        )
    return query.filter(
        Allocation.national.is_(False),
        Allocation.associated_site.has(models.Site.name == value),
    )


def _filter_chief_investigator(query, lookup, value):
    return query.filter(
        Allocation.investigators.any(models.ChiefInvestigator.email == value)
    )


def _filter_associated_site(query, lookup, value):
    return query.filter(
        Allocation.associated_site.has(models.Site.name == value)
    )


class AllocationFilterSet(filtering.FilterSet):
    filters = {
        "status": filtering.F(Allocation.status, ["exact", "in"]),
        "parent_request_id": filtering.F(Allocation.parent_request_id),
        "parent_request": filtering.F(
            Allocation.parent_request_id, ["exact", "isnull"]
        ),
        "project_id": filtering.F(Allocation.project_id, ["exact", "in"]),
        "project_name": filtering.F(Allocation.project_name, TEXT_LOOKUPS),
        "convert_trial_project": filtering.F(Allocation.convert_trial_project),
        "provisioned": filtering.F(Allocation.provisioned),
        "national": filtering.F(Allocation.national),
        "managed": filtering.F(Allocation.managed),
        "notifications": filtering.F(Allocation.notifications),
        "contact_email": filtering.F(Allocation.contact_email, TEXT_LOOKUPS),
        "approver_email": filtering.F(Allocation.approver_email, TEXT_LOOKUPS),
        "start_date": filtering.F(Allocation.start_date, DATE_LOOKUPS),
        "end_date": filtering.F(Allocation.end_date, DATE_LOOKUPS),
        "modified_time": filtering.F(
            Allocation.modified_time, DATETIME_LOOKUPS
        ),
        "submit_date": filtering.F(Allocation.submit_date, DATETIME_LOOKUPS),
        "created_by": filtering.F(Allocation.created_by),
    }
    methods = {
        "allocation_home": _filter_allocation_home,
        "chief_investigator": _filter_chief_investigator,
        "associated_site": _filter_associated_site,
    }


class PublicAllocationFilterSet(filtering.FilterSet):
    """The filters an unauthenticated caller may use.

    Restricted to the fields PublicAllocationSchema exposes, plus
    parent_request__isnull so history records can be excluded.
    """

    filters = {
        "project_name": filtering.F(
            Allocation.project_name, TEXT_LOOKUPS[:-1]
        ),
        "field_of_research_1": filtering.F(Allocation.field_of_research_1),
        "field_of_research_2": filtering.F(Allocation.field_of_research_2),
        "field_of_research_3": filtering.F(Allocation.field_of_research_3),
        "start_date": filtering.F(Allocation.start_date, DATE_LOOKUPS),
        "end_date": filtering.F(Allocation.end_date, DATE_LOOKUPS),
        "modified_time": filtering.F(
            Allocation.modified_time, DATETIME_LOOKUPS
        ),
        "submit_date": filtering.F(Allocation.submit_date, DATETIME_LOOKUPS),
        "parent_request": filtering.F(
            Allocation.parent_request_id, ["isnull"]
        ),
    }


class AllocationResource(base.Resource):
    POLICY_PREFIX = policies.ALLOCATION_PREFIX
    schema = schemas.AllocationSchema()
    admin_schema = schemas.AdminAllocationSchema()
    public_schema = schemas.PublicAllocationSchema()
    filterset = AllocationFilterSet
    public_filterset = PublicAllocationFilterSet

    def own_filter(self):
        """SQL condition for the allocations a non-admin may see.

        Their own requests (they are the contact), the approved
        allocation of the project their token is scoped to, and every
        allocation of the projects they manage.
        """
        ctx = self.context
        conditions = [Allocation.contact_email == ctx.user_name]
        if ctx.project_id:
            conditions.append(
                sa.and_(
                    Allocation.project_id == ctx.project_id,
                    Allocation.status == choices.APPROVED,
                )
            )
        managed = projects.managed_project_ids(ctx.user_id)
        if managed:
            conditions.append(Allocation.project_id.in_(sorted(managed)))
        return sa.or_(*conditions)

    def visible_query(self):
        query = db.session.query(Allocation)
        if self.caller_kind == base.ANONYMOUS:
            return query
        if self.authorize("list:all", do_raise=False):
            return query
        return query.filter(self.own_filter())

    def write_schema(self, partial=False, submit=False):
        if submit:
            cls = (
                schemas.AllocationAdminSubmitSchema
                if self.is_write_admin
                else schemas.AllocationUserSubmitSchema
            )
        else:
            cls = (
                schemas.AllocationAdminWriteSchema
                if self.is_write_admin
                else schemas.AllocationUserWriteSchema
            )
        return cls(partial=partial)

    def get_visible(self, allocation_id):
        return self.get_or_404(
            Allocation, allocation_id, query=self.visible_query()
        )

    def require_live(self, allocation):
        if allocation.is_history():
            raise exceptions.PermissionDenied(
                "Permission denied or allocation in wrong state."
            )

    def require_state(self, allocation, states):
        if allocation.status not in states:
            raise exceptions.PermissionDenied(
                "Permission denied or allocation in wrong state."
            )

    def manager(self):
        return manager.Manager(self.context)

    def dump_with_info(self, allocations, include_info):
        data = self.dump(allocations, many=True)
        if include_info and self.is_read_admin:
            mgr = self.manager()
            for allocation, item in zip(allocations, data):
                if allocation.is_history():
                    continue
                item.update(mgr.approver_info(allocation))
        return data


@blp.route("/")
class AllocationList(AllocationResource):
    def get(self):
        self.require("list")
        query = self.visible_query()
        if filtering.parse_bool(flask.request.args.get("mine")) and (
            not self.context.is_anonymous
        ):
            query = query.filter(self.own_filter())
        query = self.filter(query).order_by(
            Allocation.modified_time.desc(), Allocation.id.desc()
        )
        include_info = flask.request.args.get("include") == "approver_info"
        return pagination.paginate(
            query, lambda items: self.dump_with_info(items, include_info)
        )

    def post(self):
        self.require("create")
        data = self.body(self.write_schema(submit=True))
        allocation = self.manager().create_allocation(
            data, is_admin=self.is_write_admin
        )
        return self.dump(allocation), 201


@blp.route("/<int:allocation_id>/")
class AllocationItem(AllocationResource):
    def get(self, allocation_id):
        self.require("get")
        return self.dump(self.get_visible(allocation_id))

    def _update(self, allocation_id, partial):
        self.require_authenticated()
        allocation = self.get_visible(allocation_id)
        self.require_object("update", allocation)
        self.require_live(allocation)
        self.require_state(allocation, choices.PENDING_STATUSES)
        data = self.body(self.write_schema(partial=partial))
        allocation = self.manager().update_allocation(
            allocation, data, is_admin=self.is_write_admin
        )
        return self.dump(allocation)

    def put(self, allocation_id):
        return self._update(allocation_id, partial=False)

    def patch(self, allocation_id):
        return self._update(allocation_id, partial=True)

    def delete(self, allocation_id):
        self.require_authenticated()
        raise exceptions.MethodNotAllowed("DELETE")


@blp.route("/<int:allocation_id>/approve/")
class AllocationApprove(AllocationResource):
    def post(self, allocation_id):
        self.require("approve")
        allocation = self.get_visible(allocation_id)
        self.require_live(allocation)
        self.require_state(allocation, choices.PENDING_STATUSES)
        data = self.body(schemas.AllocationApproveSchema())
        allocation = self.manager().approve(allocation, data)
        return self.dump(allocation)


@blp.route("/<int:allocation_id>/decline/")
class AllocationDecline(AllocationResource):
    def post(self, allocation_id):
        self.require("decline")
        allocation = self.get_visible(allocation_id)
        self.require_live(allocation)
        self.require_state(allocation, choices.PENDING_STATUSES)
        data = self.body(schemas.AllocationDeclineSchema())
        explanation = data.get("status_explanation")
        if explanation is None:
            explanation = data.get("reason")
        allocation = self.manager().decline(allocation, explanation)
        return self.dump(allocation)


@blp.route("/<int:allocation_id>/submit/")
class AllocationSubmit(AllocationResource):
    EDITABLE = (
        choices.NEW,
        choices.SUBMITTED,
        choices.DECLINED,
        choices.UPDATE_PENDING,
        choices.UPDATE_DECLINED,
    )

    def post(self, allocation_id):
        self.require_authenticated()
        allocation = self.get_visible(allocation_id)
        self.require_object("submit", allocation)
        self.require_live(allocation)
        self.require_state(allocation, self.EDITABLE)
        data = self.body(self.write_schema(partial=True, submit=True))
        allocation = self.manager().submit(
            allocation,
            data,
            is_admin=self.is_write_admin,
            editor_is_approver=self.is_write_admin,
        )
        return self.dump(allocation)


@blp.route("/<int:allocation_id>/amend/")
class AllocationAmend(AllocationResource):
    def post(self, allocation_id):
        self.require_authenticated()
        allocation = self.get_visible(allocation_id)
        self.require_object("amend", allocation)
        self.require_live(allocation)
        self.require_state(allocation, (choices.APPROVED, choices.DECLINED))
        data = self.body(self.write_schema(partial=True, submit=True))
        allocation = self.manager().amend(
            allocation, data, is_admin=self.is_write_admin
        )
        return self.dump(allocation)


@blp.route("/<int:allocation_id>/delete/")
class AllocationDelete(AllocationResource):
    def post(self, allocation_id):
        self.require("delete")
        allocation = self.get_visible(allocation_id)
        self.require_live(allocation)
        allocation = self.manager().delete(allocation)
        return self.dump(allocation)


@blp.route("/<int:allocation_id>/approver_info/")
class AllocationApproverInfo(AllocationResource):
    def get(self, allocation_id):
        """Get the approver info for this allocation, comprising the
        approval urgency, the inferred expiry state and the list of
        sites that are inferred to be 'concerned' with the allocation.
        If the allocation is not pending, we will return 'N/A' as the
        urgency.  This is all derived info, and the derivation process is
        heuristic and subject to tweaking.
        """
        self.require("approver_info")
        allocation = self.get_visible(allocation_id)
        return self.manager().approver_info(allocation)


@blp.route("/<int:allocation_id>/checks/")
class AllocationChecks(AllocationResource):
    def get(self, allocation_id):
        self.require_authenticated()
        allocation = self.get_visible(allocation_id)
        self.require_object("checks", allocation)
        approving = (
            filtering.parse_bool(flask.request.args.get("approving")) or False
        ) and self.is_write_admin
        return self.manager().checks(allocation, approving=approving)

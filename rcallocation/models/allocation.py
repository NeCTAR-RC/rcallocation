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

"""The allocation request and the records hanging off it."""

from rcallocation import choices
from rcallocation.extensions import db
from rcallocation.models import base
from rcallocation.models import organisation as org_models
from rcallocation.models import reference


class AllocationRequest(db.Model):
    """An AllocationRequest represents a point in time in the history of
    a Nectar allocation.  The history is represented by the parent request
    chain.  When a significant change is made.  The id (pk) of the most
    recent AllocationRequest record for an allocation should remain the
    same.
    """

    __tablename__ = "allocation_request"

    NEW = choices.NEW
    SUBMITTED = choices.SUBMITTED
    APPROVED = choices.APPROVED
    DECLINED = choices.DECLINED
    UPDATE_PENDING = choices.UPDATE_PENDING
    UPDATE_DECLINED = choices.UPDATE_DECLINED
    DELETED = choices.DELETED

    id = db.Column(db.Integer, primary_key=True)
    parent_request_id = db.Column(
        db.Integer,
        db.ForeignKey("allocation_request.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = db.Column(
        db.String(1), nullable=False, default=choices.SUBMITTED, index=True
    )
    #: A brief explanation of the reason the request has been sent back
    #: to the user for changes
    status_explanation = db.Column(base.LongText, nullable=True)
    #: Keystone user id of the creator
    created_by = db.Column(db.String(100), nullable=False)
    submit_date = db.Column(db.DateTime, nullable=False, default=base.utcnow)
    modified_time = db.Column(
        db.DateTime, nullable=False, default=base.utcnow, index=True
    )

    # The ordering of the following fields are important, as it
    # governs the order they appear on the forms
    #: A short name used to identify the project
    project_name = db.Column(db.String(64), nullable=True)
    #: A human-friendly descriptive name for the research project
    project_description = db.Column(db.String(200), nullable=False)
    contact_email = db.Column(
        db.String(254), nullable=False, default="", index=True
    )
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    estimated_project_duration = db.Column(
        db.Integer, nullable=False, default=12
    )
    convert_trial_project = db.Column(
        db.Boolean, nullable=False, default=False
    )
    approver_email = db.Column(db.String(254), nullable=False, default="")
    #: Research project description
    use_case = db.Column(base.LongText, nullable=False)
    #: Justification and details of the proposed cloud usage
    usage_patterns = db.Column(base.LongText, nullable=False, default="")
    #: Special location requirements
    geographic_requirements = db.Column(
        base.LongText, nullable=False, default=""
    )
    project_id = db.Column(db.String(36), nullable=True, index=True)
    #: Read only legacy field, no longer used
    estimated_number_users = db.Column(db.Integer, nullable=True)
    direct_access_user_estimate = db.Column(db.Integer, nullable=True)
    estimated_service_count = db.Column(db.Integer, nullable=True)
    estimated_service_active_users = db.Column(db.Integer, nullable=True)
    multiple_allocations_check = db.Column(
        db.Boolean, nullable=True, default=False
    )
    direct_access_user_past_year = db.Column(db.Integer, nullable=True)
    active_service_count = db.Column(db.Integer, nullable=True)
    service_active_users_past_year = db.Column(db.Integer, nullable=True)
    users_figure_type = db.Column(
        db.String(10), nullable=True, default=choices.MEASURED
    )
    has_sensitive_data = db.Column(db.String(20), nullable=True)
    data_classification_level = db.Column(db.String(10), nullable=True)
    institutional_data_review = db.Column(db.String(10), nullable=True)
    field_of_research_1 = db.Column(db.String(6), nullable=True)
    for_percentage_1 = db.Column(db.Integer, nullable=False, default=100)
    field_of_research_2 = db.Column(db.String(6), nullable=True)
    for_percentage_2 = db.Column(db.Integer, nullable=False, default=0)
    field_of_research_3 = db.Column(db.String(6), nullable=True)
    for_percentage_3 = db.Column(db.Integer, nullable=False, default=0)
    #: Legacy free text, superseded by the ardc_support relation
    nectar_support = db.Column(db.String(255), nullable=False, default="")
    ardc_explanation = db.Column(db.String(1024), nullable=False, default="")
    #: Legacy free text, superseded by the ncris_facilities relation
    ncris_support = db.Column(db.String(255), nullable=False, default="")
    ncris_explanation = db.Column(db.String(1024), nullable=False, default="")
    #: The Nectar site primarily associated with this allocation
    associated_site_id = db.Column(
        db.Integer, db.ForeignKey("site.id"), nullable=True
    )
    #: Most recently assessed as meeting the Nectar National criteria
    national = db.Column(db.Boolean, nullable=False, default=False)
    #: Special RC-NAS approval reasons (admins only)
    special_approval = db.Column(db.String(1024), nullable=False, default="")
    provisioned = db.Column(db.Boolean, nullable=False, default=False)
    #: Private notes for admins
    notes = db.Column(base.LongText, nullable=True)
    #: Send notifications for this allocation
    notifications = db.Column(db.Boolean, nullable=False, default=True)
    #: Whether the allocation is managed through the dashboard
    managed = db.Column(db.Boolean, nullable=False, default=True)
    bundle_id = db.Column(
        db.Integer, db.ForeignKey("bundle.id"), nullable=True
    )
    nectar_benefit_description = db.Column(base.LongText, nullable=True)
    nectar_research_impact = db.Column(base.LongText, nullable=True)

    parent_request = db.relationship(
        "AllocationRequest",
        remote_side=[id],
        foreign_keys=[parent_request_id],
        backref=db.backref(
            "history", lazy="dynamic", order_by="AllocationRequest.id"
        ),
    )
    associated_site = db.relationship(reference.Site, lazy="joined")
    bundle = db.relationship(reference.Bundle, lazy="joined")
    quota_groups = db.relationship(
        "QuotaGroup",
        back_populates="allocation",
        lazy="selectin",
        order_by="(QuotaGroup.zone_id, QuotaGroup.service_type_id, "
        "QuotaGroup.id)",
        cascade="all, delete-orphan",
    )
    investigators = db.relationship(
        "ChiefInvestigator",
        back_populates="allocation",
        lazy="selectin",
        order_by="ChiefInvestigator.id",
        cascade="all, delete-orphan",
    )
    publications = db.relationship(
        "Publication",
        back_populates="allocation",
        lazy="selectin",
        order_by="Publication.id",
        cascade="all, delete-orphan",
    )
    grants = db.relationship(
        "Grant",
        back_populates="allocation",
        lazy="selectin",
        order_by="Grant.id",
        cascade="all, delete-orphan",
    )
    usage_types = db.relationship(
        reference.UsageType,
        secondary=base.allocation_usage_type,
        lazy="selectin",
        order_by=reference.UsageType.id,
    )
    ncris_facilities = db.relationship(
        reference.NCRISFacility,
        secondary=base.allocation_ncris_facility,
        lazy="selectin",
        order_by=reference.NCRISFacility.short_name,
    )
    ardc_support = db.relationship(
        reference.ARDCSupport,
        secondary=base.allocation_ardc_support,
        lazy="selectin",
        order_by=reference.ARDCSupport.short_name,
    )
    supported_organisations = db.relationship(
        org_models.Organisation,
        secondary=base.allocation_organisation,
        lazy="selectin",
        order_by=org_models.Organisation.id,
    )

    __table_args__ = (
        db.CheckConstraint(
            "direct_access_user_estimate >= 0",
            name="ck_allocation_direct_access_user_estimate",
        ),
        db.CheckConstraint(
            "estimated_service_count >= 0",
            name="ck_allocation_estimated_service_count",
        ),
        db.CheckConstraint(
            "estimated_service_active_users >= 0",
            name="ck_allocation_estimated_service_active_users",
        ),
        db.CheckConstraint(
            "direct_access_user_past_year >= 0",
            name="ck_allocation_direct_access_user_past_year",
        ),
        db.CheckConstraint(
            "active_service_count >= 0",
            name="ck_allocation_active_service_count",
        ),
        db.CheckConstraint(
            "service_active_users_past_year >= 0",
            name="ck_allocation_service_active_users_past_year",
        ),
    )

    # -- derived attributes --------------------------------------------------

    @property
    def status_display(self):
        return choices.REQUEST_STATUS_MAP.get(self.status, self.status)

    @property
    def allocation_home(self):
        if self.national:
            return choices.ALLOC_HOME_NATIONAL
        elif not self.associated_site:
            return choices.ALLOC_HOME_UNASSIGNED
        else:
            return self.associated_site.name

    @property
    def allocation_home_display(self):
        if self.national:
            return 'National'
        elif not self.associated_site:
            return 'Unassigned'
        else:
            return self.associated_site.display_name

    @property
    def su_budget(self):
        budget_quota = self.get_quota('rating.budget')
        if self.bundle:
            if budget_quota is not None:
                return budget_quota
            return int(
                self.bundle.su_per_year / 12 * self.estimated_project_duration
            )
        return budget_quota

    @property
    def primary_id(self):
        return self.parent_request_id or self.id

    @property
    def chief_investigator_email(self):
        if self.investigators:
            return self.investigators[0].email
        return None

    # -- state predicates --------------------------------------------------------

    def is_active(self):
        """Return True if the allocation has either been approved,
        false otherwise.
        """
        return self.status.upper() == self.APPROVED

    def is_rejected(self):
        """Return True if the allocation has either been accepted or
        rejected, false otherwise.
        """
        return self.status.upper() in (self.DECLINED, self.UPDATE_DECLINED)

    def is_requested(self):
        return self.status.upper() in (self.SUBMITTED, self.NEW)

    def amendment_requested(self):
        """Return True if the user has requested an extension"""
        return self.status.upper() in (
            self.UPDATE_PENDING,
            self.UPDATE_DECLINED,
        )

    def is_history(self):
        return self.parent_request_id is not None

    def can_be_amended(self):
        return self.is_active() and not self.is_history() and self.managed

    def can_be_edited(self):
        return not self.is_active() and not self.is_history() and self.managed

    def can_user_edit(self):
        return (
            self.status.upper() in (self.SUBMITTED, self.DECLINED, self.NEW)
            and not self.is_history()
            and self.managed
        )

    def can_user_edit_amendment(self):
        return (
            self.amendment_requested()
            and not self.is_history()
            and self.managed
        )

    def can_be_rejected(self):
        return self.is_requested() and not self.is_history() and self.managed

    def can_be_approved(self):
        return self.is_requested() and not self.is_history() and self.managed

    def can_reject_change(self):
        return self.can_approve_change()

    def can_approve_change(self):
        return self.amendment_requested() and not self.is_history()

    def can_have_publications(self):
        return self.status.upper() not in (
            self.SUBMITTED,
            self.DECLINED,
            self.NEW,
        )

    # -- quotas ----------------------------------------------------------------------

    def all_quotas(self):
        return [q for group in self.quota_groups for q in group.quotas]

    def get_quota(self, resource_code):
        """The allocated quota for a resource codename, or None."""
        for group in self.quota_groups:
            for quota in group.quotas:
                if quota.resource.codename == resource_code:
                    return quota.quota
        return None

    def quota_list(self):
        """Effective quotas: bundle quotas, the SU budget, then overrides.

        Dict insertion order is preserved so the output order matches the
        old API: bundle quotas in BundleQuota order, then the budget, then
        the allocation's own quota rows.
        """
        quotas = {}
        if self.bundle:
            zone = self.bundle.zone_id
            for bq in self.bundle.bundle_quotas:
                quotas[f"{bq.resource.codename}-{zone}"] = bq.quota_dict()
            budget = self.su_budget
            quotas[f"rating.budget-{zone}"] = {
                'zone': zone,
                'resource': 'rating.budget',
                'quota': budget,
                'requested_quota': budget,
            }
        for override in self.all_quotas():
            key = f"{override.resource.codename}-{override.group.zone_id}"
            quotas[key] = override.quota_dict()
        return list(quotas.values())

    def get_quotas_context(self):
        """Quota details for the notification templates."""
        quotas = []
        for quota in self.all_quotas():
            quotas.append(
                {
                    'service_type': quota.group.service_type.name,
                    'resource': quota.resource.name,
                    'resource_type': quota.resource.resource_type,
                    'unit': quota.resource.unit,
                    'zone': quota.group.zone.display_name,
                    'quota': quota.quota,
                    'requested_quota': quota.requested_quota,
                }
            )
        return quotas

    def __repr__(self):
        return f"<AllocationRequest {self.id}: {self.project_name}>"


class QuotaGroup(db.Model):
    """A QuotaGroup object relates a group of Quotas (for resources in
    one ServiceType) to a Zone and an AllocationRequest.
    """

    __tablename__ = "quota_group"

    id = db.Column(db.Integer, primary_key=True)
    allocation_id = db.Column(
        db.Integer,
        db.ForeignKey("allocation_request.id", ondelete="CASCADE"),
        nullable=False,
    )
    zone_id = db.Column(
        db.String(32),
        db.ForeignKey("zone.name", ondelete="CASCADE"),
        nullable=False,
    )
    service_type_id = db.Column(
        db.String(32),
        db.ForeignKey("service_type.catalog_name", ondelete="CASCADE"),
        nullable=False,
    )

    allocation = db.relationship(
        AllocationRequest, back_populates="quota_groups"
    )
    zone = db.relationship(reference.Zone, lazy="joined")
    service_type = db.relationship(reference.ServiceType, lazy="joined")
    quotas = db.relationship(
        "Quota",
        back_populates="group",
        lazy="selectin",
        order_by="Quota.id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "allocation_id",
            "zone_id",
            "service_type_id",
            name="uq_quota_group_alloc_zone_st",
        ),
    )

    def __repr__(self):
        return (
            f"<QuotaGroup {self.allocation_id} {self.service_type_id} "
            f"{self.zone_id}>"
        )


class Quota(db.Model):
    """A Quota object represent the actual value for a given Resource
    for a particular allocation.  (The relation to the allocation is
    via the QuotaGroup.)
    """

    __tablename__ = "quota"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(
        db.Integer,
        db.ForeignKey("quota_group.id", ondelete="CASCADE"),
        nullable=False,
    )
    resource_id = db.Column(
        db.Integer,
        db.ForeignKey("resource.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_quota = db.Column(db.Integer, nullable=False, default=0)
    quota = db.Column(db.Integer, nullable=False, default=0)

    group = db.relationship(QuotaGroup, back_populates="quotas")
    resource = db.relationship(reference.Resource, lazy="joined")

    __table_args__ = (
        db.UniqueConstraint(
            "group_id", "resource_id", name="uq_quota_group_resource"
        ),
        db.CheckConstraint("quota >= -1", name="ck_quota_quota"),
        db.CheckConstraint(
            "requested_quota >= -1", name="ck_quota_requested_quota"
        ),
    )

    @property
    def allocation(self):
        return self.group.allocation

    def quota_dict(self):
        return {
            'zone': self.group.zone_id,
            'resource': self.resource.codename,
            'quota': self.quota,
            'requested_quota': self.requested_quota,
        }

    def __repr__(self):
        return f"<Quota {self.group_id} {self.resource_id}>"


class ChiefInvestigator(db.Model):
    __tablename__ = "chief_investigator"

    id = db.Column(db.Integer, primary_key=True)
    allocation_id = db.Column(
        db.Integer,
        db.ForeignKey("allocation_request.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = db.Column(db.String(60), nullable=False)
    given_name = db.Column(db.String(200), nullable=False)
    surname = db.Column(db.String(200), nullable=False)
    #: Institutional email address
    email = db.Column(db.String(254), nullable=False)
    primary_organisation_id = db.Column(
        db.Integer, db.ForeignKey("organisation.id"), nullable=True
    )
    #: Other primary investigators, partner investigators and collaborators
    additional_researchers = db.Column(
        base.LongText, nullable=False, default=""
    )

    allocation = db.relationship(
        AllocationRequest, back_populates="investigators"
    )
    primary_organisation = db.relationship(
        org_models.Organisation, lazy="joined"
    )

    def __repr__(self):
        return f"<ChiefInvestigator {self.title} {self.given_name} {self.surname}>"


class Publication(db.Model):
    """A research output.

    Only 'Peer reviewed journal article' (AJ) publications need to be
    reported to NCRIS. Unspecified (U) should not be used for new ones.
    """

    __tablename__ = "publication"

    id = db.Column(db.Integer, primary_key=True)
    allocation_id = db.Column(
        db.Integer,
        db.ForeignKey("allocation_request.id", ondelete="CASCADE"),
        nullable=False,
    )
    output_type = db.Column(db.String(2), nullable=False)
    #: Details of the research output (not for outputs with DOIs)
    publication = db.Column(db.String(512), nullable=False, default="")
    #: Required for 'AJ' publications for NCRIS
    doi = db.Column(db.String(256), nullable=False, default="")
    #: Cached JSON of the CrossRef lookup for the DOI
    crossref_metadata = db.Column(base.LongText, nullable=False, default="")

    allocation = db.relationship(
        AllocationRequest, back_populates="publications"
    )

    def __repr__(self):
        return f"<Publication {self.id}>"


class Grant(db.Model):
    __tablename__ = "grant"

    id = db.Column(db.Integer, primary_key=True)
    allocation_id = db.Column(
        db.Integer,
        db.ForeignKey("allocation_request.id", ondelete="CASCADE"),
        nullable=False,
    )
    grant_type = db.Column(db.String(128), nullable=False)
    grant_subtype = db.Column(db.String(128), nullable=False)
    #: Other funding source details
    funding_body_scheme = db.Column(db.String(255), nullable=False, default="")
    grant_id = db.Column(db.String(200), nullable=False, default="")
    first_year_funded = db.Column(db.Integer, nullable=False)
    last_year_funded = db.Column(db.Integer, nullable=False)
    #: Total funding amount in AUD
    total_funding = db.Column(db.Float, nullable=False)

    allocation = db.relationship(AllocationRequest, back_populates="grants")

    __table_args__ = (
        db.UniqueConstraint(
            "allocation_id",
            "grant_type",
            "grant_subtype",
            "funding_body_scheme",
            "grant_id",
            "first_year_funded",
            "total_funding",
            name="uq_grant_dedup",
        ),
    )

    def __repr__(self):
        return f"<Grant {self.id} {self.grant_type}/{self.grant_subtype}>"

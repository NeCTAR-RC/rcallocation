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

"""Allocation request schemas.

Dump schemas reproduce the three DRF serializers (public, user, admin).
Load schemas split the same way: users may only set the request fields,
admins (and approvers) the administrative ones as well. The old API
silently ignored read-only and unknown input keys, so do these.
"""

import marshmallow as ma

from rcallocation.api.v1.schemas import base
from rcallocation.api.v1.schemas import fields
from rcallocation import choices
from rcallocation import forcodes


USERS_MIN_ERROR = "The estimated number of users must be greater than 0"
COUNT_MIN_ERROR = "The estimated number cannot be less than 0"
YEAR_ERROR = "Please input a year between 1970 ~ 3000"


def _users(**kwargs):
    return base.IntOrDigits(
        allow_none=True,
        validate=ma.validate.Range(min=1, error=USERS_MIN_ERROR),
        **kwargs,
    )


def _count(**kwargs):
    return base.IntOrDigits(
        allow_none=True,
        validate=ma.validate.Range(min=0, error=COUNT_MIN_ERROR),
        **kwargs,
    )


def _for_choice():
    return base.choice(list(forcodes.FOR_CODES_ALL) + [""])


def _codes(choice_pairs):
    return [code for code, _ in choice_pairs]


# ---------------------------------------------------------------------------
# dump schemas
# ---------------------------------------------------------------------------


class PublicAllocationSchema(base.BaseSchema):
    """What an unauthenticated caller sees."""

    id = ma.fields.Integer()
    project_name = ma.fields.String()
    project_description = ma.fields.String()
    modified_time = base.DRFDateTime()
    submit_date = base.DRFDateTime()
    start_date = ma.fields.Date()
    end_date = ma.fields.Date()
    bundle = fields.BundleField()
    field_of_research_1 = ma.fields.String()
    field_of_research_2 = ma.fields.String()
    field_of_research_3 = ma.fields.String()
    for_percentage_1 = ma.fields.Integer()
    for_percentage_2 = ma.fields.Integer()
    for_percentage_3 = ma.fields.Integer()
    supported_organisations = fields.ManyLookupField(
        fields.OrganisationField()
    )
    quotas = ma.fields.Method("get_quotas")

    def get_quotas(self, obj):
        return obj.quota_list()


class AllocationSchema(PublicAllocationSchema):
    """What an authenticated caller sees (the old AllocationSerializer)."""

    status_display = ma.fields.String()
    chief_investigator = ma.fields.String(attribute="chief_investigator_email")
    allocation_home = ma.fields.String()
    allocation_home_display = ma.fields.String()
    associated_site = fields.AssociatedSiteField()
    usage_types = fields.ManyLookupField(fields.UsageTypeField())
    ardc_support = fields.ManyLookupField(fields.ARDCSupportField())
    ncris_facilities = fields.ManyLookupField(fields.NCRISFacilityField())
    parent_request = ma.fields.Integer(attribute="parent_request_id")
    status = ma.fields.String()
    contact_email = ma.fields.String()
    estimated_project_duration = ma.fields.Integer()
    convert_trial_project = ma.fields.Boolean()
    approver_email = ma.fields.String()
    use_case = ma.fields.String()
    usage_patterns = ma.fields.String()
    geographic_requirements = ma.fields.String()
    project_id = ma.fields.String()
    estimated_number_users = ma.fields.Integer()
    direct_access_user_estimate = ma.fields.Integer()
    estimated_service_count = ma.fields.Integer()
    estimated_service_active_users = ma.fields.Integer()
    multiple_allocations_check = ma.fields.Boolean()
    direct_access_user_past_year = ma.fields.Integer()
    active_service_count = ma.fields.Integer()
    service_active_users_past_year = ma.fields.Integer()
    users_figure_type = ma.fields.String()
    has_sensitive_data = ma.fields.String()
    data_classification_level = ma.fields.String()
    institutional_data_review = ma.fields.String()
    nectar_support = ma.fields.String()
    ardc_explanation = ma.fields.String()
    ncris_support = ma.fields.String()
    ncris_explanation = ma.fields.String()
    national = ma.fields.Boolean()
    special_approval = ma.fields.String()
    provisioned = ma.fields.Boolean()
    notifications = ma.fields.Boolean()
    managed = ma.fields.Boolean()
    nectar_benefit_description = ma.fields.String()
    nectar_research_impact = ma.fields.String()
    su_budget = ma.fields.Integer()


class AdminAllocationSchema(AllocationSchema):
    notes = ma.fields.String()
    status_explanation = ma.fields.String()


class ApproverInfoSchema(base.BaseSchema):
    approval_urgency = ma.fields.String()
    expiry_state = ma.fields.String()
    concerned_sites = ma.fields.List(ma.fields.String())


class CheckSchema(base.BaseSchema):
    code = ma.fields.String()
    message = ma.fields.String()


class ChecksSchema(base.BaseSchema):
    warnings = ma.fields.List(ma.fields.Nested(CheckSchema))
    nags = ma.fields.List(ma.fields.Nested(CheckSchema))


# ---------------------------------------------------------------------------
# nested write schemas
# ---------------------------------------------------------------------------


class QuotaValueSchema(base.BaseSchema):
    """One quota value: ``{zone, resource, requested_quota | quota}``.

    ``resource`` is a codename (``compute.cores``) or a resource id.
    """

    zone = ma.fields.String(required=True)
    resource = ma.fields.Raw(required=True)
    quota = base.IntOrDigits(validate=base.min_value(-1))
    requested_quota = base.IntOrDigits(validate=base.min_value(-1))


class NestedInvestigatorSchema(base.BaseSchema):
    id = base.IntOrDigits(allow_none=True)
    title = ma.fields.String(required=True, validate=base.max_length(60))
    given_name = ma.fields.String(required=True, validate=base.max_length(200))
    surname = ma.fields.String(required=True, validate=base.max_length(200))
    email = ma.fields.Email(required=True)
    primary_organisation = fields.PrimaryOrganisationField(allow_none=True)
    additional_researchers = ma.fields.String(validate=base.max_length(1000))


def _doi_ok(value):
    return value == "" or base.DOI_PATTERN.match(value) is not None


class NestedPublicationSchema(base.BaseSchema):
    id = base.IntOrDigits(allow_none=True)
    output_type = ma.fields.String(
        required=True, validate=base.choice(choices.OUTPUT_TYPES)
    )
    publication = ma.fields.String(validate=base.max_length(512))
    doi = ma.fields.String(validate=base.max_length(256))
    crossref_metadata = ma.fields.String()

    @ma.validates("doi")
    def validate_doi(self, value, **kwargs):
        if not _doi_ok(value):
            raise ma.ValidationError(base.doi().error)


class NestedGrantSchema(base.BaseSchema):
    id = base.IntOrDigits(allow_none=True)
    grant_type = ma.fields.String(
        required=True, validate=base.choice(_codes(choices.GRANT_TYPES))
    )
    grant_subtype = ma.fields.String(
        required=True, validate=base.choice(_codes(choices.GRANT_SUBTYPES))
    )
    funding_body_scheme = ma.fields.String(validate=base.max_length(255))
    grant_id = ma.fields.String(validate=base.max_length(200))
    first_year_funded = base.IntOrDigits(
        required=True,
        validate=ma.validate.Range(min=1970, max=3000, error=YEAR_ERROR),
    )
    last_year_funded = base.IntOrDigits(
        required=True,
        validate=ma.validate.Range(min=1970, max=3000, error=YEAR_ERROR),
    )
    total_funding = ma.fields.Float(required=True, validate=base.min_value(1))


class NestedWritesMixin:
    quotas = ma.fields.List(ma.fields.Nested(QuotaValueSchema))
    investigators = ma.fields.List(ma.fields.Nested(NestedInvestigatorSchema))
    grants = ma.fields.List(ma.fields.Nested(NestedGrantSchema))
    publications = ma.fields.List(ma.fields.Nested(NestedPublicationSchema))
    ignore_warnings = ma.fields.Boolean(load_default=True)


# ---------------------------------------------------------------------------
# load schemas
# ---------------------------------------------------------------------------


class AllocationUserWriteSchema(base.BaseSchema):
    """Fields a requester may set (old AllocationSerializer writable set).

    ``allocation_home`` and ``associated_site`` are accepted here so that
    a non-admin setting them gets the 403 the old API produced.
    """

    project_name = ma.fields.String(
        allow_none=True, validate=base.max_length(64)
    )
    project_description = ma.fields.String(
        required=True, validate=[base.not_blank(), base.max_length(200)]
    )
    estimated_project_duration = base.IntOrDigits(
        validate=base.choice(choices.DURATIONS)
    )
    convert_trial_project = ma.fields.Boolean()
    use_case = ma.fields.String(
        required=True, validate=[base.not_blank(), base.max_length(4096)]
    )
    usage_patterns = ma.fields.String(validate=base.max_length(1024))
    geographic_requirements = ma.fields.String(validate=base.max_length(1024))
    direct_access_user_estimate = _users()
    estimated_service_count = _count()
    estimated_service_active_users = _users()
    multiple_allocations_check = ma.fields.Boolean(allow_none=True)
    direct_access_user_past_year = _users()
    active_service_count = _count()
    service_active_users_past_year = _users()
    users_figure_type = ma.fields.String(
        allow_none=True, validate=base.choice(_codes(choices.OPTION_CHOICES))
    )
    has_sensitive_data = ma.fields.String(
        allow_none=True,
        validate=base.choice(_codes(choices.SENSITIVE_DATA_CHOICES)),
    )
    data_classification_level = ma.fields.String(
        allow_none=True,
        validate=base.choice(_codes(choices.DATA_CLASSIFICATION_CHOICES)),
    )
    institutional_data_review = ma.fields.String(
        allow_none=True,
        validate=base.choice(_codes(choices.INSTITUTIONAL_REVIEW_CHOICES)),
    )
    field_of_research_1 = ma.fields.String(
        allow_none=True, validate=_for_choice()
    )
    field_of_research_2 = ma.fields.String(
        allow_none=True, validate=_for_choice()
    )
    field_of_research_3 = ma.fields.String(
        allow_none=True, validate=_for_choice()
    )
    for_percentage_1 = base.IntOrDigits(
        validate=base.choice(choices.PERCENTAGES)
    )
    for_percentage_2 = base.IntOrDigits(
        validate=base.choice(choices.PERCENTAGES)
    )
    for_percentage_3 = base.IntOrDigits(
        validate=base.choice(choices.PERCENTAGES)
    )
    nectar_support = ma.fields.String(validate=base.max_length(255))
    ardc_support = fields.ManyLookupField(fields.ARDCSupportField())
    ardc_explanation = ma.fields.String(validate=base.max_length(1024))
    ncris_support = ma.fields.String(validate=base.max_length(255))
    ncris_explanation = ma.fields.String(validate=base.max_length(1024))
    ncris_facilities = fields.ManyLookupField(fields.NCRISFacilityField())
    usage_types = fields.ManyLookupField(fields.UsageTypeField())
    supported_organisations = fields.ManyLookupField(
        fields.OrganisationField()
    )
    bundle = fields.BundleField(allow_none=True)
    nectar_benefit_description = ma.fields.String(
        allow_none=True, validate=base.max_length(4096)
    )
    nectar_research_impact = ma.fields.String(
        allow_none=True, validate=base.max_length(4096)
    )
    allocation_home = fields.AllocationHomeField()
    associated_site = fields.AssociatedSiteField(allow_none=True)

    @ma.validates("supported_organisations")
    def validate_supported_organisations(self, value, **kwargs):
        if len(value) > 1:
            for org in value:
                if org.full_name == choices.ORG_ALL_FULL_NAME:
                    raise ma.ValidationError(
                        "'All Organisations' cannot be used in this context"
                    )
            if len({org.id for org in value}) != len(value):
                raise ma.ValidationError("Duplicate organisations")


class AllocationAdminWriteSchema(AllocationUserWriteSchema):
    """Admin writable set (old AdminAllocationSerializer).

    ``status``, ``approver_email``, ``parent_request``, ``created_by``
    and the timestamps are never writable.
    """

    status_explanation = ma.fields.String(allow_none=True)
    notes = ma.fields.String(allow_none=True)
    contact_email = ma.fields.Email()
    start_date = ma.fields.Date(allow_none=True)
    end_date = ma.fields.Date(allow_none=True)
    project_id = ma.fields.String(
        allow_none=True, validate=base.max_length(36)
    )
    provisioned = ma.fields.Boolean()
    notifications = ma.fields.Boolean()
    managed = ma.fields.Boolean()
    national = ma.fields.Boolean()
    special_approval = ma.fields.String(validate=base.max_length(1024))


class AllocationUserSubmitSchema(NestedWritesMixin, AllocationUserWriteSchema):
    """Create, submit and amend bodies for requesters."""


class AllocationAdminSubmitSchema(
    NestedWritesMixin, AllocationAdminWriteSchema
):
    """Create, submit and amend bodies for admins and approvers."""


class AllocationApproveSchema(base.BaseSchema):
    """Optional changes applied atomically with an approval."""

    status_explanation = ma.fields.String(allow_none=True)
    associated_site = fields.AssociatedSiteField(allow_none=True)
    national = ma.fields.Boolean()
    special_approval = ma.fields.String(validate=base.max_length(1024))
    bundle = fields.BundleField(allow_none=True)
    estimated_project_duration = base.IntOrDigits(
        validate=base.choice(choices.DURATIONS)
    )
    start_date = ma.fields.Date(allow_none=True)
    end_date = ma.fields.Date(allow_none=True)
    notes = ma.fields.String(allow_none=True)
    quotas = ma.fields.List(ma.fields.Nested(QuotaValueSchema))
    ignore_warnings = ma.fields.Boolean(load_default=True)


class AllocationDeclineSchema(base.BaseSchema):
    status_explanation = ma.fields.String(allow_none=True)
    #: Alias accepted for convenience
    reason = ma.fields.String(allow_none=True)

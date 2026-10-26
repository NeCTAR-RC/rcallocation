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

"""oslo.policy rules for the allocation API.

Project-scoped tokens gain elevated access only through the dedicated
``allocationadmin`` and ``allocationapprover`` roles; the generic keystone
``admin`` role on a project grants nothing. System-scoped ``admin`` and
``reader`` tokens are honoured as before.

Ownership targets carry ``contact_email`` (matched against the keystone
username) and ``is_owner`` (computed by the view from the caller's project
and tenantmanager projects). Allocation state checks (a request must be
pending to be approved, for example) are enforced in the views, not here.
"""

from oslo_policy import _checks
from oslo_policy import policy


class IsAuthenticatedCheck(_checks.Check):
    """``is_authenticated:True`` passes for any caller with a user id."""

    def __call__(self, target, creds, enforcer, current_rule=None):
        wanted = str(self.match).lower() == "true"
        return bool(creds.get("user_id")) == wanted


policy.register("is_authenticated", IsAuthenticatedCheck)


ADMIN = "admin"
APPROVER = "approver"
WRITE_ADMIN = "write_admin"
SYSTEM_READER = "system_reader"
READ_ADMIN = "read_admin"
AUTHENTICATED = "authenticated"
OWNER = "owner"
ADMIN_OR_OWNER = "admin_or_owner"
APPROVER_OR_OWNER = "approver_or_owner"
WRITE_ADMIN_OR_OWNER = "write_admin_or_owner"
OWNER_OR_READ_ADMIN = "owner_or_read_admin"
PUBLIC = "public"

SCOPE_SYSTEM_PROJECT = ["system", "project"]

base_rules = [
    policy.RuleDefault(
        name=ADMIN,
        check_str="role:allocationadmin or (role:admin and system_scope:all)",
        description="Allocation administrators: full read and write "
        "access to everything except approving requests.",
    ),
    policy.RuleDefault(
        name=APPROVER,
        check_str="role:allocationapprover",
        description="Allocation approvers: may approve and decline requests.",
    ),
    policy.RuleDefault(
        name=WRITE_ADMIN,
        check_str=f"rule:{ADMIN} or rule:{APPROVER}",
        description="Callers who may set administrative fields.",
    ),
    policy.RuleDefault(
        name=SYSTEM_READER,
        check_str="role:reader and system_scope:all",
        description="System-scoped read-only access.",
    ),
    policy.RuleDefault(
        name=READ_ADMIN,
        check_str=f"rule:{WRITE_ADMIN} or rule:{SYSTEM_READER}",
        description="Callers who may read every allocation with the "
        "administrative field set.",
    ),
    policy.RuleDefault(
        name=AUTHENTICATED,
        check_str="is_authenticated:True",
        description="Any caller presenting a valid token.",
    ),
    policy.RuleDefault(
        name=OWNER,
        check_str="user_name:%(contact_email)s or 'True':%(is_owner)s",
        description="The allocation's contact, or a member of its project "
        "(or of a project the caller manages).",
    ),
    policy.RuleDefault(
        name=ADMIN_OR_OWNER,
        check_str=f"rule:{ADMIN} or rule:{OWNER}",
    ),
    policy.RuleDefault(
        name=APPROVER_OR_OWNER,
        check_str=f"rule:{APPROVER} or rule:{OWNER}",
    ),
    policy.RuleDefault(
        name=WRITE_ADMIN_OR_OWNER,
        check_str=f"rule:{WRITE_ADMIN} or rule:{OWNER}",
    ),
    policy.RuleDefault(
        name=OWNER_OR_READ_ADMIN,
        check_str=f"rule:{READ_ADMIN} or rule:{OWNER}",
    ),
    policy.RuleDefault(
        name=PUBLIC,
        check_str="",
        description="Anyone, including unauthenticated callers.",
    ),
]


def _rule(prefix, action, check, description, operations):
    return policy.DocumentedRuleDefault(
        name=prefix % action,
        check_str=check,
        scope_types=SCOPE_SYSTEM_PROJECT,
        description=description,
        operations=operations,
    )


def _ops(path, *methods):
    return [{"path": path, "method": m} for m in methods]


VERSIONS_PREFIX = "rcallocation:versions:%s"
versions_rules = [
    _rule(
        VERSIONS_PREFIX,
        "list",
        f"rule:{PUBLIC}",
        "List API versions.",
        _ops("/v1/versions/", "GET"),
    ),
]


ALLOCATION_PREFIX = "rcallocation:allocation:%s"
_A = "/v1/allocations/"
_AI = "/v1/allocations/{allocation_id}/"
allocation_rules = [
    _rule(
        ALLOCATION_PREFIX,
        "list",
        f"rule:{PUBLIC}",
        "List allocations. Unauthenticated callers get the public field "
        "set; others see their own and their projects' allocations.",
        _ops(_A, "GET"),
    ),
    _rule(
        ALLOCATION_PREFIX,
        "list:all",
        f"rule:{READ_ADMIN}",
        "See every allocation with the administrative field set.",
        _ops(_A, "GET"),
    ),
    _rule(
        ALLOCATION_PREFIX,
        "get",
        f"rule:{PUBLIC}",
        "Show an allocation.",
        _ops(_AI, "GET"),
    ),
    _rule(
        ALLOCATION_PREFIX,
        "create",
        f"rule:{AUTHENTICATED}",
        "Create an allocation request.",
        _ops(_A, "POST"),
    ),
    _rule(
        ALLOCATION_PREFIX,
        "update",
        f"rule:{WRITE_ADMIN_OR_OWNER}",
        "Update a pending allocation request without recording history.",
        _ops(_AI, "PUT", "PATCH"),
    ),
    _rule(
        ALLOCATION_PREFIX,
        "submit",
        f"rule:{WRITE_ADMIN_OR_OWNER}",
        "Edit and (re)submit an allocation request, recording history.",
        _ops(_AI + "submit/", "POST"),
    ),
    _rule(
        ALLOCATION_PREFIX,
        "approve",
        f"rule:{APPROVER}",
        "Approve a pending allocation request.",
        _ops(_AI + "approve/", "POST"),
    ),
    _rule(
        ALLOCATION_PREFIX,
        "decline",
        f"rule:{APPROVER}",
        "Decline a pending allocation request.",
        _ops(_AI + "decline/", "POST"),
    ),
    _rule(
        ALLOCATION_PREFIX,
        "amend",
        f"rule:{WRITE_ADMIN_OR_OWNER}",
        "Request an amendment or extension of an approved allocation.",
        _ops(_AI + "amend/", "POST"),
    ),
    _rule(
        ALLOCATION_PREFIX,
        "delete",
        f"rule:{ADMIN}",
        "Mark an allocation as deleted.",
        _ops(_AI + "delete/", "POST"),
    ),
    _rule(
        ALLOCATION_PREFIX,
        "approver_info",
        f"rule:{READ_ADMIN}",
        "Show approval urgency and concerned sites.",
        _ops(_AI + "approver_info/", "GET"),
    ),
    _rule(
        ALLOCATION_PREFIX,
        "checks",
        f"rule:{OWNER_OR_READ_ADMIN}",
        "Run the advisory checks over an allocation.",
        _ops(_AI + "checks/", "GET"),
    ),
]


QUOTA_PREFIX = "rcallocation:quota:%s"
quota_rules = [
    _rule(
        QUOTA_PREFIX,
        "list",
        f"rule:{PUBLIC}",
        "List quotas.",
        _ops("/v1/quotas/", "GET"),
    ),
    _rule(
        QUOTA_PREFIX,
        "list:all",
        f"rule:{READ_ADMIN}",
        "See every quota.",
        _ops("/v1/quotas/", "GET"),
    ),
    _rule(
        QUOTA_PREFIX,
        "get",
        f"rule:{PUBLIC}",
        "Show a quota.",
        _ops("/v1/quotas/{quota_id}/", "GET"),
    ),
    _rule(
        QUOTA_PREFIX,
        "create",
        f"rule:{AUTHENTICATED}",
        "Add a quota to a pending allocation request.",
        _ops("/v1/quotas/", "POST"),
    ),
    _rule(
        QUOTA_PREFIX,
        "delete",
        f"rule:{WRITE_ADMIN_OR_OWNER}",
        "Remove a quota from a pending allocation request.",
        _ops("/v1/quotas/{quota_id}/", "DELETE"),
    ),
]


def _reference_rules(prefix, path, name, list_check, write_check):
    item = path + "{id}/"
    return [
        _rule(prefix, "list", list_check, f"List {name}.", _ops(path, "GET")),
        _rule(prefix, "get", list_check, f"Show a {name}.", _ops(item, "GET")),
        _rule(
            prefix,
            "create",
            write_check,
            f"Create a {name}.",
            _ops(path, "POST"),
        ),
        _rule(
            prefix,
            "update",
            write_check,
            f"Update a {name}.",
            _ops(item, "PUT", "PATCH"),
        ),
    ]


SITE_PREFIX = "rcallocation:site:%s"
ZONE_PREFIX = "rcallocation:zone:%s"
SERVICE_TYPE_PREFIX = "rcallocation:service_type:%s"
RESOURCE_PREFIX = "rcallocation:resource:%s"
BUNDLE_PREFIX = "rcallocation:bundle:%s"
NCRIS_FACILITY_PREFIX = "rcallocation:ncris_facility:%s"
ARDC_SUPPORT_PREFIX = "rcallocation:ardc_support:%s"
USAGE_TYPE_PREFIX = "rcallocation:usage_type:%s"
APPROVER_PREFIX = "rcallocation:approver:%s"

reference_rules = (
    _reference_rules(
        SITE_PREFIX, "/v1/sites/", "site", f"rule:{PUBLIC}", f"rule:{ADMIN}"
    )
    + _reference_rules(
        ZONE_PREFIX, "/v1/zones/", "zone", f"rule:{PUBLIC}", f"rule:{ADMIN}"
    )
    + _reference_rules(
        SERVICE_TYPE_PREFIX,
        "/v1/service-types/",
        "service type",
        f"rule:{PUBLIC}",
        f"rule:{ADMIN}",
    )
    + _reference_rules(
        RESOURCE_PREFIX,
        "/v1/resources/",
        "resource",
        f"rule:{PUBLIC}",
        f"rule:{ADMIN}",
    )
    + _reference_rules(
        BUNDLE_PREFIX,
        "/v1/bundles/",
        "bundle",
        f"rule:{PUBLIC}",
        f"rule:{ADMIN}",
    )
    + _reference_rules(
        NCRIS_FACILITY_PREFIX,
        "/v1/ncris-facilities/",
        "NCRIS facility",
        f"rule:{PUBLIC}",
        f"rule:{ADMIN}",
    )
    + _reference_rules(
        ARDC_SUPPORT_PREFIX,
        "/v1/ardc-projects/",
        "ARDC support program or project",
        f"rule:{PUBLIC}",
        f"rule:{ADMIN}",
    )
    + _reference_rules(
        USAGE_TYPE_PREFIX,
        "/v1/usage-types/",
        "usage type",
        f"rule:{PUBLIC}",
        f"rule:{ADMIN}",
    )
    + _reference_rules(
        APPROVER_PREFIX,
        "/v1/approvers/",
        "approver",
        f"rule:{READ_ADMIN}",
        f"rule:{ADMIN}",
    )
)


ORGANISATION_PREFIX = "rcallocation:organisation:%s"
organisation_rules = _reference_rules(
    ORGANISATION_PREFIX,
    "/v1/organisations/",
    "organisation",
    f"rule:{PUBLIC}",
    f"rule:{ADMIN}",
) + [
    _rule(
        ORGANISATION_PREFIX,
        "propose",
        f"rule:{AUTHENTICATED}",
        "Propose a new organisation for vetting.",
        _ops("/v1/organisations/", "POST"),
    ),
    _rule(
        ORGANISATION_PREFIX,
        "vet",
        f"rule:{ADMIN}",
        "Approve or decline a proposed organisation.",
        _ops("/v1/organisations/{id}/approve/", "POST")
        + _ops("/v1/organisations/{id}/decline/", "POST"),
    ),
]


def _related_rules(prefix, path, name):
    item = path + "{id}/"
    return [
        _rule(
            prefix,
            "list",
            f"rule:{AUTHENTICATED}",
            f"List {name}s of the caller's allocations.",
            _ops(path, "GET"),
        ),
        _rule(
            prefix,
            "list:all",
            f"rule:{READ_ADMIN}",
            f"List every {name}.",
            _ops(path, "GET"),
        ),
        _rule(
            prefix,
            "get",
            f"rule:{AUTHENTICATED}",
            f"Show a {name}.",
            _ops(item, "GET"),
        ),
        _rule(
            prefix,
            "create",
            f"rule:{AUTHENTICATED}",
            f"Add a {name} to a pending allocation request.",
            _ops(path, "POST"),
        ),
        _rule(
            prefix,
            "update",
            f"rule:{WRITE_ADMIN_OR_OWNER}",
            f"Update a {name}.",
            _ops(item, "PUT", "PATCH"),
        ),
        _rule(
            prefix,
            "delete",
            f"rule:{WRITE_ADMIN_OR_OWNER}",
            f"Delete a {name}.",
            _ops(item, "DELETE"),
        ),
    ]


CHIEF_INVESTIGATOR_PREFIX = "rcallocation:chief_investigator:%s"
PUBLICATION_PREFIX = "rcallocation:publication:%s"
GRANT_PREFIX = "rcallocation:grant:%s"

related_rules = (
    _related_rules(
        CHIEF_INVESTIGATOR_PREFIX,
        "/v1/chiefinvestigators/",
        "chief investigator",
    )
    + _related_rules(PUBLICATION_PREFIX, "/v1/publications/", "publication")
    + _related_rules(GRANT_PREFIX, "/v1/grants/", "grant")
)


FOR_PREFIX = "rcallocation:for:%s"
for_rules = [
    _rule(
        FOR_PREFIX,
        "codes",
        f"rule:{PUBLIC}",
        "List Fields of Research codes.",
        _ops("/v1/for-codes/", "GET")
        + _ops("/v1/for-codes-2008/", "GET")
        + _ops("/v1/for-codes-2020/", "GET")
        + _ops("/v1/for-codes-all/", "GET"),
    ),
    _rule(
        FOR_PREFIX,
        "tree",
        f"rule:{PUBLIC}",
        "Show active allocations aggregated by Field of Research.",
        _ops("/v1/for-tree/", "GET")
        + _ops("/v1/for-tree-2008/", "GET")
        + _ops("/v1/for-tree-2020/", "GET")
        + _ops("/v1/for-tree-all/", "GET"),
    ),
]


def list_rules():
    return (
        base_rules
        + versions_rules
        + allocation_rules
        + quota_rules
        + reference_rules
        + organisation_rules
        + related_rules
        + for_rules
    )

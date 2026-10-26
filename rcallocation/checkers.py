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

"""Advisory checks run over an allocation request.

``QuotaSanityChecker`` produces warnings for approvers (storage requested
outside the approving site, unjustified flavours, unvetted organisations,
no current grants). ``NagChecker`` produces reminders for users renewing
an allocation. Each check returns a ``(code, message)`` tuple or a list
of them; the codes are stable strings used as anchors in the support
documentation.

The checkers read a flat ``values`` mapping (field names plus
``quota-<codename>__<zone>`` keys for quota values) falling back to the
allocation record, so they can run on proposed values before they are
saved as well as on stored records.
"""

from datetime import datetime

from oslo_log import log as logging

from rcallocation import choices
from rcallocation.common import config
from rcallocation.extensions import db
from rcallocation import forcodes
from rcallocation import models
from rcallocation import utils


LOG = logging.getLogger(__name__)


# The following warning code strings will used as anchors in the
# support page that contains "more information" about the errors.
# The values should be stable and unique.
CINDER_NOT_LOCAL = 'CINDER_NOT_LOCAL'
MANILA_NOT_LOCAL = 'MANILA_NOT_LOCAL'
FLAVORS_NOT_JUSTIFIED = 'FLAVORS_NOT_JUSTIFIED'
APPROVER_PROBLEM = 'APPROVER_PROBLEM'
APPROVER_NOT_AUTHORIZED = 'APPROVER_NOT_AUTHORIZED'
APPROVER_DISABLED_ORGANISATION = 'APPROVER_DISABLED_ORGANISATION'
APPROVER_UNVETTED_ORGANISATION = 'APPROVER_UNVETTED_ORGANISATION'
NO_VALID_GRANTS = 'NO_VALID_GRANTS'
REENTER_FOR_CODES = 'REENTER_FOR_CODES'
DATA_SENSITIVITY = 'DATA_SENSITIVITY'
NO_PUBLICATIONS = 'NO_PUBLICATIONS'


def quota_key(codename, zone):
    return f'quota-{codename}__{zone}'


def storage_zone_to_home(zone):
    mappings = config.get_mappings().home_storage_zones
    for home, zones in mappings.items():
        if zone in zones:
            return home
    return None


def get_foreign_zones(associated_sites):
    zones = set(name for (name,) in db.session.query(models.Zone.name).all())
    mappings = config.get_mappings().home_storage_zones
    for site in associated_sites:
        home_zones = set(mappings.get(site.name, []))
        zones -= home_zones
    return zones


def cinder_local_check(context):
    if not context.approving:
        # These are approver-only checks.
        return None
    associated_site = context.get_field('associated_site')
    if associated_site:
        foreign_zones = get_foreign_zones([associated_site])
        for zone in sorted(foreign_zones):
            q = context.get_field(quota_key('volume.gigabytes', zone))
            if not q or q == 0:
                continue
            national = context.get_field('national')
            return (
                CINDER_NOT_LOCAL,
                '{} approved {} allocation requests volume storage '
                'in {}'.format(
                    associated_site.name,
                    'national' if national else 'local',
                    zone,
                ),
            )
    return None


def manila_local_check(context):
    if not context.approving:
        # These are approver-only checks.
        return None
    associated_site = context.get_field('associated_site')
    if associated_site:
        foreign_zones = get_foreign_zones([associated_site])
        for zone in sorted(foreign_zones):
            q = context.get_field(quota_key('share.shares', zone))
            if not q or q == 0:
                continue
            national = context.get_field('national')
            return (
                MANILA_NOT_LOCAL,
                '{} approved {} allocation requests shares in {}'.format(
                    associated_site.name,
                    'national' if national else 'local',
                    zone,
                ),
            )
    return None


def flavor_check(context):
    bundle = context.get_field('bundle')
    if bundle:
        return None
    huge_ram = context.get_field(
        quota_key('compute.flavor:hugeram-v3', 'nectar')
    )
    if huge_ram and not context.get_field('usage_patterns'):
        return (
            FLAVORS_NOT_JUSTIFIED,
            'Requests for access to special flavors must be explained '
            'in the "Justification ..." field.',
        )
    return None


def approver_checks(context):
    if context.user_name is None or not context.approving:
        return None
    sites = utils.sites_for_approver(context.user_name)
    if len(sites) == 0:
        return (
            APPROVER_PROBLEM,
            'Problem with approver registration: contact Core Services',
        )

    other_zones = set()
    foreign_zones = get_foreign_zones(sites)
    for zone in foreign_zones:
        for codename in ['volume.gigabytes', 'share.shares']:
            q = context.get_field(quota_key(codename, zone))
            if q and q > 0:
                other_zones.add(zone)

    return [
        (
            APPROVER_NOT_AUTHORIZED,
            f"""Quota should be authorized by the other site before
             approving '{z}' storage quota""",
        )
        for z in sorted(other_zones)
    ]


def grant_checks(context):
    if not context.approving:
        # These are approver-only checks.  When we look at the form
        # submitted by the user, there is not enough context to know
        # if warnings about grants, etc are relevant.
        return None

    this_year = datetime.now().year
    if (
        not context.get_field('national')
        or context.get_field('special_approval')
        or len(context.allocation.ardc_support)
        or len(context.allocation.ncris_facilities)
    ):
        return None
    for g in context.allocation.grants:
        if (
            g.grant_type in ('arc', 'nhmrc', 'mrff', 'comp', 'govt', 'rdc')
            and g.last_year_funded >= this_year
        ):
            return None
    return [
        (
            NO_VALID_GRANTS,
            "There are no current competitive grants for this request. "
            "Either approve it as Local, or add a Special approval reason.",
        )
    ]


def organisation_checks(context):
    if not context.approving:
        # These are approver-only checks.
        return None

    res = []

    def _check(org):
        if org is None:
            return
        if not org.enabled:
            res.append(
                (
                    APPROVER_DISABLED_ORGANISATION,
                    "This allocation request is using an Organisation "
                    f"({org.full_name}) that has been disabled. Please"
                    "get the user to resubmit with another Organisation.",
                )
            )
        elif org.proposed_by and not org.vetted_by:
            res.append(
                (
                    APPROVER_UNVETTED_ORGANISATION,
                    "This allocation request is using an Organisation "
                    f"({org.full_name}) that has been proposed "
                    f"(by {org.proposed_by}) but not vetted. "
                    "Please get an Allocations Admin to vet it before "
                    "approving this request or amendment.",
                )
            )

    for o in context.allocation.supported_organisations:
        _check(o)
    for ci in context.allocation.investigators:
        _check(ci.primary_organisation)

    return res or None


class Checker:
    CHECKS = []

    def __init__(
        self, allocation=None, values=None, user_name=None, approving=False
    ):
        self.allocation = allocation
        self.values = values or {}
        self.user_name = user_name
        self.approving = approving

    def do_checks(self):
        res = []
        for check in self.CHECKS:
            info = check(self)
            # A check may return a tuple or a list of tuples
            if info:
                if isinstance(info, list):
                    res.extend(info)
                else:
                    res.append(info)
        return res

    def get_field(self, name):
        value = self.values.get(name)
        if value is None and self.allocation is not None:
            value = getattr(self.allocation, name, None)
        return value


class QuotaSanityChecker(Checker):
    CHECKS = [
        cinder_local_check,
        manila_local_check,
        flavor_check,
        approver_checks,
        organisation_checks,
        grant_checks,
    ]


NO_SURVEY = 'NO_SURVEY'
LEGACY_NCRIS = 'LEGACY_NCRIS'
LEGACY_ARDC = 'LEGACY_ARDC'
EXPIRED_GRANT = 'EXPIRED_GRANT'
UNSPECIFIED_OUTPUT = 'UNSPECIFIED_OUTPUT'
NO_CROSSREF = 'NO_CROSSREF'

# Grants that have expired this number of years ago are no longer
# relevant to allocation decisions.  Allocations ctty consensus is
# that 4 years is about right.
EXPIRED_GRANT_CUTOFF_YEARS = 4


def _count(value):
    if value is None:
        return 0
    return len(list(value))


def survey_check(checker):
    if _count(checker.get_field('usage_types')) == 0:
        return (NO_SURVEY, 'One or more "Usage Types" need to be selected.')
    return None


def ncris_check(checker):
    if (
        checker.get_field('ncris_support')
        and _count(checker.get_field('ncris_facilities')) == 0
    ):
        return (
            LEGACY_NCRIS,
            'The information that you previously entered for '
            'NCRIS support text box needs to be reviewed and '
            'reentered in the NCRIS facilities and details fields.',
        )
    return None


def ardc_check(checker):
    if (
        checker.get_field('nectar_support')
        and _count(checker.get_field('ardc_support')) == 0
    ):
        return (
            LEGACY_ARDC,
            'The information that you previously entered for '
            'Nectar support text box needs to be reentered in the '
            'ARDC support and details fields.',
        )
    return None


def grant_check(checker):
    if checker.allocation is None:
        return None
    cutoff = datetime.now().year - EXPIRED_GRANT_CUTOFF_YEARS
    if any(g.last_year_funded < cutoff + 1 for g in checker.allocation.grants):
        return (
            EXPIRED_GRANT,
            f'One or more of your listed research grants ended in {cutoff} or '
            'earlier. Old grants that are no longer relevant to '
            'allocation renewal assessment should be removed from the '
            'form.',
        )
    return None


def output_checks(checker):
    if checker.allocation is None:
        return []
    res = []
    publications = checker.allocation.publications
    if any(p.output_type == choices.UNSPECIFIED for p in publications):
        res.append(
            (
                UNSPECIFIED_OUTPUT,
                'One or more of the Publications / Outputs listed on the '
                'form needs to be reentered with a publication category '
                'and (if available) a DOI.  When you have done this, '
                'please delete the old entry.',
            )
        )
    if any(
        p.output_type == choices.PEER_REVIEWED_JOURNAL_ARTICLE
        and p.crossref_metadata == ""
        for p in publications
    ):
        res.append(
            (
                NO_CROSSREF,
                'One or more of your Publications has been entered as a '
                'peer-reviewed journal article, but it does not have a '
                'validated DOI.  Please reenter it.',
            )
        )
    return res


def for_check(checker):
    if checker.allocation is None:
        return None
    codes = forcodes.for_codes()
    for for_code in [
        checker.allocation.field_of_research_1,
        checker.allocation.field_of_research_2,
        checker.allocation.field_of_research_3,
    ]:
        if for_code and for_code not in codes:
            return [
                (
                    REENTER_FOR_CODES,
                    'This allocation request is using legacy Field of '
                    'Research (FoR) codes.  You will need to reenter the '
                    'FoR information using '
                    f'{forcodes.for_series().replace("_", " ")} codes.',
                )
            ]
    return None


def data_sensitivity_check(context):
    """Checks if a renewal request has 'not_sure' data classification.

    For renewal requests, the data classification level should be
    clearly specified and not 'not_sure'.
    """
    if context.allocation and context.allocation.can_have_publications():
        classification_level = context.get_field('data_classification_level')
        if classification_level == 'not_sure':
            return (
                DATA_SENSITIVITY,
                'This is a renewal request. The data sensitivity should be '
                'classified as Green, Yellow, Orange, or Red based on the '
                'Data Classification Framework.',
            )

    return None


def publications_check(context):
    """Remind renewing users to capture publications and impact statement."""
    if context.allocation and context.allocation.can_have_publications():
        return (
            NO_PUBLICATIONS,
            'Please provide an impact and benefit statement for your '
            'project. Also include any publications which have occurred '
            'since your last renewal. Providing this information supports '
            'the ongoing sustainability of the ARDC Nectar Research Cloud.',
        )
    return None


class NagChecker(Checker):
    CHECKS = [
        survey_check,
        ncris_check,
        ardc_check,
        grant_check,
        output_checks,
        for_check,
        data_sensitivity_check,
        publications_check,
    ]


def values_from_allocation(allocation):
    """Flat values for the checkers built from a stored allocation.

    Quota values use the allocated quota for approved allocations and the
    requested quota otherwise, as the dashboard's quota form initial values
    did. This holds when approving too: an approver checking a pending
    request evaluates the amounts asked for, not the allocated quota that
    has not been set yet.
    """
    values = {}
    use_allocated = allocation.status == choices.APPROVED
    for item in allocation.quota_list():
        key = quota_key(item['resource'], item['zone'])
        values[key] = (
            item['quota'] if use_allocated else item['requested_quota']
        )
    return values


def as_dicts(results):
    return [{"code": code, "message": message} for code, message in results]

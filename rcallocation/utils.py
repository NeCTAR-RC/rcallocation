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

from oslo_log import log as logging
import sqlalchemy as sa

from rcallocation.common import config
from rcallocation.extensions import db
from rcallocation import models


LOG = logging.getLogger(__name__)


def normalise_project_name(project_name):
    return project_name.lower().replace('_', '-')


def is_project_name_available(project_name, allocation=None):
    """True if no allocation (live, history or deleted) uses the name.

    Names compare case-insensitively with ``_`` and ``-`` treated as the
    same character. When ``allocation`` is given, that record and its
    history rows are excluded so a request can keep its own name.
    """
    if not project_name:
        return True
    Allocation = models.AllocationRequest
    normalised = sa.func.lower(
        sa.func.replace(Allocation.project_name, '_', '-')
    )
    query = db.session.query(Allocation.id).filter(
        normalised == normalise_project_name(project_name)
    )
    if allocation is not None and allocation.id is not None:
        query = query.filter(
            Allocation.id != allocation.id,
            sa.or_(
                Allocation.parent_request_id.is_(None),
                Allocation.parent_request_id != allocation.id,
            ),
        )
    return query.first() is None


def strip_email_sub_domains(domain):
    prefix = domain.split('.', 1)[0]
    if prefix in (
        'my',
        'ems',
        'exchange',
        'groupwise',
        'student',
        'students',
        'studentmail',
    ):
        _, _, domain = domain.partition('.')
        if domain == 'griffithuni.edu.au':
            return 'griffith.edu.au'
        if domain == 'waimr.uwa.edu.au':
            return 'uwa.edu.au'
        if domain == 'uni.sydney.edu.au':
            return 'sydney.edu.au'
        if domain == 'usyd.edu.au':
            return 'sydney.edu.au'
        if domain == 'myune.edu.au':
            return 'une.edu.au'
        if domain == 'aucklanduni.ac.nz':
            return 'auckland.ac.nz'
        if domain == 'data61.csiro.au':
            return 'csiro.au'
    return domain


def extract_email_domain(email_address):
    _, _, domain = email_address.partition('@')
    return domain


def institution_from_email(contact_email):
    email_domain = extract_email_domain(contact_email or '')
    domain = strip_email_sub_domains(email_domain)
    return domain


def get_member_map():
    """Email domain to the Site records whose members use that domain.

    Built from the ``site_members`` mapping (site name to domains) in the
    mappings file and the Site table.
    """
    res = {}
    sites = {s.name: s for s in db.session.query(models.Site).all()}
    for site_name, domains in config.get_mappings().site_members.items():
        site = sites.get(site_name)
        if site is None:
            LOG.error("Unknown site %s in site_members mapping", site_name)
            continue
        for domain in domains:
            res.setdefault(domain, []).append(site)
    return res


def sites_from_email(contact_email, member_map=None):
    domain = institution_from_email(contact_email)
    if member_map is None:
        member_map = get_member_map()
    return member_map.get(domain, [])


def sites_for_approver(username):
    """The sites an approver may approve for, logging problems."""
    approver = (
        db.session.query(models.Approver).filter_by(username=username).first()
    )
    if approver is None:
        LOG.warning("No Approver found for '%s'", username)
        return []
    sites = list(approver.sites)
    if len(sites) == 0:
        LOG.warning("Approver for '%s' has no associated sites", username)
    return sites


def get_interested_sites(allocation, member_map=None):
    """Get the list of Nectar sites for whom this request is
    relevant.  (This is a heuristic ... and may be refined)

    Pass a ``member_map`` from get_member_map when looking up many
    allocations so the Site table is read once.
    """
    if allocation.associated_site:
        return [allocation.associated_site]
    return sites_from_email(allocation.contact_email, member_map)

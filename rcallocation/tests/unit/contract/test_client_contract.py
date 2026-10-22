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

"""Contract tests: the unchanged python-nectarallocationclient must work.

Every manager method the client exposes is exercised against the service
through the real client code path.
"""

import datetime
import unittest

from nectarallocationclient import exceptions as client_exceptions
from nectarallocationclient import states
from nectarallocationclient.v1 import allocations

from rcallocation import choices
from rcallocation.extensions import db
from rcallocation import models
from rcallocation.tests.unit.api.v1 import common
from rcallocation.tests.unit.contract import harness
from rcallocation.tests.unit import factories


class ContractTestCase(common.AllocationApiTestCase):
    def setUp(self):
        super().setUp()
        self.c = harness.make_client(self.app)
        self.session = harness.make_session(self.app)


class TestAllocations(ContractTestCase):
    def test_list_and_pagination(self):
        for _ in range(3):
            factories.create_allocation(contact_email='other@example.com')
        self.as_admin()
        allocations = self.c.allocations.list()
        self.assertEqual(4, len(allocations))
        self.assertTrue(all(hasattr(a, 'quotas') for a in allocations))
        # The client follows "next" links page by page
        self.assertEqual(4, len(self.c.allocations.list(limit=1)))
        self.assertEqual(
            4, len(self.c.allocations.list(parent_request__isnull=True))
        )

    def test_get_current_and_last_approved(self):
        self.as_admin()
        approved = factories.create_allocation(
            status=choices.APPROVED, project_id='pid', project_name='on'
        )
        # History copies keep the older timestamp of the live record
        factories.create_allocation(
            parent_request_id=approved.id,
            status=choices.APPROVED,
            project_id='pid',
            modified_time=datetime.datetime(2020, 1, 1),
        )
        current = self.c.allocations.get_current(project_id='pid')
        self.assertEqual(approved.id, current.id)
        self.assertEqual('on', current.project_name)
        last = self.c.allocations.get_last_approved(project_id='pid')
        self.assertEqual(approved.id, last.id)
        self.assertEqual(states.APPROVED, last.status)

    def test_get_and_quota_helpers(self):
        self.as_user()
        allocation = self.c.allocations.get(self.allocation.id)
        self.assertEqual(self.allocation.id, allocation.id)
        self.assertEqual(10, len(allocation.quotas))
        self.assertEqual(
            {'compute.cores', 'compute.instances'},
            {q.resource for q in allocation.get_quota('compute')},
        )
        self.assertEqual('Submitted', allocation.status_display)
        self.assertEqual(
            {'budget': 0}, allocation.get_allocated_cloudkitty_quota()
        )

    def test_get_bundle_quotas(self):
        allocation = factories.create_allocation(
            bundle='gold',
            create_quotas=False,
            status=choices.APPROVED,
            contact_email=common.USER["user_name"],
        )
        self.as_user()
        fetched = self.c.allocations.get(allocation.id)
        self.assertEqual('gold', fetched.bundle)
        self.assertEqual(
            {'budget': 16000}, fetched.get_allocated_cloudkitty_quota()
        )
        nova = fetched.get_allocated_nova_quota()
        self.assertEqual(200, nova['cores'])

    def test_create_update_approve_amend_delete(self):
        self.as_user()
        created = self.c.allocations.create(
            project_name='client-proj',
            project_description='Made by the client',
            use_case='testing the client',
            estimated_project_duration=6,
            field_of_research_1='300101',
            for_percentage_1=100,
            supported_organisations=['https://ror.org/23456789'],
            bundle='silver',
            convert_trial_project=True,
            notifications=False,
            managed=True,
            national=False,
            associated_site=None,
        )
        self.assertEqual(states.SUBMITTED, created.status)
        self.assertEqual('client-proj', created.project_name)
        self.assertEqual('silver', created.bundle)
        self.assertEqual(common.USER["user_name"], created.contact_email)
        self.assertTrue(created.convert_trial_project)
        self.assertEqual(6, created.estimated_project_duration)
        self.assertEqual(
            {'budget': 4000}, created.get_allocated_cloudkitty_quota()
        )

        updated = self.c.allocations.update(
            created.id, use_case='changed', usage_patterns='lots'
        )
        self.assertEqual('changed', updated.use_case)

        self.as_approver()
        self.c.allocations.update(created.id, associated_site='qcif')
        approved = self.c.allocations.approve(created.id)
        self.assertEqual(states.APPROVED, approved.status)
        self.assertEqual('qcif', approved.associated_site)

        self.as_user()
        amended = self.c.allocations.amend(created.id)
        self.assertEqual(states.UPDATE_PENDING, amended.status)

        self.as_admin()
        info = self.c.allocations.get_approver_info(created.id)
        self.assertEqual(
            {'approval_urgency', 'expiry_state', 'concerned_sites'},
            set(info),
        )
        deleted = self.c.allocations.delete(created.id)
        self.assertEqual(states.DELETED, deleted.status)
        self.assertEqual(
            3,
            len(self.c.allocations.list(parent_request=created.id)),
        )

    def test_errors(self):
        self.as_user()
        self.assertRaises(
            client_exceptions.NotFound, self.c.allocations.get, 9999
        )
        self.assertRaises(
            client_exceptions.Forbidden,
            self.c.allocations.approve,
            self.allocation.id,
        )
        with self.assertRaises(client_exceptions.BadRequest) as ctx:
            self.c.allocations.create(
                project_name='x',
                project_description='x',
                use_case='x',
                bundle='bogus',
            )
        self.assertIn("Bundle 'bogus' does not exist", str(ctx.exception))
        self.as_anon()
        self.assertRaises(
            client_exceptions.Forbidden,
            self.c.allocations.update,
            self.allocation.id,
            use_case='x',
        )

    def test_filters_pass_through(self):
        self.as_admin()
        factories.create_allocation(
            contact_email='other@example.com', status=choices.APPROVED
        )
        self.assertEqual(1, len(self.c.allocations.list(status='A')))
        self.assertEqual(1, len(self.c.allocations.list(status__in='E,R')))
        self.assertEqual(
            1,
            len(self.c.allocations.list(contact_email__icontains='OTHER')),
        )


class TestQuotas(ContractTestCase):
    def test_quota_lifecycle(self):
        self.as_user()
        quotas = self.c.quotas.list(allocation=self.allocation.id)
        self.assertEqual(10, len(quotas))
        self.assertEqual(
            10,
            len(
                self.c.quotas.list(
                    allocation=self.allocation.id, zone='nectar'
                )
            )
            + len(
                self.c.quotas.list(
                    allocation=self.allocation.id, zone='melbourne'
                )
            )
            + len(
                self.c.quotas.list(
                    allocation=self.allocation.id, zone='monash'
                )
            ),
        )
        self.assertEqual(
            5,
            len(
                self.c.quotas.list(
                    allocation=self.allocation.id, service_type='network'
                )
            )
            + len(
                self.c.quotas.list(
                    allocation=self.allocation.id, service_type='object'
                )
            ),
        )
        ram = factories.get(
            models.Resource, quota_name='ram', service_type_id='compute'
        )
        quota = self.c.quotas.create(
            allocation=self.allocation.id,
            resource=ram.id,
            zone='nectar',
            quota=5,
            requested_quota=7,
        )
        self.assertEqual(ram.id, quota.resource)
        self.assertEqual(5, quota.quota)
        self.assertEqual(7, quota.requested_quota)
        self.assertEqual('nectar', quota.zone)
        self.assertEqual(self.allocation.id, quota.allocation)
        self.assertEqual(ram.id, self.c.quotas.get(quota.id).resource)
        self.c.quotas.delete(quota.id)
        self.assertRaises(
            client_exceptions.NotFound, self.c.quotas.get, quota.id
        )


class TestReferenceData(ContractTestCase):
    def test_zones(self):
        self.as_anon()
        zones = self.c.zones.list()
        self.assertEqual(7, len(zones))
        self.assertEqual('nectar', self.c.zones.get('nectar').name)
        homes = self.c.zones.compute_homes()
        self.assertEqual({'national', 'uom', 'monash', 'qcif'}, set(homes))
        self.as_admin()
        zone = self.c.zones.create(
            name='perth', display_name='Perth', enabled=True
        )
        self.assertEqual('Perth', zone.display_name)
        self.assertFalse(self.c.zones.update('perth', enabled=False).enabled)

    def test_service_types_and_resources(self):
        self.as_anon()
        compute = self.c.service_types.get('compute')
        self.assertEqual('compute', compute.catalog_name)
        self.assertEqual(
            ['cores', 'instances', 'ram'],
            [r.quota_name for r in compute.resources],
        )
        self.assertEqual(['nectar'], compute.zones)
        resources = self.c.resources.list()
        self.assertEqual(11, len(resources))
        cores = [r for r in resources if r.quota_name == 'cores'][0]
        self.assertEqual('compute', cores.service_type)
        self.assertEqual(cores.id, self.c.resources.get(cores.id).id)
        self.as_admin()
        st = self.c.service_types.create(
            catalog_name='dns',
            name='DNS',
            description='d',
            zones=['nectar'],
            notes='',
            order=9,
            experimental=False,
            location_specific=False,
        )
        self.assertEqual('dns', st.catalog_name)
        resource = self.c.resources.create(
            name='Zones',
            service_type='dns',
            quota_name='zones',
            unit='zones',
            requestable=True,
            resource_type='integer',
            help_text='',
        )
        self.assertEqual(
            'dns.zones', f'{resource.service_type}.{resource.quota_name}'
        )

    def test_sites_and_approvers(self):
        self.as_admin()
        sites = self.c.sites.list()
        self.assertEqual(4, len(sites))
        qcif = [s for s in sites if s.name == 'qcif'][0]
        site = self.c.sites.create(
            name='darwin', display_name='Darwin', enabled=True
        )
        self.assertEqual('darwin', site.name)
        approver = self.c.approvers.create(
            username='jim@example.com', display_name='Jim', sites=[qcif.id]
        )
        self.assertEqual([qcif.id], approver.sites)
        self.assertEqual(
            'Jimmy',
            self.c.approvers.update(
                approver.id, display_name='Jimmy'
            ).display_name,
        )
        self.assertEqual(4, len(self.c.approvers.list()))

    def test_bundles(self):
        self.as_anon()
        bundles = self.c.bundles.list()
        self.assertCountEqual(
            ['gold', 'silver', 'bronze'], [b.name for b in bundles]
        )
        gold = self.c.bundles.get(
            [b for b in bundles if b.name == 'gold'][0].id
        )
        self.assertEqual('nectar', gold.zone)
        self.assertEqual(9, len(gold.quotas))
        self.assertEqual('object.object', gold.quotas[0].resource)

    def test_facilities_and_projects(self):
        self.as_anon()
        facilities = self.c.facilities.list()
        self.assertEqual(22, len(facilities))
        ala = self.c.facilities.get(
            [f for f in facilities if f.short_name == 'ALA'][0].id
        )
        self.assertEqual('Atlas of Living Australia', ala.name)
        projects = self.c.ardc_projects.list(enabled=True)
        self.assertIn('CVL', [p.short_name for p in projects])


class TestOrganisationsAndRelated(ContractTestCase):
    def test_organisations(self):
        self.as_anon()
        orgs = self.c.organisations.list(
            ror_id__iexact='HTTPS://ROR.ORG/12345678'
        )
        self.assertEqual(1, len(orgs))
        self.assertEqual('QCIF', orgs[0].short_name)
        self.assertEqual(
            1,
            len(
                self.c.organisations.list(
                    full_name__iexact='monash university'
                )
            ),
        )
        self.as_admin()
        factories.create_approver(common.ADMIN["user_name"], "Admin")
        proposed = self.c.organisations.create(
            full_name='Proposed Uni',
            short_name='PU',
            url='https://pu.edu',
            country='AU',
            ror_id='',
            parent=None,
            precedes=[],
            proposed_by='someone',
            vetted_by=None,
            enabled=True,
        )
        self.assertEqual('someone', proposed.proposed_by)
        self.c.organisations.approve(proposed.id)
        approved = self.c.organisations.get(proposed.id)
        self.assertTrue(approved.enabled)
        self.assertIsNotNone(approved.vetted_by)
        self.c.organisations.decline(proposed.id)
        self.assertFalse(self.c.organisations.get(proposed.id).enabled)

    def test_investigators_publications_grants(self):
        self.as_user()
        ci = self.c.chiefinvestigators.create(
            allocation=self.allocation.id,
            title='Dr',
            given_name='Ada',
            surname='Lovelace',
            email='ada@example.com',
            primary_organisation='https://ror.org/23456789',
            additional_researchers='',
        )
        self.assertEqual('Ada', ci.given_name)
        self.assertEqual('https://ror.org/23456789', ci.primary_organisation)
        self.assertEqual(
            1,
            len(self.c.chiefinvestigators.list(allocation=self.allocation.id)),
        )
        self.assertEqual(
            'Adah',
            self.c.chiefinvestigators.update(
                ci.id, given_name='Adah'
            ).given_name,
        )
        self.c.chiefinvestigators.delete(ci.id)

        pub = self.c.publications.create(
            allocation=self.allocation.id,
            output_type='AJ',
            publication='',
            doi='10.1234/abc',
        )
        self.assertEqual('10.1234/abc', pub.doi)
        self.assertEqual(
            1, len(self.c.publications.list(allocation=self.allocation.id))
        )
        self.c.publications.delete(pub.id)

        grant = self.c.grants.create(
            allocation=self.allocation.id,
            grant_type='arc',
            grant_subtype='arc-discovery',
            first_year_funded=2024,
            last_year_funded=2026,
            total_funding=1000,
            funding_body_scheme='',
            grant_id='g1',
        )
        self.assertEqual('g1', grant.grant_id)
        self.assertEqual(
            1, len(self.c.grants.list(allocation=self.allocation.id))
        )
        self.c.grants.delete(grant.id)
        self.assertEqual(
            0, len(self.c.grants.list(allocation=self.allocation.id))
        )


class TestHiveContract(ContractTestCase):
    """What hive's AllocationsClient reads with a project-scoped token."""

    def test_project_allocation_summary(self):
        allocation = factories.create_allocation(
            contact_email='someone-else@example.com',
            project_id='idproj2',
            project_name='proj2',
            status=choices.APPROVED,
            bundle='bronze',
            create_quotas=False,
        )
        self.as_user2()
        response = self.session.get(
            harness.BASE_URL + '/allocations/?project_id=idproj2&status=A'
            '&parent_request__isnull=True',
            raise_exc=False,
        )
        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(1, body['count'])
        result = body['results'][0]
        for field in (
            'id',
            'project_id',
            'project_name',
            'status',
            'start_date',
            'end_date',
            'quotas',
        ):
            self.assertIn(field, result)
        self.assertEqual(allocation.id, result['id'])
        budget = [
            q for q in result['quotas'] if q['resource'] == 'rating.budget'
        ]
        self.assertEqual(4000, budget[0]['quota'])
        for quota in result['quotas']:
            self.assertEqual(
                {'zone', 'resource', 'quota', 'requested_quota'}, set(quota)
            )
        self.assertIsNone(
            db.session.get(
                models.AllocationRequest, allocation.id
            ).parent_request_id
        )


@unittest.skipUnless(
    hasattr(allocations.AllocationManager, 'submit'),
    "needs python-nectarallocationclient 2.2 or later",
)
class TestClientActions(ContractTestCase):
    """The additive methods of python-nectarallocationclient 2.2.

    These are what the converted dashboard relies on: nested writes,
    submit, decline, approve and amend with changes, checks, organisation
    search and usage types. Skipped with the 2.1 client pinned in
    test-requirements.txt; bump the pin once 2.2.0 is released.
    """

    INVESTIGATOR = {
        'title': 'Dr',
        'given_name': 'Ada',
        'surname': 'Lovelace',
        'email': 'ada@unimelb.edu.au',
        'primary_organisation': 'Monash',
    }

    def test_submit_with_nested_lists(self):
        self.as_user()
        submitted = self.c.allocations.submit(
            self.allocation.id,
            use_case='A better use case',
            investigators=[self.INVESTIGATOR],
            grants=[
                {
                    'grant_type': 'arc',
                    'grant_subtype': 'arc-discovery',
                    'first_year_funded': 2024,
                    'last_year_funded': 2026,
                    'total_funding': 1000,
                }
            ],
            publications=[
                {'output_type': 'AJ', 'doi': '10.1234/xyz', 'publication': ''}
            ],
            quotas=[
                {
                    'zone': 'nectar',
                    'resource': 'compute.cores',
                    'requested_quota': 8,
                }
            ],
        )
        self.assertEqual(states.SUBMITTED, submitted.status)
        self.assertEqual('A better use case', submitted.use_case)
        # quotas is the full set: rows not listed are gone
        self.assertEqual(
            [('compute.cores', 8)],
            [(q.resource, q.requested_quota) for q in submitted.quotas],
        )
        self.assertEqual(
            ['ada@unimelb.edu.au'],
            [
                ci.email
                for ci in self.c.chiefinvestigators.list(
                    allocation=self.allocation.id
                )
            ],
        )
        self.assertEqual(
            1, len(self.c.grants.list(allocation=self.allocation.id))
        )
        self.assertEqual(
            1, len(self.c.publications.list(allocation=self.allocation.id))
        )
        self.assertEqual(
            1,
            len(self.c.allocations.list(parent_request=self.allocation.id)),
        )

    def test_approve_with_changes(self):
        self.as_approver()
        approved = self.c.allocations.approve(
            self.allocation.id,
            associated_site='qcif',
            status_explanation='Looks good',
            quotas=[
                {'zone': 'nectar', 'resource': 'compute.cores', 'quota': 16}
            ],
        )
        self.assertEqual(states.APPROVED, approved.status)
        self.assertEqual('qcif', approved.associated_site)
        self.assertEqual('Looks good', approved.status_explanation)
        cores = [q for q in approved.quotas if q.resource == 'compute.cores']
        self.assertEqual(16, cores[0].quota)

    def test_approve_warnings_conflict(self):
        factories.create_approver(
            common.APPROVER["user_name"],
            "The Approver",
            sites=[factories.get(models.Site, name='uom')],
        )
        allocation = factories.create_allocation(
            associated_site=factories.get(models.Site, name='uom')
        )
        self.as_approver()
        with self.assertRaises(client_exceptions.Conflict) as ctx:
            self.c.allocations.approve(
                allocation.id,
                ignore_warnings=False,
                quotas=[
                    {
                        'zone': 'monash',
                        'resource': 'volume.gigabytes',
                        'quota': 10,
                    }
                ],
            )
        codes = [w['code'] for w in ctx.exception.message['warnings']]
        self.assertIn('CINDER_NOT_LOCAL', codes)
        self.assertEqual(
            states.SUBMITTED, self.c.allocations.get(allocation.id).status
        )

    def test_decline(self):
        self.as_approver()
        declined = self.c.allocations.decline(
            self.allocation.id, status_explanation='Not enough detail'
        )
        self.assertEqual(states.DECLINED, declined.status)
        self.assertEqual('Not enough detail', declined.status_explanation)
        self.assertEqual(
            1,
            len(self.c.allocations.list(parent_request=self.allocation.id)),
        )

    def test_amend_with_changes(self):
        approved = factories.create_allocation(
            status=choices.APPROVED, contact_email=common.USER["user_name"]
        )
        self.as_user()
        amended = self.c.allocations.amend(
            approved.id,
            use_case='Amended use case',
            quotas=[
                {
                    'zone': 'nectar',
                    'resource': 'compute.cores',
                    'requested_quota': 12,
                }
            ],
        )
        self.assertEqual(states.UPDATE_PENDING, amended.status)
        self.assertEqual('Amended use case', amended.use_case)
        cores = [q for q in amended.quotas if q.resource == 'compute.cores']
        self.assertEqual(12, cores[0].requested_quota)

    def test_checks(self):
        self.as_user()
        result = self.c.allocations.checks(self.allocation.id)
        self.assertEqual({'warnings', 'nags'}, set(result))
        self.assertEqual([], result['warnings'])
        self.as_approver()
        result = self.c.allocations.checks(self.allocation.id, approving=True)
        self.assertIsInstance(result['warnings'], list)
        for warning in result['warnings']:
            self.assertEqual({'code', 'message'}, set(warning))

    def test_create_with_nested_lists(self):
        self.as_user()
        created = self.c.allocations.create(
            project_name='nested-proj',
            project_description='Nested',
            use_case='testing nested writes',
            quotas=[
                {
                    'zone': 'nectar',
                    'resource': 'compute.cores',
                    'requested_quota': 4,
                },
                {
                    'zone': 'nectar',
                    'resource': 'compute.instances',
                    'requested_quota': 2,
                },
            ],
            investigators=[self.INVESTIGATOR],
        )
        self.assertEqual(states.SUBMITTED, created.status)
        self.assertEqual(
            {('compute.cores', 4), ('compute.instances', 2)},
            {(q.resource, q.requested_quota) for q in created.quotas},
        )
        self.assertEqual(
            1, len(self.c.chiefinvestigators.list(allocation=created.id))
        )

    def test_list_include_and_mine(self):
        factories.create_allocation(contact_email='other@example.com')
        self.as_admin()
        listed = self.c.allocations.list(include='approver_info')
        self.assertEqual(2, len(listed))
        self.assertTrue(all(hasattr(a, 'approval_urgency') for a in listed))
        self.as_user()
        mine = self.c.allocations.list(mine=True)
        self.assertEqual([self.allocation.id], [a.id for a in mine])

    def test_organisation_search(self):
        self.as_anon()
        page = self.c.organisations.search('monash')
        self.assertEqual(1, page.count)
        self.assertEqual('Monash University', page[0].full_name)
        self.assertFalse(page.has_more)
        first = self.c.organisations.search(page_size=1)
        self.assertEqual(1, len(first))
        self.assertTrue(first.has_more)
        self.assertGreater(first.count, 1)
        second = self.c.organisations.search(page=2, page_size=1)
        self.assertNotEqual(first[0].id, second[0].id)

    def test_usage_types(self):
        self.as_anon()
        self.assertTrue([u.name for u in self.c.usage_types.list()])
        self.as_admin()
        created = self.c.usage_types.create(
            name='Contract testing', enabled=True
        )
        self.assertEqual('Contract testing', created.name)
        self.assertFalse(
            self.c.usage_types.update(created.id, enabled=False).enabled
        )
        self.assertEqual(created.id, self.c.usage_types.get(created.id).id)

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

"""Port of nectar-dashboard's rcallocation/tests/unit/api/test_allocations."""

from datetime import date
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from rcallocation import choices
from rcallocation import models
from rcallocation.tests.unit.api.v1 import common
from rcallocation.tests.unit import factories


def strip_requested(quotas):
    return [
        {k: v for k, v in q.items() if k != "requested_quota"} for q in quotas
    ]


class AllocationTests(common.AllocationApiTestCase):
    def test_list_allocations(self):
        self.as_user()
        response = self.client.get('/v1/allocations/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json['results']))

    def test_list_allocations_unauthenticated(self):
        self.as_anon()
        response = self.client.get('/v1/allocations/')
        self.assertEqual(response.status_code, 200)

    def test_list_allocations_unauthenticated_filtered(self):
        factories.create_allocation(parent_request_id=self.allocation.id)
        self.as_anon()
        response = self.client.get('/v1/allocations/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(2, response.json['count'])

        response = self.client.get(
            '/v1/allocations/?parent_request__isnull=True'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, response.json['count'])
        self.assertEqual(1, len(response.json['results']))

    def test_list_allocations_unauthenticated_filter_project_name(self):
        factories.create_allocation(project_name='findme')
        self.as_anon()
        response = self.client.get('/v1/allocations/?project_name=findme')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, response.json['count'])

    def test_list_allocations_negative(self):
        self.as_user()
        factories.create_allocation(contact_email='other@example.com')
        response = self.client.get('/v1/allocations/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json['results']))

    def test_list_allocations_admin(self):
        self.as_admin()
        factories.create_allocation(contact_email='other@example.com')
        response = self.client.get('/v1/allocations/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(2, len(response.json['results']))

    def test_filter_contact_email(self):
        self.as_admin()
        factories.create_allocation(contact_email='other@example.com')
        response = self.client.get(
            '/v1/allocations/?contact_email=other@example.com'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json['results']))

    def test_filter_national(self):
        self.as_admin()
        factories.create_allocation(national=True)
        response = self.client.get('/v1/allocations/?national=True')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json['results']))
        response = self.client.get('/v1/allocations/?national=False')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json['results']))

    def test_filter_allocation_home_national(self):
        self.as_admin()
        factories.create_allocation(national=True)
        response = self.client.get('/v1/allocations/?allocation_home=national')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json['results']))
        self.assertEqual(
            response.json['results'][0]['allocation_home'], 'national'
        )
        self.assertEqual(response.json['results'][0]['national'], True)

    def test_filter_allocation_home_unassigned(self):
        self.as_admin()
        factories.create_allocation(national=False, associated_site=None)
        response = self.client.get(
            '/v1/allocations/?allocation_home=unassigned'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json['results']))
        self.assertEqual(
            response.json['results'][0]['allocation_home'], 'unassigned'
        )
        self.assertEqual(response.json['results'][0]['national'], False)
        self.assertIsNone(response.json['results'][0]['associated_site'])

    def test_filter_allocation_home_local(self):
        self.as_admin()
        current_site = self.allocation.associated_site.name
        factories.create_allocation(national=False, associated_site=None)
        response = self.client.get(
            f'/v1/allocations/?allocation_home={current_site}'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json['results']))
        self.assertEqual(
            response.json['results'][0]['allocation_home'], current_site
        )
        self.assertEqual(response.json['results'][0]['national'], False)
        self.assertEqual(
            response.json['results'][0]['associated_site'], current_site
        )

    def test_filter_associated_site_name(self):
        self.as_admin()
        current_site = self.allocation.associated_site.name
        factories.create_allocation(national=False, associated_site=None)
        response = self.client.get(
            f'/v1/allocations/?associated_site={current_site}'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json['results']))
        self.assertEqual(
            response.json['results'][0]['allocation_home'], current_site
        )
        self.assertEqual(response.json['results'][0]['national'], False)
        self.assertEqual(
            response.json['results'][0]['associated_site'], current_site
        )

        response = self.client.get(
            '/v1/allocations/?associated_site=kanmantoo'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(0, len(response.json['results']))

    def test_get_allocation(self):
        self.as_user()
        response = self.client.get('/v1/allocations/1/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, response.json['id'])
        for field in ['notes', 'status_explanation']:
            self.assertNotIn(field, response.json.keys())
        site = response.json['associated_site']
        self.assertEqual(response.json['national'], False)
        self.assertEqual(response.json['allocation_home'], site)
        self.assertEqual(response.json['allocation_home_display'], site)
        quotas = [
            {'quota': 0, 'resource': 'volume.gigabytes', 'zone': 'melbourne'},
            {'quota': 0, 'resource': 'volume.gigabytes', 'zone': 'monash'},
            {'quota': 0, 'resource': 'compute.cores', 'zone': 'nectar'},
            {'quota': 0, 'resource': 'compute.instances', 'zone': 'nectar'},
            {'quota': 0, 'resource': 'network.router', 'zone': 'nectar'},
            {'quota': 0, 'resource': 'network.network', 'zone': 'nectar'},
            {'quota': 0, 'resource': 'network.loadbalancer', 'zone': 'nectar'},
            {'quota': 0, 'resource': 'network.floatingip', 'zone': 'nectar'},
            {'quota': 0, 'resource': 'object.object', 'zone': 'nectar'},
            {'quota': 0, 'resource': 'rating.budget', 'zone': 'nectar'},
        ]
        self.assertEqual(strip_requested(response.json['quotas']), quotas)
        for quota in response.json['quotas']:
            self.assertIn('requested_quota', quota)
        self.assertEqual(None, response.json.get('bundle'))
        self.assertIn('su_budget', response.json)
        self.assertIsNone(response.json['parent_request'])

    def test_get_allocation_unauthenticated(self):
        self.as_anon()
        response = self.client.get('/v1/allocations/1/')
        self.assertEqual(response.status_code, 200)
        public_fields = {
            'id',
            'project_name',
            'project_description',
            'modified_time',
            'submit_date',
            'start_date',
            'end_date',
            'bundle',
            'field_of_research_1',
            'field_of_research_2',
            'field_of_research_3',
            'for_percentage_1',
            'for_percentage_2',
            'for_percentage_3',
            'supported_organisations',
            'quotas',
        }
        self.assertEqual(public_fields, set(response.json.keys()))

    def test_get_allocation_bundle(self):
        allocation = factories.create_allocation(
            bundle='silver', create_quotas=False
        )
        self.as_anon()
        response = self.client.get(f'/v1/allocations/{allocation.id}/')
        self.assertEqual(response.status_code, 200)
        expected = [
            {'quota': 100, 'resource': 'object.object', 'zone': 'nectar'},
            {'quota': 100, 'resource': 'compute.cores', 'zone': 'nectar'},
            {'quota': 100, 'resource': 'compute.instances', 'zone': 'nectar'},
            {'quota': 1000, 'resource': 'compute.ram', 'zone': 'nectar'},
            {'quota': 8000, 'resource': 'rating.budget', 'zone': 'nectar'},
            {'quota': 10, 'resource': 'network.router', 'zone': 'nectar'},
            {'quota': 10, 'resource': 'network.network', 'zone': 'nectar'},
            {
                'quota': 10,
                'resource': 'network.loadbalancer',
                'zone': 'nectar',
            },
            {'quota': 10, 'resource': 'network.floatingip', 'zone': 'nectar'},
        ]
        self.assertEqual(expected, strip_requested(response.json['quotas']))
        self.assertEqual('silver', response.json.get('bundle'))

    def test_get_allocation_negative(self):
        self.as_user()
        factories.create_allocation(contact_email='other@example.com')
        response = self.client.get('/v1/allocations/2/')
        self.assertEqual(response.status_code, 404)

    def test_get_allocation_admin(self):
        self.as_admin()
        factories.create_allocation(contact_email='other@example.com')
        response = self.client.get('/v1/allocations/2/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(2, response.json['id'])
        self.assertIn('notes', response.json.keys())

    def test_update_allocation(self):
        self.as_user()
        self.assertNotEqual('test-update', self.allocation.use_case)
        response = self.client.patch(
            '/v1/allocations/1/', data={'use_case': 'test-update'}
        )
        self.assertEqual(response.status_code, 200, response.json)
        allocation = factories.refresh(self.allocation)
        self.assertEqual('test-update', allocation.use_case)

    def test_update_allocation_invalid_state(self):
        self.as_user()
        allocation = factories.create_allocation(
            status=choices.APPROVED, contact_email=common.USER["user_name"]
        )
        response = self.client.patch(
            f'/v1/allocations/{allocation.id}/',
            data={'use_case': 'test-update'},
        )
        self.assertEqual(response.status_code, 403)

    def test_update_allocation_read_only_field(self):
        self.as_user()
        response = self.client.patch(
            '/v1/allocations/1/', data={'status': choices.APPROVED}
        )
        self.assertEqual(response.status_code, 200)
        # It returns 200 but value doesn't change
        allocation = factories.refresh(self.allocation)
        self.assertEqual(choices.SUBMITTED, allocation.status)

    def test_update_allocation_read_only_fields_admin(self):
        self.as_admin()
        parent = factories.create_allocation(contact_email='other@example.com')
        response = self.client.patch(
            '/v1/allocations/1/',
            json={
                'status': choices.APPROVED,
                'approver_email': 'approver@example.com',
                'parent_request': parent.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        # It returns 200 but the values don't change
        allocation = factories.refresh(self.allocation)
        self.assertEqual(choices.SUBMITTED, allocation.status)
        self.assertEqual('', allocation.approver_email)
        self.assertIsNone(allocation.parent_request_id)

    def test_update_national(self):
        self.assertFalse(self.allocation.national)
        self.as_admin()
        response = self.client.patch(
            '/v1/allocations/1/', data={'national': True}
        )
        self.assertEqual(response.status_code, 200)
        allocation = factories.refresh(self.allocation)
        self.assertTrue(allocation.national)

    def test_update_national_as_user(self):
        self.assertFalse(self.allocation.national)
        self.as_user()
        response = self.client.patch(
            '/v1/allocations/1/', data={'national': True}
        )
        self.assertEqual(response.status_code, 200)
        # It returns 200 but value doesn't change
        allocation = factories.refresh(self.allocation)
        self.assertFalse(allocation.national)

    def test_update_associated_site(self):
        current_site = self.allocation.associated_site.name
        new_site = 'monash' if current_site != 'monash' else 'qcif'
        self.as_admin()
        response = self.client.patch(
            '/v1/allocations/1/', data={'associated_site': new_site}
        )
        self.assertEqual(response.status_code, 200)
        allocation = factories.refresh(self.allocation)
        self.assertEqual(allocation.associated_site.name, new_site)

    def test_update_associated_site_as_user(self):
        current_site = self.allocation.associated_site.name
        new_site = 'monash' if current_site != 'monash' else 'qcif'
        self.as_user()
        response = self.client.patch(
            '/v1/allocations/1/', data={'associated_site': new_site}
        )
        self.assertEqual(response.status_code, 403)

    def test_update_allocation_home_local(self):
        self.as_admin()
        current_site = self.allocation.associated_site.name
        new_site = 'monash' if current_site != 'monash' else 'qcif'
        response = self.client.patch(
            '/v1/allocations/1/', data={'allocation_home': new_site}
        )
        self.assertEqual(response.status_code, 200)
        allocation = factories.refresh(self.allocation)
        self.assertEqual(allocation.associated_site.name, new_site)
        self.assertFalse(allocation.national)

    def test_update_allocation_home_national(self):
        self.as_admin()
        current_site = self.allocation.associated_site.name
        response = self.client.patch(
            '/v1/allocations/1/', data={'allocation_home': 'national'}
        )
        self.assertEqual(response.status_code, 200)
        allocation = factories.refresh(self.allocation)
        self.assertEqual(allocation.associated_site.name, current_site)
        self.assertTrue(allocation.national)

    def test_update_allocation_home_unassigned(self):
        self.as_admin()
        response = self.client.patch(
            '/v1/allocations/1/', data={'allocation_home': 'unassigned'}
        )
        self.assertEqual(response.status_code, 200)
        allocation = factories.refresh(self.allocation)
        self.assertIsNone(allocation.associated_site)
        self.assertFalse(allocation.national)

    def test_update_allocation_dates(self):
        self.as_admin()
        start_date = date(2019, 4, 2)
        end_date = date(2019, 5, 2)
        response = self.client.patch(
            '/v1/allocations/1/',
            data={
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d'),
            },
        )
        self.assertEqual(response.status_code, 200)
        allocation = factories.refresh(self.allocation)
        self.assertEqual(start_date, allocation.start_date)
        self.assertEqual(end_date, allocation.end_date)

    def test_update_allocation_dates_user(self):
        self.as_user()
        response = self.client.patch(
            '/v1/allocations/1/',
            data={'start_date': '2019-04-03', 'end_date': '2019-05-03'},
        )
        self.assertEqual(response.status_code, 200)
        allocation = factories.refresh(self.allocation)
        self.assertIsNone(allocation.start_date)
        self.assertIsNone(allocation.end_date)

    def test_update_allocation_ardc_none(self):
        self.as_admin()
        response = self.client.patch(
            '/v1/allocations/1/', json={'ardc_support': []}
        )
        self.assertEqual(response.status_code, 200)
        allocation = factories.refresh(self.allocation)
        self.assertEqual(0, len(allocation.ardc_support))

    def test_update_allocation_ardc_two(self):
        self.as_admin()
        response = self.client.patch(
            '/v1/allocations/1/', json={'ardc_support': ['cvl', 'BCCVL']}
        )
        self.assertEqual(response.status_code, 200, response.json)
        allocation = factories.refresh(self.allocation)
        self.assertEqual(2, len(allocation.ardc_support))

        # Check that we can see the ardc_support in a GET
        response = self.client.get('/v1/allocations/1/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['ardc_support'], ['BCCVL', 'CVL'])

    def test_update_allocation_ardc_unknown(self):
        self.as_admin()
        response = self.client.patch(
            '/v1/allocations/1/', json={'ardc_support': ['fish']}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            {
                'ardc_support': [
                    "'fish' is not a known ARDC project or program"
                ]
            },
            response.json,
        )

    def test_update_allocation_facilities_none(self):
        self.as_admin()
        response = self.client.patch(
            '/v1/allocations/1/', json={'ncris_facilities': []}
        )
        self.assertEqual(response.status_code, 200)
        allocation = factories.refresh(self.allocation)
        self.assertEqual(0, len(allocation.ncris_facilities))

    def test_update_allocation_facilities_two(self):
        self.as_admin()
        response = self.client.patch(
            '/v1/allocations/1/', json={'ncris_facilities': ['ala', 'MA']}
        )
        self.assertEqual(response.status_code, 200)
        allocation = factories.refresh(self.allocation)
        self.assertEqual(2, len(allocation.ncris_facilities))

        # Check that we can see the facilities in a GET
        response = self.client.get('/v1/allocations/1/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['ncris_facilities'], ['ALA', 'MA'])

    def test_update_allocation_facilities_unknown(self):
        self.as_admin()
        response = self.client.patch(
            '/v1/allocations/1/', json={'ncris_facilities': ['fish']}
        )
        self.assertEqual(response.status_code, 400)

    def test_update_allocation_organizations(self):
        self.assertEqual(1, len(self.allocation.supported_organisations))

        self.as_approver()
        response = self.client.patch(
            f'/v1/allocations/{self.allocation.id}/',
            json={'supported_organisations': ['qcif', 'monash']},
        )
        self.assertEqual(response.status_code, 200, response.json)
        allocation = factories.refresh(self.allocation)
        self.assertEqual(2, len(allocation.supported_organisations))

        response = self.client.patch(
            f'/v1/allocations/{allocation.id}/',
            json={
                'supported_organisations': [
                    'Monash University',
                    'Queensland Cyber Infrastructure Foundation',
                ]
            },
        )
        self.assertEqual(response.status_code, 200)
        allocation = factories.refresh(self.allocation)
        self.assertEqual(2, len(allocation.supported_organisations))

        response = self.client.patch(
            f'/v1/allocations/{allocation.id}/',
            json={
                'supported_organisations': [
                    'https://ror.org/12345678',
                    'https://ror.org/23456789',
                ]
            },
        )
        self.assertEqual(response.status_code, 200)
        allocation = factories.refresh(self.allocation)
        self.assertEqual(2, len(allocation.supported_organisations))

        # Check that we can see the organizations in a GET
        response = self.client.get(f'/v1/allocations/{self.allocation.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(
            response.json['supported_organisations'],
            ['https://ror.org/23456789', 'https://ror.org/12345678'],
        )

    def test_update_allocation_organisations_disabled(self):
        self.as_approver()
        response = self.client.patch(
            f'/v1/allocations/{self.allocation.id}/',
            json={'supported_organisations': ['UWW']},
        )
        self.assertEqual(response.status_code, 400)

    def test_update_allocation_organisations_ambiguous(self):
        factories.create_organisation(
            short_name='UZ',
            full_name='Zumba University',
            ror_id='https://ror.org/1111',
        )
        factories.create_organisation(
            short_name='UZ',
            full_name='Zombie University',
            ror_id='https://ror.org/2222',
        )
        self.as_approver()
        response = self.client.patch(
            f'/v1/allocations/{self.allocation.id}/',
            json={'supported_organisations': ['Zombie University']},
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.patch(
            f'/v1/allocations/{self.allocation.id}/',
            json={'supported_organisations': ['Zumba University']},
        )
        self.assertEqual(response.status_code, 200)
        # The short name is ambiguous
        response = self.client.patch(
            f'/v1/allocations/{self.allocation.id}/',
            json={'supported_organisations': ['UZ']},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            {
                'supported_organisations': [
                    "'UZ' is an ambiguous Organisation name"
                ]
            },
            response.json,
        )

    def test_update_allocation_organisations_bad(self):
        self.as_approver()
        # Fish is unknown
        response = self.client.patch(
            f'/v1/allocations/{self.allocation.id}/',
            json={'supported_organisations': ['fish']},
        )
        self.assertEqual(response.status_code, 400)

        # 'Unknown' is known but not allowed
        response = self.client.patch(
            f'/v1/allocations/{self.allocation.id}/',
            json={'supported_organisations': ['unknown']},
        )
        self.assertEqual(response.status_code, 400)

        # 'All' is known and allowed
        response = self.client.patch(
            f'/v1/allocations/{self.allocation.id}/',
            json={'supported_organisations': ['all']},
        )
        self.assertEqual(response.status_code, 200)

        # 'All' cannot be used with other orgs
        response = self.client.patch(
            f'/v1/allocations/{self.allocation.id}/',
            json={'supported_organisations': ['all', 'qcif']},
        )
        self.assertEqual(response.status_code, 400)

    def test_update_allocation_unauthenticated(self):
        self.as_anon()
        response = self.client.patch(
            '/v1/allocations/1/', data={'use_case': 'test-update'}
        )
        self.assertEqual(response.status_code, 403)

    def test_update_allocation_negative(self):
        self.as_user()
        factories.create_allocation(contact_email='other@example.com')
        response = self.client.patch(
            '/v1/allocations/2/', data={'use_case': 'test-update'}
        )
        self.assertEqual(response.status_code, 404)

    def test_update_allocation_admin(self):
        self.as_admin()
        factories.create_allocation(contact_email='other@example.com')
        response = self.client.patch(
            '/v1/allocations/2/', data={'use_case': 'test-update'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual('test-update', response.json['use_case'])

    def test_update_allocation_admin_field(self):
        self.as_admin()
        factories.create_allocation(contact_email='other@example.com')
        response = self.client.patch(
            '/v1/allocations/2/', data={'notes': 'test-notes'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual('test-notes', response.json['notes'])

    def test_update_notes_keeps_modified_time(self):
        self.as_admin()
        before = factories.refresh(self.allocation).modified_time
        response = self.client.patch(
            '/v1/allocations/1/', data={'notes': 'test-notes'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            before, factories.refresh(self.allocation).modified_time
        )
        response = self.client.patch(
            '/v1/allocations/1/', data={'use_case': 'changed'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreater(
            factories.refresh(self.allocation).modified_time, before
        )

    def test_update_same_project_name(self):
        self.as_user()
        allocation = factories.refresh(self.allocation)
        allocation.project_name = 'keepme'
        factories.db.session.commit()
        response = self.client.patch(
            '/v1/allocations/1/', data={'project_name': 'keepme'}
        )
        self.assertEqual(response.status_code, 200, response.json)

    def test_approver_info(self):
        self.as_admin()
        allocation = factories.create_allocation(
            status='A',
            contact_email='other@example.com',
            end_date=(datetime.now(timezone.utc).date() - timedelta(days=2)),
        )
        response = self.client.get('/v1/allocations/2/approver_info/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {
                'approval_urgency': 'N/A',
                'expiry_state': 'Unknown',
                'concerned_sites': [allocation.associated_site.name],
            },
            response.json,
        )

        allocation = factories.refresh(allocation)
        allocation.status = 'N'
        factories.db.session.commit()
        site = allocation.associated_site.name
        response = self.client.get('/v1/allocations/2/approver_info/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {
                'approval_urgency': 'New',
                'expiry_state': 'Unknown',
                'concerned_sites': [site],
            },
            response.json,
        )

    def test_approver_info_as_user(self):
        self.as_user()
        factories.create_allocation(
            status='A', contact_email='other@example.com'
        )
        response = self.client.get('/v1/allocations/2/approver_info/')
        self.assertEqual(response.status_code, 403)

    def _make_data(
        self,
        project_name='test-project',
        project_description='project for testing',
        start_date='2000-01-01',
        use_case='for testing',
        supported_organisations=['https://ror.org/12345678'],
        usage_types=['Other'],
        **kwargs,
    ):
        data = {
            'project_name': project_name,
            'project_description': project_description,
            'start_date': start_date,
            'use_case': use_case,
            'usage_types': usage_types,
            'supported_organisations': supported_organisations,
            'ncris_facilities': ['ALA'],
        }
        data.update(kwargs)
        return data

    def _created(self, project_name='test-project'):
        return factories.get(
            models.AllocationRequest, project_name=project_name
        )

    def test_create(self):
        self.as_admin()
        data = self._make_data()
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        allocation = self._created()
        self.assertEqual(common.ADMIN["user_id"], allocation.created_by)
        self.assertEqual('test-project', response.json['project_name'])
        self.assertEqual(
            common.ADMIN["user_name"], response.json['contact_email']
        )
        self.assertIsNone(response.json['associated_site'])
        self.assertEqual(response.json['allocation_home'], 'unassigned')
        self.assertFalse(response.json['national'])
        self.assertEqual(choices.SUBMITTED, response.json['status'])
        self.assertEqual(1, len(response.json['ncris_facilities']))

    def test_create_as_user(self):
        self.as_user()
        data = self._make_data()
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        allocation = self._created()
        self.assertEqual(common.USER["user_id"], allocation.created_by)
        self.assertEqual('test-project', response.json['project_name'])
        self.assertEqual(
            common.USER["user_name"], response.json['contact_email']
        )
        self.assertIsNone(response.json['associated_site'])
        self.assertEqual(response.json['allocation_home'], 'unassigned')
        self.assertFalse(response.json['national'])
        self.assertEqual(choices.SUBMITTED, response.json['status'])
        self.assertEqual(1, len(response.json['ncris_facilities']))

    def test_create_with_bundle(self):
        self.as_user()
        data = self._make_data()
        data['bundle'] = 'gold'
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        allocation = self._created()
        self.assertEqual('gold', allocation.bundle.name)

    def test_create_with_bundle_invalid(self):
        self.as_user()
        data = self._make_data()
        data['bundle'] = 'bogus'
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            "Bundle 'bogus' does not exist", response.json['bundle'][0]
        )

    def test_create_with_no_site(self):
        self.as_admin()
        data = self._make_data(national=False, associated_site='')
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        allocation = self._created()
        self.assertEqual(common.ADMIN["user_id"], allocation.created_by)
        self.assertIsNone(response.json['associated_site'])
        self.assertEqual(response.json['allocation_home'], 'unassigned')
        self.assertFalse(response.json['national'])
        self.assertEqual(choices.SUBMITTED, response.json['status'])

    def test_create_as_user_with_no_site(self):
        self.as_user()
        data = self._make_data(national=False, associated_site='')
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        self.assertFalse(response.json['national'])
        self.assertIsNone(response.json['associated_site'])

    def test_create_as_user_with_national(self):
        self.as_user()
        data = self._make_data(national=True, associated_site='')
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        # Yes ... 'national' should be false if there is no associate site
        self.assertFalse(response.json['national'])
        self.assertIsNone(response.json['associated_site'])

    def test_create_with_associated_site(self):
        self.as_admin()
        data = self._make_data(national=False, associated_site='qcif')
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(response.json['associated_site'], 'qcif')
        self.assertEqual(response.json['allocation_home'], 'qcif')
        self.assertFalse(response.json['national'])
        self.assertEqual(choices.SUBMITTED, response.json['status'])

    def test_create_with_associated_site_as_user(self):
        self.as_user()
        data = self._make_data(national=False, associated_site='qcif')
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 403)

    def test_create_override_contact_email(self):
        self.as_admin()
        data = self._make_data(contact_email='test_override@example.com')
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(
            'test_override@example.com', response.json['contact_email']
        )

    def test_create_bad_site(self):
        self.as_user()
        data = self._make_data(national=False, associated_site='Bogus')
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json['associated_site'][0], "Site 'Bogus' does not exist"
        )

    def test_create_alloc_home(self):
        self.as_admin()
        data = self._make_data(national=False, allocation_home='qcif')
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(response.json['allocation_home'], 'qcif')
        self.assertEqual(response.json['associated_site'], 'qcif')
        self.assertFalse(response.json['national'])

    def test_create_alloc_home_national(self):
        self.as_admin()
        data = self._make_data(allocation_home='national')
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(response.json['allocation_home'], 'national')
        self.assertEqual(response.json['associated_site'], None)
        self.assertTrue(response.json['national'])

    def test_create_alloc_home_unassigned(self):
        self.as_admin()
        data = self._make_data(allocation_home='unassigned')
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(response.json['allocation_home'], 'unassigned')
        self.assertEqual(response.json['associated_site'], None)
        self.assertFalse(response.json['national'])

    def test_create_alloc_home_as_user(self):
        self.as_user()
        data = self._make_data(allocation_home='qcif')
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 403)

    def test_create_bogus_alloc_home_as_user(self):
        self.as_user()
        data = self._make_data(allocation_home='Bogus')
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json['allocation_home'][0], "Site 'Bogus' does not exist"
        )

    def test_create_bogus_alloc_home2_as_user(self):
        self.as_user()
        for bogus in ['national', 'unassigned']:
            data = self._make_data(allocation_home=bogus)
            response = self.client.post('/v1/allocations/', data=data)
            self.assertEqual(response.status_code, 403)

    def test_create_alloc_home_conflict(self):
        self.as_admin()
        data = self._make_data(
            national=False, associated_site='qcif', allocation_home='qcif'
        )
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json[0],
            "Cannot use 'allocation_home' with 'national' "
            "or 'associated_site'",
        )

    def test_create_duplicate_project_name(self):
        self.as_user()
        factories.create_allocation(project_name='test-project')
        data = self._make_data()
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json['project_name'][0], "Project name already exists"
        )

    def test_create_duplicate_project_name_normalised(self):
        self.as_user()
        factories.create_allocation(project_name='Test_Project')
        data = self._make_data(project_name='test-project')
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 400)

    def test_create_multiple_usage_types(self):
        self.as_user()
        data = self._make_data(
            usage_types=['Other', 'Hosting services to support research']
        )
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(2, len(self._created().usage_types))

    def test_create_unknown_usage_type(self):
        self.as_user()
        data = self._make_data(usage_types=['Unknown'])
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json['usage_types'][0],
            "'Unknown' is not a known UsageType",
        )

    def test_create_disabled_usage_type(self):
        self.as_user()
        data = self._make_data(usage_types=['Disabled'])
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json['usage_types'][0], "UsageType 'Disabled' is disabled"
        )

    def test_create_no_usage_types(self):
        self.as_user()
        data = self._make_data(usage_types=[])
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)

    def test_create_organisations(self):
        self.as_user()
        data = self._make_data(supported_organisations=['QCIF', 'Monash'])
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)

    def test_create_all_organisations(self):
        self.as_user()
        data = self._make_data(supported_organisations=['all'])
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)

    def test_create_dup_organisations(self):
        self.as_user()
        data = self._make_data(supported_organisations=["QCIF", "QCIF"])
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 400)

    def test_create_bad_organisations(self):
        self.as_user()
        data = self._make_data(supported_organisations=["Unknown"])
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 400)

        data = self._make_data(supported_organisations=["all", "QCIF"])
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 400)

        data = self._make_data(supported_organisations=["fish"])
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 400)

    def test_create_unauthenticated(self):
        self.as_anon()
        data = self._make_data()
        response = self.client.post('/v1/allocations/', data=data)
        self.assertEqual(response.status_code, 403)

    def test_create_json(self):
        self.as_user()
        data = self._make_data()
        response = self.client.post('/v1/allocations/', json=data)
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(['ALA'], response.json['ncris_facilities'])

    def test_approve(self):
        self.as_approver()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/approve/'
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(choices.APPROVED, response.json['status'])
        self.assertEqual(
            common.APPROVER["user_name"], response.json['approver_email']
        )
        self.assertEqual(1, factories.history_count(self.allocation))

    def test_approve_invalid_state(self):
        self.as_approver()
        allocation = factories.create_allocation(status=choices.APPROVED)
        response = self.client.post(
            f'/v1/allocations/{allocation.id}/approve/'
        )
        self.assertEqual(response.status_code, 403)

    def test_approve_no_site(self):
        self.as_approver()
        allocation = factories.create_allocation(associated_site=None)
        response = self.client.post(
            f'/v1/allocations/{allocation.id}/approve/'
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json['error'],
            "The associated_site attribute must be set before approving",
        )

    def test_approve_invalid_role(self):
        self.as_user()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/approve/'
        )
        self.assertEqual(response.status_code, 403)

    def test_approve_admin_only(self):
        # An admin without the approver role cannot approve (parity).
        self.as_admin()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/approve/'
        )
        self.assertEqual(response.status_code, 403)

    def test_amend(self):
        self.as_user()
        allocation = factories.create_allocation(
            contact_email=common.USER["user_name"], status=choices.APPROVED
        )
        response = self.client.post(f'/v1/allocations/{allocation.id}/amend/')
        self.assertEqual(response.status_code, 200, response.json)
        allocation = factories.refresh(allocation)
        self.assertEqual(choices.UPDATE_PENDING, allocation.status)
        self.assertEqual(1, factories.history_count(allocation))

    def test_amend_invalid_state(self):
        self.as_user()
        response = self.client.post('/v1/allocations/1/amend/')
        self.assertEqual(response.status_code, 403)

    def test_amend_invalid_user(self):
        self.as_user()
        allocation = factories.create_allocation(
            contact_email='bogus@wrong.com', status=choices.APPROVED
        )
        response = self.client.post(f'/v1/allocations/{allocation.id}/amend/')
        self.assertEqual(response.status_code, 404)

    def test_delete(self):
        self.assertEqual(0, factories.history_count(self.allocation))
        self.as_admin()
        response = self.client.post('/v1/allocations/1/delete/')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(choices.DELETED, response.json['status'])
        # Check that a history record has been created
        self.assertEqual(1, factories.history_count(self.allocation))

    def test_delete_deleted(self):
        self.as_admin()
        allocation = factories.refresh(self.allocation)
        allocation.status = choices.DELETED
        factories.db.session.commit()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/delete/'
        )
        self.assertEqual(response.status_code, 200)
        # Check that no history record was created
        self.assertEqual(0, factories.history_count(self.allocation))

    def test_delete_historic(self):
        self.as_admin()
        # Kludge ... a history record is one with a parent
        allocation = factories.refresh(self.allocation)
        allocation.parent_request_id = allocation.id
        factories.db.session.commit()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/delete/'
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_invalid_role(self):
        self.as_user()
        response = self.client.post('/v1/allocations/1/delete/')
        self.assertEqual(response.status_code, 403)

    def test_destroy(self):
        self.as_user()
        response = self.client.delete('/v1/allocations/1/')
        self.assertEqual(response.status_code, 405)

    def test_destroy_anonymous(self):
        self.as_anon()
        response = self.client.delete('/v1/allocations/1/')
        self.assertEqual(response.status_code, 403)

    def test_list_pagination_links(self):
        self.as_admin()
        for _ in range(3):
            factories.create_allocation(contact_email='other@example.com')
        response = self.client.get('/v1/allocations/?limit=2')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(4, response.json['count'])
        self.assertEqual(2, len(response.json['results']))
        self.assertEqual(
            'http://localhost/v1/allocations/?limit=2&offset=2',
            response.json['next'],
        )
        self.assertIsNone(response.json['previous'])
        response = self.client.get(response.json['next'])
        self.assertEqual(2, len(response.json['results']))
        self.assertIsNone(response.json['next'])
        self.assertEqual(
            'http://localhost/v1/allocations/?limit=2',
            response.json['previous'],
        )

    def test_list_ordering_newest_first(self):
        self.as_admin()
        older = factories.create_allocation(
            contact_email='other@example.com',
            modified_time=datetime(2020, 1, 1),
        )
        response = self.client.get('/v1/allocations/')
        ids = [a['id'] for a in response.json['results']]
        self.assertEqual([self.allocation.id, older.id], ids)

    def test_datetime_format(self):
        self.as_user()
        response = self.client.get('/v1/allocations/1/')
        self.assertRegex(
            response.json['modified_time'],
            r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$',
        )

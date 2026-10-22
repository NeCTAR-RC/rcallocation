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

"""Chief investigators, publications and grants (port of
test_investigators plus coverage of the two sibling endpoints)."""

from rcallocation import choices
from rcallocation.extensions import db
from rcallocation import models
from rcallocation.tests.unit.api.v1 import common
from rcallocation.tests.unit import factories


class InvestigatorTests(common.AllocationApiTestCase):
    def setUp(self):
        super().setUp()
        self.ci = factories.create_investigator(
            self.allocation,
            primary_organisation=factories.get(
                models.Organisation, short_name="Monash"
            ),
        )

    def test_list(self):
        self.as_user()
        response = self.client.get('/v1/chiefinvestigators/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json['results']))
        self.assertEqual(
            {
                'id': self.ci.id,
                'allocation': self.allocation.id,
                'title': 'Prof.',
                'given_name': 'MeRC',
                'surname': 'Monash',
                'email': 'merc.monash@monash.edu',
                'primary_organisation': 'https://ror.org/23456789',
                'additional_researchers': 'None',
            },
            response.json['results'][0],
        )

    def test_list_unauthenticated(self):
        self.as_anon()
        response = self.client.get('/v1/chiefinvestigators/')
        self.assertEqual(response.status_code, 403)

    def test_list_other(self):
        # Don't list the CIs for another user's allocations
        self.as_user2()
        response = self.client.get('/v1/chiefinvestigators/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(0, len(response.json['results']))

    def test_list_admin(self):
        # An admin can see all allocations' CIs
        self.as_admin()
        response = self.client.get('/v1/chiefinvestigators/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json['results']))

    def test_list_filter_allocation(self):
        other = factories.create_allocation(contact_email='x@example.com')
        factories.create_investigator(other)
        self.as_admin()
        response = self.client.get(
            f'/v1/chiefinvestigators/?allocation={self.allocation.id}'
        )
        self.assertEqual(1, response.json['count'])

    def test_get(self):
        self.as_user()
        response = self.client.get(f'/v1/chiefinvestigators/{self.ci.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.ci.id, response.json['id'])

    def test_get_unauthenticated(self):
        self.as_anon()
        response = self.client.get(f'/v1/chiefinvestigators/{self.ci.id}/')
        self.assertEqual(response.status_code, 403)

    def test_get_other(self):
        self.as_user2()
        response = self.client.get(f'/v1/chiefinvestigators/{self.ci.id}/')
        self.assertEqual(response.status_code, 404)

    def test_get_admin(self):
        self.as_admin()
        response = self.client.get(f'/v1/chiefinvestigators/{self.ci.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.ci.id, response.json['id'])

    def test_update(self):
        self.as_user()
        response = self.client.patch(
            f'/v1/chiefinvestigators/{self.ci.id}/',
            data={'given_name': 'Cholmondely'},
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual('Cholmondely', response.json['given_name'])

    def test_update_wrong_state(self):
        self.as_user()
        allocation = factories.refresh(self.allocation)
        allocation.status = choices.APPROVED
        db.session.commit()
        response = self.client.patch(
            f'/v1/chiefinvestigators/{self.ci.id}/',
            data={'given_name': 'Maxwell'},
        )
        self.assertEqual(response.status_code, 403)

    def test_delete(self):
        self.as_user()
        response = self.client.delete(f'/v1/chiefinvestigators/{self.ci.id}/')
        self.assertEqual(response.status_code, 204)

    def test_delete_invalid_state(self):
        self.as_user()
        allocation = factories.refresh(self.allocation)
        allocation.status = choices.APPROVED
        db.session.commit()
        response = self.client.delete(f'/v1/chiefinvestigators/{self.ci.id}/')
        self.assertEqual(response.status_code, 403)

    def test_delete_other_user(self):
        self.as_user2()
        response = self.client.delete(f'/v1/chiefinvestigators/{self.ci.id}/')
        self.assertEqual(response.status_code, 404)

    def _make_data(self):
        return {
            'allocation': self.allocation.id,
            'given_name': 'Joe',
            'surname': 'Bloggs',
            'title': 'Mr',
            'email': 'joe@monash.edu',
            'primary_organisation': factories.get(
                models.Organisation, short_name='Monash'
            ).id,
        }

    def test_create(self):
        # This doesn't strictly make sense because we are actually
        # adding a 2nd CI record.
        for persona in (self.as_user, self.as_approver):
            persona()
            data = self._make_data()
            response = self.client.post('/v1/chiefinvestigators/', data=data)
            self.assertEqual(response.status_code, 201, response.json)
            ci = db.session.get(models.ChiefInvestigator, response.json['id'])
            self.assertEqual('Bloggs', ci.surname)
            self.assertEqual(self.allocation.id, ci.allocation_id)

    def test_create_primary_org_all(self):
        self.as_user()
        data = self._make_data()
        data['primary_organisation'] = 'all'
        response = self.client.post('/v1/chiefinvestigators/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            {
                'primary_organisation': [
                    "'All Organisations' may not be used here"
                ]
            },
            response.json,
        )

    def test_create_wrong_state(self):
        self.as_user()
        allocation = factories.refresh(self.allocation)
        allocation.status = choices.APPROVED
        db.session.commit()
        response = self.client.post(
            '/v1/chiefinvestigators/', data=self._make_data()
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            ["Allocation in status 'Approved' can not be updated"],
            response.json,
        )

    def test_create_other_users_allocation(self):
        self.as_user2()
        response = self.client.post(
            '/v1/chiefinvestigators/', data=self._make_data()
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(["Allocation does not exist"], response.json)

    def test_create_unauthenticated(self):
        self.as_anon()
        response = self.client.post(
            '/v1/chiefinvestigators/', data=self._make_data()
        )
        self.assertEqual(response.status_code, 403)


class PublicationTests(common.AllocationApiTestCase):
    def setUp(self):
        super().setUp()
        self.pub = factories.create_publication(self.allocation)

    def test_list(self):
        self.as_user()
        response = self.client.get('/v1/publications/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [
                {
                    'id': self.pub.id,
                    'allocation': self.allocation.id,
                    'output_type': 'AN',
                    'publication': 'publication testing',
                    'doi': '',
                    'crossref_metadata': '',
                }
            ],
            response.json['results'],
        )

    def test_create_with_doi(self):
        self.as_user()
        data = {
            'allocation': self.allocation.id,
            'output_type': 'AJ',
            'doi': '10.1234/abc-123',
        }
        response = self.client.post('/v1/publications/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual('10.1234/abc-123', response.json['doi'])

    def test_create_bad_doi(self):
        self.as_user()
        data = {
            'allocation': self.allocation.id,
            'output_type': 'AJ',
            'doi': 'not a doi',
        }
        response = self.client.post('/v1/publications/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('doi', response.json)

    def test_create_bad_output_type(self):
        self.as_user()
        data = {'allocation': self.allocation.id, 'output_type': 'ZZ'}
        response = self.client.post('/v1/publications/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            {'output_type': ['"ZZ" is not a valid choice.']}, response.json
        )

    def test_delete(self):
        self.as_user()
        response = self.client.delete(f'/v1/publications/{self.pub.id}/')
        self.assertEqual(response.status_code, 204)


class GrantTests(common.AllocationApiTestCase):
    def setUp(self):
        super().setUp()
        self.grant = factories.create_grant(
            self.allocation, grant_type='arc', grant_subtype='arc-discovery'
        )

    def test_list(self):
        self.as_user()
        response = self.client.get('/v1/grants/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [
                {
                    'id': self.grant.id,
                    'allocation': self.allocation.id,
                    'grant_type': 'arc',
                    'grant_subtype': 'arc-discovery',
                    'funding_body_scheme': 'ARC funding scheme',
                    'grant_id': 'arc-grant-0001',
                    'first_year_funded': 2015,
                    'last_year_funded': 2017,
                    'total_funding': 20000.0,
                }
            ],
            response.json['results'],
        )

    def test_create(self):
        self.as_user()
        data = {
            'allocation': self.allocation.id,
            'grant_type': 'nhmrc',
            'grant_subtype': 'nhmrc-ideas',
            'first_year_funded': 2024,
            'last_year_funded': 2026,
            'total_funding': 50000,
        }
        response = self.client.post('/v1/grants/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual('nhmrc', response.json['grant_type'])

    def test_create_bad_year(self):
        self.as_user()
        data = {
            'allocation': self.allocation.id,
            'grant_type': 'nhmrc',
            'grant_subtype': 'nhmrc-ideas',
            'first_year_funded': 1900,
            'last_year_funded': 2026,
            'total_funding': 50000,
        }
        response = self.client.post('/v1/grants/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            {'first_year_funded': ['Please input a year between 1970 ~ 3000']},
            response.json,
        )

    def test_update_by_approver(self):
        self.as_approver()
        response = self.client.patch(
            f'/v1/grants/{self.grant.id}/', data={'grant_id': 'new-id'}
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual('new-id', response.json['grant_id'])

    def test_delete_other(self):
        self.as_user2()
        response = self.client.delete(f'/v1/grants/{self.grant.id}/')
        self.assertEqual(response.status_code, 404)

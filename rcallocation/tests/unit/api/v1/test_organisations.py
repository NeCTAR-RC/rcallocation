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

from rcallocation.extensions import db
from rcallocation import models
from rcallocation.tests.unit.api.v1 import common
from rcallocation.tests.unit import factories


class OrganisationTest(common.AllocationApiTestCase):
    def setUp(self):
        super().setUp()
        self.admin_approver = factories.create_approver(
            common.ADMIN["user_name"], "Fred the Admin"
        )

    def _make_data(
        self,
        full_name='University of Testing Australia',
        short_name='UTA',
        country='AU',
        **kwargs,
    ):
        data = {
            'full_name': full_name,
            'short_name': short_name,
            'country': country,
        }
        data.update(kwargs)
        return data

    def _check_data(self, expected, actual, extra=None):
        e = {'enabled': True, 'ror_id': '', 'parent': None, 'precedes': []}
        e.update(expected)
        e.update(extra or {})
        for k in ['id', 'proposed_by', 'vetted_by']:
            e.pop(k, None)
        for key, value in e.items():
            self.assertEqual(value, actual[key], key)

    def test_list(self):
        self.as_admin()
        response = self.client.get('/v1/organisations/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json['results']), 4)

    def test_list_as_approver(self):
        self.as_approver()
        response = self.client.get('/v1/organisations/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json['results']), 4)

    def test_list_as_user(self):
        self.as_user()
        response = self.client.get('/v1/organisations/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json['results']), 4)

    def test_list_anon(self):
        self.as_anon()
        response = self.client.get('/v1/organisations/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json['results']), 4)

    def test_get(self):
        self.as_user()
        response = self.client.get('/v1/organisations/1/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual('QCIF', response.json['short_name'])
        self.assertNotIn('vetted_by', response.json.keys())
        self.assertNotIn('proposed_by', response.json.keys())
        self.assertTrue(response.json['vetted'])

    def test_get_as_approver(self):
        self.as_approver()
        response = self.client.get('/v1/organisations/1/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual('QCIF', response.json['short_name'])
        self.assertEqual(None, response.json['vetted_by'])
        self.assertEqual('', response.json['proposed_by'])

    def test_approve_anon(self):
        self.as_anon()
        response = self.client.post('/v1/organisations/1/approve/')
        self.assertEqual(response.status_code, 403)

    def test_approve_as_user(self):
        self.as_user()
        response = self.client.post('/v1/organisations/1/approve/')
        self.assertEqual(response.status_code, 403)

    def test_approve_as_admin(self):
        self.as_admin()
        org = factories.create_organisation(proposed_by="someone")
        response = self.client.post(f'/v1/organisations/{org.id}/approve/')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(response.json['enabled'])
        self.assertEqual(self.admin_approver.id, response.json['vetted_by'])
        self.assertEqual("someone", response.json['proposed_by'])
        self.assertTrue(response.json['vetted'])

    def test_approve_as_admin_bad(self):
        self.as_admin()
        org = factories.create_organisation(ror_id="https://xyz")
        response = self.client.post(f'/v1/organisations/{org.id}/approve/')
        self.assertEqual(response.status_code, 400)

    def test_approve_as_admin_unknown(self):
        self.as_admin()
        response = self.client.post('/v1/organisations/99/approve/')
        self.assertEqual(response.status_code, 404)

    def test_decline_anon(self):
        self.as_anon()
        response = self.client.post('/v1/organisations/1/decline/')
        self.assertEqual(response.status_code, 403)

    def test_decline_as_user(self):
        self.as_user()
        response = self.client.post('/v1/organisations/1/decline/')
        self.assertEqual(response.status_code, 403)

    def test_decline_as_admin(self):
        self.as_admin()
        org = factories.create_organisation(proposed_by="someone")
        response = self.client.post(f'/v1/organisations/{org.id}/decline/')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertFalse(response.json['enabled'])
        self.assertEqual(self.admin_approver.id, response.json['vetted_by'])
        self.assertEqual("someone", response.json['proposed_by'])

    def test_create_anon(self):
        self.as_anon()
        response = self.client.post('/v1/organisations/')
        self.assertEqual(response.status_code, 403)

    def test_create_as_admin(self):
        self.as_admin()
        data = self._make_data(
            url="https://www.uta.edu.au", ror_id="https://ror.org/spqr01"
        )
        response = self.client.post('/v1/organisations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        self._check_data(data, response.json)
        org = db.session.get(models.Organisation, response.json['id'])
        self.assertFalse(org.proposed_by)
        self.assertIsNone(org.vetted_by)

    def test_propose_as_user(self):
        self.as_user()
        data = self._make_data(url="https://www.uta.edu.au")
        response = self.client.post('/v1/organisations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        self._check_data(data, response.json)
        self.assertNotIn('vetted_by', response.json)
        self.assertNotIn('proposed_by', response.json)
        self.assertFalse(response.json['vetted'])
        org = db.session.get(models.Organisation, response.json['id'])
        self.assertEqual(common.USER["user_id"], org.proposed_by)
        self.assertIsNone(org.vetted_by)

    def test_propose_missing_field(self):
        self.as_user()
        data = self._make_data(
            short_name='WTF', full_name='', url='https://wtf.org'
        )
        response = self.client.post('/v1/organisations/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('full_name', response.json)

    def test_propose_bad_country(self):
        self.as_user()
        data = self._make_data(
            short_name='WTF',
            full_name='World Triffid Foundation',
            url='https://wtf.org',
            country='xx',
        )
        response = self.client.post('/v1/organisations/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('country', response.json)

    def test_propose_bad_url(self):
        self.as_user()
        data = self._make_data(
            short_name='WTF',
            full_name='World Triffid Foundation',
            url='not a url',
        )
        response = self.client.post('/v1/organisations/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('url', response.json)

    def test_propose_extra_fields(self):
        self.as_user()
        data = self._make_data(
            short_name='WTF',
            full_name='World Triffid Foundation',
            url='https://wtf.org',
            ror_id='https://ror.org/xyzzy',
            enabled=False,
        )
        response = self.client.post('/v1/organisations/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual('', response.json['ror_id'])
        self.assertTrue(response.json['enabled'])

    def test_propose_duplicate(self):
        self.as_user()
        data = self._make_data(
            short_name='QCIF',
            full_name='Queensland Cyber Infrastructure Foundation',
            url='https://qcif.edu.au',
        )
        response = self.client.post('/v1/organisations/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            {
                'full_name': [
                    'An Organisation with this full name already exists.'
                ]
            },
            response.json,
        )

    def test_propose_rejected(self):
        self.as_user()
        data = self._make_data(
            short_name='UWW',
            full_name='University of Woop Woop',
            url='https://uww.edu.au',
        )
        response = self.client.post('/v1/organisations/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            {
                'full_name': [
                    'An Organisation with this full name has already been '
                    'rejected.'
                ]
            },
            response.json,
        )

    def test_patch_as_anon(self):
        self.as_anon()
        data = self._make_data(url="https://www.uta.edu.au")
        response = self.client.patch('/v1/organisations/1/', data=data)
        self.assertEqual(response.status_code, 403)

    def test_patch_as_user(self):
        self.as_user()
        data = self._make_data(url="https://www.uta.edu.au")
        response = self.client.patch('/v1/organisations/1/', data=data)
        self.assertEqual(response.status_code, 403)

    def test_patch_as_admin(self):
        self.as_admin()
        data = self._make_data(url="https://www.uta.edu.au")
        response = self.client.patch('/v1/organisations/1/', data=data)
        self.assertEqual(response.status_code, 200, response.json)
        org = db.session.get(models.Organisation, 1)
        self.assertEqual("https://www.uta.edu.au", org.url)

    def test_patch_precedes(self):
        self.as_admin()
        response = self.client.patch(
            '/v1/organisations/1/', json={'precedes': [2], 'parent': 2}
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual([2], response.json['precedes'])
        self.assertEqual(2, response.json['parent'])
        response = self.client.get('/v1/organisations/2/')
        self.assertEqual([2], response.json['precedes'] or [2])

    def test_delete_as_admin(self):
        self.as_admin()
        response = self.client.delete('/v1/organisations/1/')
        self.assertEqual(response.status_code, 405)

    def test_filter_organisations(self):
        org1 = factories.create_organisation()
        factories.create_organisation()
        factories.create_organisation()
        self.as_anon()
        response = self.client.get('/v1/organisations/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json['results']), 7)
        response = self.client.get(
            f'/v1/organisations/?short_name={org1.short_name}'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json['results']), 1)
        self.assertEqual(
            response.json['results'][0]['full_name'], org1.full_name
        )

    def test_filter_iexact(self):
        self.as_anon()
        response = self.client.get(
            '/v1/organisations/?short_name__iexact=qcif'
        )
        self.assertEqual(1, response.json['count'])
        response = self.client.get(
            '/v1/organisations/?ror_id__iexact=HTTPS://ROR.ORG/12345678'
        )
        self.assertEqual(1, response.json['count'])

    def test_filter_search(self):
        self.as_anon()
        response = self.client.get('/v1/organisations/?search=monash')
        self.assertEqual(1, response.json['count'])
        response = self.client.get(
            '/v1/organisations/?search=university&exclude_all=true'
        )
        self.assertCountEqual(
            ['Monash University', 'University of Woop Woop'],
            [o['full_name'] for o in response.json['results']],
        )
        response = self.client.get('/v1/organisations/?vetted=false')
        self.assertCountEqual(
            ['UWW', 'all'],
            [o['short_name'] for o in response.json['results']],
        )

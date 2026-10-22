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

"""Reference data endpoints (ports of test_access_control, test_approvers,
test_bundles, test_facilities, test_sites, test_supports, test_zones)."""

from rcallocation.common import config
from rcallocation.extensions import db
from rcallocation import models
from rcallocation.tests.unit.api.v1 import common
from rcallocation.tests.unit import factories
from rcallocation.tests.unit import fixtures


class AccessControlTest(common.AllocationApiTestCase):
    endpoints = [
        'ncris-facilities',
        'zones',
        'service-types',
        'sites',
        'ardc-projects',
        'resources',
        'bundles',
        'usage-types',
    ]

    def test_list(self):
        self.as_user()
        for e in self.endpoints:
            response = self.client.get(f'/v1/{e}/')
            self.assertEqual(response.status_code, 200, e)

    def test_list_unauthenticated(self):
        self.as_anon()
        for e in self.endpoints:
            response = self.client.get(f'/v1/{e}/')
            self.assertEqual(response.status_code, 200, e)

    def test_create_no_permission(self):
        self.as_user()
        for e in self.endpoints:
            response = self.client.post(f'/v1/{e}/', data={})
            self.assertEqual(response.status_code, 403, e)

    def test_update_no_permission(self):
        self.as_user()
        for e in self.endpoints:
            response = self.client.patch(f'/v1/{e}/xxx/', data={})
            self.assertEqual(response.status_code, 403, e)

    def test_update_unknown(self):
        self.as_admin()
        for e in self.endpoints:
            response = self.client.patch(f'/v1/{e}/xxx/', data={})
            self.assertEqual(response.status_code, 404, e)

    def test_delete(self):
        self.as_admin()
        for e in self.endpoints:
            response = self.client.delete(f'/v1/{e}/XXX/')
            self.assertEqual(response.status_code, 405, e)

    def test_delete_no_permission(self):
        self.as_user()
        for e in self.endpoints:
            response = self.client.delete(f'/v1/{e}/XXX/')
            self.assertEqual(response.status_code, 403, e)


class ApproverTest(common.AllocationApiTestCase):
    def setUp(self):
        super().setUp()
        self.qcif = factories.get(models.Site, name='qcif')
        self.uom = factories.get(models.Site, name='uom')
        # Delete all the existing approvers setup in base
        for approver in db.session.query(models.Approver).all():
            db.session.delete(approver)
        db.session.commit()
        self.assertEqual(db.session.query(models.Approver).count(), 0)
        self.jim = factories.create_approver(
            'jim.spriggs@uq.edu.au', 'Jim Spriggs', sites=[self.qcif]
        )

    def test_list_approvers(self):
        self.as_admin()
        response = self.client.get('/v1/approvers/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json['results']), 1)
        self.assertEqual(
            {
                'id': self.jim.id,
                'username': 'jim.spriggs@uq.edu.au',
                'display_name': 'Jim Spriggs',
                'sites': [self.qcif.id],
            },
            response.json['results'][0],
        )

    def test_list_approvers_as_approver(self):
        self.as_approver()
        response = self.client.get('/v1/approvers/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json['results']), 1)

    def test_list_approvers_unauthenticated(self):
        self.as_anon()
        response = self.client.get('/v1/approvers/')
        self.assertEqual(response.status_code, 403)

    def test_list_approvers_as_user(self):
        self.as_user()
        response = self.client.get('/v1/approvers/')
        self.assertEqual(response.status_code, 403)

    def test_filter_username(self):
        self.as_admin()
        response = self.client.get(
            '/v1/approvers/?username=jim.spriggs@uq.edu.au'
        )
        self.assertEqual(1, response.json['count'])
        response = self.client.get('/v1/approvers/?username=nobody')
        self.assertEqual(0, response.json['count'])

    def test_create_approver(self):
        data = {
            'username': 'joe.bloggs@uq.edu.au',
            'display_name': 'Joseph Bloggs',
            'sites': [self.qcif.id],
        }
        self.as_admin()
        response = self.client.post('/v1/approvers/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        joe = factories.get(models.Approver, username='joe.bloggs@uq.edu.au')
        self.assertEqual(joe.display_name, 'Joseph Bloggs')
        self.assertEqual([self.qcif.id], [s.id for s in joe.sites])

    def test_create_approver_no_permission(self):
        self.as_user()
        response = self.client.post('/v1/approvers/', data={'name': 'darwin'})
        self.assertEqual(response.status_code, 403)

    def test_create_approver_duplicate(self):
        data = {
            'username': 'jim.spriggs@uq.edu.au',
            'display_name': 'Joseph Bloggs',
            'sites': [self.qcif.id],
        }
        self.as_admin()
        response = self.client.post('/v1/approvers/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            {'username': ['approver with this username already exists.']},
            response.json,
        )

    def test_update_approver(self):
        self.as_admin()
        data = {
            'display_name': 'Adolphus Spriggs',
            'sites': [self.qcif.id, self.uom.id],
        }
        response = self.client.patch(
            f'/v1/approvers/{self.jim.id}/', data=data
        )
        self.assertEqual(response.status_code, 200, response.json)
        jim = factories.refresh(self.jim)
        self.assertEqual(jim.display_name, 'Adolphus Spriggs')
        self.assertCountEqual(
            [self.qcif.id, self.uom.id], [s.id for s in jim.sites]
        )

    def test_delete_approver(self):
        self.as_admin()
        response = self.client.delete(f'/v1/approvers/{self.jim.id}/')
        self.assertEqual(response.status_code, 405)


class BundleTest(common.AllocationApiTestCase):
    def setUp(self):
        super().setUp()
        self.bundle = factories.get(models.Bundle, name='gold')

    def test_list_bundles(self):
        self.as_user()
        response = self.client.get('/v1/bundles/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(3, len(response.json['results']))

    def test_list_bundles_unauthenticated(self):
        self.as_anon()
        response = self.client.get('/v1/bundles/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(3, len(response.json['results']))

    def test_get_bundle(self):
        self.as_user()
        response = self.client.get(f'/v1/bundles/{self.bundle.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.bundle.id, response.json['id'])
        self.assertEqual(self.bundle.name, response.json['name'])
        self.assertEqual(self.bundle.description, response.json['description'])
        self.assertEqual('nectar', response.json['zone'])
        self.assertEqual(self.bundle.quota_list(), response.json['quotas'])
        self.assertEqual(
            {
                'zone': 'nectar',
                'resource': 'object.object',
                'quota': 200,
                'requested_quota': 200,
            },
            response.json['quotas'][0],
        )

    def test_create_bundle(self):
        self.as_admin()
        data = {
            'name': 'platinum',
            'description': 'lots and lots',
            'zone': 'nectar',
            'su_per_year': 20000,
            'order': 10,
        }
        response = self.client.post('/v1/bundles/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        b = factories.get(models.Bundle, name='platinum')
        self.assertEqual(data['description'], b.description)
        self.assertEqual('nectar', b.zone.name)
        self.assertEqual(10, b.order)
        self.assertEqual([], response.json['quotas'])

    def test_create_bundle_bad_zone(self):
        self.as_admin()
        data = {
            'name': 'platinum',
            'description': 'lots and lots',
            'zone': 'nowhere',
            'su_per_year': 20000,
            'order': 10,
        }
        response = self.client.post('/v1/bundles/', data=data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('zone', response.json)

    def test_update_bundle(self):
        self.as_admin()
        response = self.client.patch(
            f'/v1/bundles/{self.bundle.id}/', data={'description': 'Very good'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            'Very good', factories.refresh(self.bundle).description
        )

    def test_delete_bundle(self):
        self.as_admin()
        response = self.client.delete(f'/v1/bundles/{self.bundle.id}/')
        self.assertEqual(response.status_code, 405)


class FacilitiesTest(common.AllocationApiTestCase):
    def setUp(self):
        super().setUp()
        self.ala = factories.get(models.NCRISFacility, short_name='ALA')

    def test_list_facilities(self):
        self.as_user()
        response = self.client.get('/v1/ncris-facilities/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(fixtures.NCRIS_FACILITIES), len(response.json['results'])
        )

    def test_list_facilities_unauthenticated(self):
        self.as_anon()
        response = self.client.get('/v1/ncris-facilities/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(fixtures.NCRIS_FACILITIES), len(response.json['results'])
        )

    def test_get_facility(self):
        self.as_anon()
        response = self.client.get(f'/v1/ncris-facilities/{self.ala.id}/')
        self.assertEqual(
            {
                'id': self.ala.id,
                'name': 'Atlas of Living Australia',
                'short_name': 'ALA',
            },
            response.json,
        )

    def test_create_facility_no_permission(self):
        self.as_user()
        response = self.client.post(
            '/v1/ncris-facilities/', data={'name': 'Applied Magic Facility'}
        )
        self.assertEqual(response.status_code, 403)

    def test_create_facility_duplicate(self):
        self.as_admin()
        response = self.client.post(
            '/v1/ncris-facilities/',
            data={'name': 'Astronomy Australia Ltd', 'short_name': 'AAL2'},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('name', response.json)

    def test_create_facility(self):
        self.as_admin()
        response = self.client.post(
            '/v1/ncris-facilities/',
            data={'name': 'Applied Magic Facility', 'short_name': 'AMF'},
        )
        self.assertEqual(response.status_code, 201, response.json)

    def test_update_facility(self):
        self.as_admin()
        response = self.client.patch(
            f'/v1/ncris-facilities/{self.ala.id}/',
            data={'name': 'Atlas of Lovely Australia'},
        )
        self.assertEqual(response.status_code, 200, response.json)

    def test_delete_facility(self):
        self.as_admin()
        response = self.client.delete(f'/v1/ncris-facilities/{self.ala.id}/')
        self.assertEqual(response.status_code, 405)


class SiteTest(common.AllocationApiTestCase):
    def setUp(self):
        super().setUp()
        self.uom = factories.get(models.Site, name='uom')

    def test_list_sites(self):
        self.as_user()
        response = self.client.get('/v1/sites/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(factories.ALL_SITES), len(response.json['results'])
        )

    def test_list_sites_unauthenticated(self):
        self.as_anon()
        response = self.client.get('/v1/sites/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(factories.ALL_SITES), len(response.json['results'])
        )

    def test_create_site_no_permission(self):
        self.as_user()
        response = self.client.post('/v1/sites/', data={'name': 'darwin'})
        self.assertEqual(response.status_code, 403)

    def test_create_site_duplicate(self):
        self.as_admin()
        response = self.client.post(
            '/v1/sites/', data={'name': 'uom', 'display_name': 'Melbourne'}
        )
        self.assertEqual(response.status_code, 400)

    def test_create_site(self):
        self.as_admin()
        response = self.client.post(
            '/v1/sites/',
            data={'name': 'darwin', 'display_name': 'Darwin University'},
        )
        self.assertEqual(response.status_code, 201, response.json)
        self.assertTrue(response.json['enabled'])

    def test_update_site(self):
        self.as_admin()
        response = self.client.patch(
            f'/v1/sites/{self.uom.id}/',
            data={'display_name': 'University of Darwin'},
        )
        self.assertEqual(response.status_code, 200)

    def test_delete_site(self):
        self.as_admin()
        response = self.client.delete(f'/v1/sites/{self.uom.id}/')
        self.assertEqual(response.status_code, 405)


class SupportsTest(common.AllocationApiTestCase):
    def setUp(self):
        super().setUp()
        self.cvl = factories.get(models.ARDCSupport, short_name='CVL')

    def test_list_projects(self):
        self.as_user()
        response = self.client.get('/v1/ardc-projects/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(fixtures.ARDC_SUPPORT), len(response.json['results'])
        )

    def test_list_projects_unauthenticated(self):
        self.as_anon()
        response = self.client.get('/v1/ardc-projects/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(fixtures.ARDC_SUPPORT), len(response.json['results'])
        )

    def test_list_projects_filter_enabled(self):
        cvl = factories.refresh(self.cvl)
        cvl.enabled = False
        db.session.commit()
        self.as_user()
        response = self.client.get('/v1/ardc-projects/?enabled=true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(fixtures.ARDC_SUPPORT) - 1, len(response.json['results'])
        )
        response = self.client.get('/v1/ardc-projects/?enabled=false')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json['results']))

    def test_create_project_no_permission(self):
        self.as_user()
        response = self.client.post(
            '/v1/ardc-projects/', data={'name': 'Applied Magic Project'}
        )
        self.assertEqual(response.status_code, 403)

    def test_create_project_duplicate(self):
        self.as_admin()
        response = self.client.post(
            '/v1/ardc-projects/',
            data={
                'name': 'Characterization Virtual Laboratory',
                'short_name': 'CVL2',
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_create_project(self):
        self.as_admin()
        data = {
            'name': 'Applied Magic Project',
            'short_name': 'AMF',
            'rank': 50,
        }
        response = self.client.post('/v1/ardc-projects/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(50, response.json['rank'])
        self.assertTrue(response.json['project'])

    def test_update_project(self):
        self.as_admin()
        response = self.client.patch(
            f'/v1/ardc-projects/{self.cvl.id}/',
            data={'name': 'Chimeric Virtual Laboratory'},
        )
        self.assertEqual(response.status_code, 200, response.json)

    def test_delete_project(self):
        self.as_admin()
        response = self.client.delete(f'/v1/ardc-projects/{self.cvl.id}/')
        self.assertEqual(response.status_code, 405)


class ZoneTests(common.AllocationApiTestCase):
    def test_compute_homes(self):
        self.as_anon()
        response = self.client.get('/v1/zones/compute_homes/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(config.get_mappings().home_zones, response.json)

    def test_list_and_get(self):
        self.as_anon()
        response = self.client.get('/v1/zones/')
        self.assertEqual(7, response.json['count'])
        response = self.client.get('/v1/zones/melbourne/')
        self.assertEqual(
            {
                'name': 'melbourne',
                'display_name': 'melbourne',
                'enabled': True,
            },
            response.json,
        )

    def test_create_and_update(self):
        self.as_admin()
        response = self.client.post(
            '/v1/zones/', data={'name': 'perth', 'display_name': 'Perth'}
        )
        self.assertEqual(response.status_code, 201, response.json)
        response = self.client.patch(
            '/v1/zones/perth/', data={'enabled': 'False'}
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertFalse(response.json['enabled'])


class ServiceTypeTests(common.AllocationApiTestCase):
    def test_get(self):
        self.as_anon()
        response = self.client.get('/v1/service-types/compute/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual('compute', response.json['catalog_name'])
        self.assertEqual(['nectar'], response.json['zones'])
        self.assertEqual(
            ['cores', 'instances', 'ram'],
            [r['quota_name'] for r in response.json['resource_set']],
        )
        self.assertEqual(
            'compute', response.json['resource_set'][0]['service_type']
        )

    def test_create(self):
        self.as_admin()
        data = {
            'catalog_name': 'dns',
            'name': 'DNS',
            'zones': ['nectar'],
            'order': 5,
        }
        response = self.client.post('/v1/service-types/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual(['nectar'], response.json['zones'])
        self.assertEqual([], response.json['resource_set'])


class ResourceTests(common.AllocationApiTestCase):
    def test_list_filter(self):
        self.as_anon()
        response = self.client.get('/v1/resources/?service_type=compute')
        self.assertEqual(3, response.json['count'])

    def test_create(self):
        self.as_admin()
        data = {
            'name': 'Zones',
            'service_type': 'network',
            'quota_name': 'zones',
            'unit': 'zones',
        }
        response = self.client.post('/v1/resources/', data=data)
        self.assertEqual(response.status_code, 201, response.json)
        self.assertEqual('integer', response.json['resource_type'])
        self.assertEqual('network', response.json['service_type'])

    def test_create_duplicate(self):
        self.as_admin()
        data = {
            'name': 'Cores',
            'service_type': 'compute',
            'quota_name': 'cores',
            'unit': 'cores',
        }
        response = self.client.post('/v1/resources/', data=data)
        self.assertEqual(response.status_code, 400)


class UsageTypeTests(common.AllocationApiTestCase):
    def test_list(self):
        self.as_anon()
        response = self.client.get('/v1/usage-types/')
        self.assertEqual(len(fixtures.USAGE_TYPES) + 1, response.json['count'])
        response = self.client.get('/v1/usage-types/?enabled=true')
        self.assertEqual(len(fixtures.USAGE_TYPES), response.json['count'])
        self.assertEqual(
            {'id', 'name', 'enabled'}, set(response.json['results'][0])
        )

    def test_create(self):
        self.as_admin()
        response = self.client.post(
            '/v1/usage-types/', data={'name': 'Teaching'}
        )
        self.assertEqual(response.status_code, 201, response.json)
        self.assertTrue(response.json['enabled'])

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

from rcallocation import choices
from rcallocation.extensions import db
from rcallocation import models
from rcallocation.tests.unit.api.v1 import common
from rcallocation.tests.unit import factories


class QuotaTests(common.AllocationApiTestCase):
    def setUp(self):
        super().setUp()
        self.zone = factories.create_zone('testzone')
        self.service_type = factories.create_service_type(
            'test_st', zones=[self.zone]
        )
        self.resource = factories.create_resource(
            'test_resource', self.service_type
        )
        self.quota_group = factories.create_quota_group(
            self.allocation, self.service_type, self.zone
        )
        self.quota = factories.create_quota(self.quota_group, self.resource)

    def _quota_count(self, **filters):
        query = db.session.query(models.Quota).join(models.Quota.group)
        if 'contact_email' in filters:
            query = query.join(models.QuotaGroup.allocation).filter(
                models.AllocationRequest.contact_email
                == filters['contact_email']
            )
        if 'allocation' in filters:
            query = query.filter(
                models.QuotaGroup.allocation_id == filters['allocation'].id
            )
        return query.count()

    def test_list_quotas(self):
        self.as_user()
        factories.create_allocation(
            contact_email=common.USER["user_name"], create_quotas=True
        )
        response = self.client.get('/v1/quotas/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._quota_count(contact_email=common.USER["user_name"]),
            len(response.json['results']),
        )

    def test_list_quotas_for_allocation(self):
        self.as_user()
        factories.create_allocation(
            contact_email=common.USER["user_name"], create_quotas=True
        )
        factories.create_allocation(contact_email='otheruser')
        factories.create_allocation(contact_email='otheruser2')
        response = self.client.get(
            f'/v1/quotas/?group__allocation={self.allocation.id}'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._quota_count(allocation=self.allocation),
            len(response.json['results']),
        )

    def test_list_quotas_unauthenticated(self):
        self.as_anon()
        response = self.client.get('/v1/quotas/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            db.session.query(models.Quota).count(),
            len(response.json['results']),
        )

    def test_list_quotas_negative(self):
        self.as_user()
        factories.create_allocation(contact_email='other@example.com')
        response = self.client.get('/v1/quotas/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._quota_count(contact_email=common.USER["user_name"]),
            len(response.json['results']),
        )

    def test_list_quotas_admin(self):
        self.as_admin()
        factories.create_allocation(contact_email='foo@example.com')
        factories.create_allocation(contact_email='bar@example.com')
        response = self.client.get('/v1/quotas/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            db.session.query(models.Quota).count(),
            len(response.json['results']),
        )

    def test_get_quota(self):
        self.as_user()
        response = self.client.get(f'/v1/quotas/{self.quota.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.quota.id, response.json['id'])
        self.assertEqual(
            {
                'id': self.quota.id,
                'zone': 'testzone',
                'allocation': self.allocation.id,
                'requested_quota': self.quota.requested_quota,
                'quota': 0,
                'resource': self.resource.id,
            },
            response.json,
        )

    def test_get_quota_unauthenticated(self):
        self.as_anon()
        response = self.client.get(f'/v1/quotas/{self.quota.id}/')
        self.assertEqual(response.status_code, 200)

    def test_get_quota_negative(self):
        self.as_user2()
        response = self.client.get(f'/v1/quotas/{self.quota.id}/')
        self.assertEqual(response.status_code, 404)

    def test_get_quota_admin(self):
        self.as_admin()
        response = self.client.get(f'/v1/quotas/{self.quota.id}/')
        self.assertEqual(response.status_code, 200)

    def test_update_quota(self):
        self.as_admin()
        response = self.client.patch(
            f'/v1/quotas/{self.quota.id}/', data={'resource': 4}
        )
        self.assertEqual(response.status_code, 405)

    def test_delete_quota(self):
        self.as_user()
        response = self.client.delete(f'/v1/quotas/{self.quota.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(db.session.get(models.Quota, self.quota.id))

    def test_delete_quota_invalid_state(self):
        self.as_user()
        allocation = factories.refresh(self.allocation)
        allocation.status = choices.APPROVED
        db.session.commit()
        response = self.client.delete(f'/v1/quotas/{self.quota.id}/')
        self.assertEqual(response.status_code, 403)

    def test_delete_quota_negative(self):
        self.as_user2()
        response = self.client.delete(f'/v1/quotas/{self.quota.id}/')
        self.assertEqual(response.status_code, 404)

    def test_delete_quota_approver(self):
        self.as_approver()
        response = self.client.delete(f'/v1/quotas/{self.quota.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(db.session.get(models.Quota, self.quota.id))

    def test_delete_quota_admin(self):
        self.as_admin()
        response = self.client.delete(f'/v1/quotas/{self.quota.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(db.session.get(models.Quota, self.quota.id))

    def test_delete_quota_project_admin_role(self):
        # The keystone admin role on a project grants nothing here; the
        # quota is not visible to a non-owner so the answer is 404.
        self.persona(dict(common.USER2, roles=['member', 'admin']))
        response = self.client.delete(f'/v1/quotas/{self.quota.id}/')
        self.assertEqual(response.status_code, 404)
        self.assertIsNotNone(db.session.get(models.Quota, self.quota.id))

    def test_delete_quota_unauthenticated(self):
        # Closed: anonymous callers could delete quotas in the old API.
        self.as_anon()
        response = self.client.delete(f'/v1/quotas/{self.quota.id}/')
        self.assertEqual(response.status_code, 403)

    def _data(self, resource, **overrides):
        data = {
            'allocation': self.allocation.id,
            'resource': resource.id,
            'zone': self.zone.name,
            'quota': 20,
            'requested_quota': 10,
        }
        data.update(overrides)
        return data

    def test_create(self):
        self.as_user()
        resource = factories.create_resource(
            'test_resource2', self.service_type
        )
        response = self.client.post('/v1/quotas/', data=self._data(resource))
        self.assertEqual(response.status_code, 201, response.json)
        quota = db.session.get(models.Quota, response.json['id'])
        # Use the same service type to quota group should be existing
        self.assertEqual(self.quota_group.id, quota.group_id)
        self.assertEqual(20, quota.quota)
        self.assertEqual(10, quota.requested_quota)

    def test_create_unlimited_managed(self):
        self.as_user()
        resource = factories.create_resource(
            'test_resource2', self.service_type
        )
        response = self.client.post(
            '/v1/quotas/',
            data=self._data(resource, quota=-1, requested_quota=-1),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            ["Unlimited quota not allowed for managed allocation"],
            response.json,
        )

    def test_create_unlimited_unmanaged(self):
        self.as_user()
        resource = factories.create_resource(
            'test_resource2', self.service_type
        )
        allocation = factories.refresh(self.allocation)
        allocation.managed = False
        db.session.commit()
        response = self.client.post(
            '/v1/quotas/',
            data=self._data(resource, quota=-1, requested_quota=-1),
        )
        self.assertEqual(response.status_code, 201, response.json)
        quota = db.session.get(models.Quota, response.json['id'])
        self.assertEqual(self.quota_group.id, quota.group_id)

    def test_create_approver(self):
        self.as_approver()
        resource = factories.create_resource(
            'test_resource2', self.service_type
        )
        response = self.client.post('/v1/quotas/', data=self._data(resource))
        self.assertEqual(response.status_code, 201, response.json)
        quota = db.session.get(models.Quota, response.json['id'])
        self.assertEqual(self.quota_group.id, quota.group_id)

    def test_create_invalid_requested_quota(self):
        self.as_user()
        resource = factories.create_resource(
            'test_resource2', self.service_type
        )
        response = self.client.post(
            '/v1/quotas/', data=self._data(resource, requested_quota=-2)
        )
        self.assertEqual(response.status_code, 400)

    def test_create_invalid_quota(self):
        self.as_user()
        resource = factories.create_resource(
            'test_resource2', self.service_type
        )
        response = self.client.post(
            '/v1/quotas/', data=self._data(resource, quota=-2)
        )
        self.assertEqual(response.status_code, 400)

    def test_create_duplicate(self):
        self.as_user()
        response = self.client.post(
            '/v1/quotas/', data=self._data(self.resource)
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(["Duplicate quota resource"], response.json)

    def test_create_invalid_zone(self):
        zone = factories.create_zone('testzone2')
        self.as_user()
        response = self.client.post(
            '/v1/quotas/', data=self._data(self.resource, zone=zone.name)
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            ["Resource not available in this zone"], response.json
        )

    def test_create_unknown_zone(self):
        self.as_user()
        response = self.client.post(
            '/v1/quotas/', data=self._data(self.resource, zone='nowhere')
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(["Zone does not exist"], response.json)

    def test_create_wrong_state(self):
        self.as_user()
        allocation = factories.refresh(self.allocation)
        allocation.status = choices.APPROVED
        db.session.commit()
        resource = factories.create_resource(
            'test_resource2', self.service_type
        )
        response = self.client.post('/v1/quotas/', data=self._data(resource))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            ["Allocation quota in status 'Approved' can not be updated"],
            response.json,
        )

    def test_create_other_users_allocation(self):
        self.as_user2()
        resource = factories.create_resource(
            'test_resource2', self.service_type
        )
        response = self.client.post('/v1/quotas/', data=self._data(resource))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(["Allocation does not exist"], response.json)

    def test_create_unauthenticated(self):
        self.as_anon()
        resource = factories.create_resource(
            'test_resource2', self.service_type
        )
        response = self.client.post('/v1/quotas/', data=self._data(resource))
        self.assertEqual(response.status_code, 403)

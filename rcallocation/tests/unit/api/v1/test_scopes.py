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

"""Project scoped reads and system scoped tokens (ports of
test_project_scoped_reads and test_system_scope)."""

from unittest import mock

from rcallocation import choices
from rcallocation.extensions import db
from rcallocation import models
from rcallocation.tests.unit.api.v1 import common
from rcallocation.tests.unit import factories


class ProjectScopedReadTests(common.AllocationApiTestCase):
    """A project member may read the approved allocation of the project
    their token is scoped to, not only the requests they are the contact
    for. The new dashboard reads the SU budget and quotas this way with the
    user's own token.
    """

    def setUp(self):
        super().setUp()
        # proj2's approved allocation, whose contact is somebody else.
        self.project_allocation = factories.create_allocation(
            contact_email='someone-else@example.com',
            project_id='idproj2',
            project_name='proj2',
            status=choices.APPROVED,
        )
        # A pending request for the same project is still private.
        self.pending = factories.create_allocation(
            contact_email='someone-else@example.com',
            project_id='idproj2',
            project_name='proj2-pending',
            status=choices.SUBMITTED,
        )
        self.contact = {
            "user_id": "contact",
            "user_name": "someone-else@example.com",
            "project_id": "idunrelated",
            "roles": ["member"],
        }

    def test_member_sees_own_project_approved_allocation(self):
        self.as_user2()
        ids = self.ids(self.client.get('/v1/allocations/'))
        self.assertIn(self.project_allocation.id, ids)
        self.assertNotIn(self.pending.id, ids)
        self.assertNotIn(self.allocation.id, ids)

    def test_member_can_filter_by_project_id(self):
        self.as_user2()
        ids = self.ids(
            self.client.get('/v1/allocations/?project_id=idproj2&status=A')
        )
        self.assertEqual({self.project_allocation.id}, ids)

    def test_member_can_retrieve_it(self):
        self.as_user2()
        response = self.client.get(
            f'/v1/allocations/{self.project_allocation.id}/'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['project_id'], 'idproj2')

    def test_other_project_member_cannot_see_it(self):
        self.as_user()
        ids = self.ids(self.client.get('/v1/allocations/'))
        self.assertNotIn(self.project_allocation.id, ids)
        self.assertNotIn(self.pending.id, ids)
        # Their own request is still there.
        self.assertIn(self.allocation.id, ids)
        response = self.client.get(
            f'/v1/allocations/{self.project_allocation.id}/'
        )
        self.assertEqual(response.status_code, 404)

    def test_contact_still_sees_pending_requests(self):
        self.persona(self.contact)
        ids = self.ids(self.client.get('/v1/allocations/'))
        self.assertEqual({self.project_allocation.id, self.pending.id}, ids)

    def test_member_cannot_update_project_allocation(self):
        self.as_user2()
        response = self.client.patch(
            f'/v1/allocations/{self.project_allocation.id}/',
            json={'use_case': 'changed'},
        )
        self.assertIn(response.status_code, (403, 404))

    def test_quotas_follow_allocation_visibility(self):
        quota = (
            db.session.query(models.Quota)
            .join(models.Quota.group)
            .filter(
                models.QuotaGroup.allocation_id == self.project_allocation.id
            )
            .first()
        )
        self.assertIsNotNone(quota, "factory should create quotas")
        pending_quota = (
            db.session.query(models.Quota)
            .join(models.Quota.group)
            .filter(models.QuotaGroup.allocation_id == self.pending.id)
            .first()
        )

        self.as_user2()
        ids = self.ids(self.client.get('/v1/quotas/'))
        self.assertIn(quota.id, ids)
        self.assertNotIn(pending_quota.id, ids)

        self.as_user()
        ids = self.ids(self.client.get('/v1/quotas/'))
        self.assertNotIn(quota.id, ids)

    def test_mine_filter(self):
        self.as_user2()
        ids = self.ids(self.client.get('/v1/allocations/?mine=true'))
        self.assertEqual({self.project_allocation.id}, ids)
        # Admins asking for "mine" get their own view, not everything.
        self.persona(dict(common.ADMIN, project_id='idproj2'))
        ids = self.ids(self.client.get('/v1/allocations/'))
        self.assertEqual(3, len(ids))
        ids = self.ids(self.client.get('/v1/allocations/?mine=true'))
        self.assertEqual({self.project_allocation.id}, ids)

    @mock.patch('rcallocation.common.projects.managed_project_ids')
    def test_tenant_manager_sees_managed_projects(self, managed):
        managed.return_value = {'idproj2'}
        self.as_user()
        ids = self.ids(self.client.get('/v1/allocations/'))
        # Every allocation of a managed project, pending ones included.
        self.assertEqual(
            {self.allocation.id, self.project_allocation.id, self.pending.id},
            ids,
        )
        managed.assert_called_with(common.USER["user_id"])
        # ... and may amend the approved one as an owner.
        response = self.client.post(
            f'/v1/allocations/{self.project_allocation.id}/amend/'
        )
        self.assertEqual(response.status_code, 200, response.json)


class SystemScopeAllocationTests(common.AllocationApiTestCase):
    def test_list_allocations_system_admin(self):
        self.as_system_admin()
        response = self.client.get('/v1/allocations/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json['results']))
        # Admin serializer exposes admin-only fields
        self.assertIn('notes', response.json['results'][0])

    def test_list_allocations_system_reader(self):
        self.as_system_reader()
        response = self.client.get('/v1/allocations/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, len(response.json['results']))
        self.assertIn('notes', response.json['results'][0])

    def test_list_allocations_system_member(self):
        # No matching system role: sees only allocations it owns
        self.as_system_member()
        response = self.client.get('/v1/allocations/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(0, len(response.json['results']))

    def test_get_allocation_system_member(self):
        self.as_system_member()
        response = self.client.get(f'/v1/allocations/{self.allocation.id}/')
        self.assertEqual(response.status_code, 404)

    def test_update_allocation_system_admin(self):
        self.as_system_admin()
        response = self.client.patch(
            f'/v1/allocations/{self.allocation.id}/',
            data={'use_case': 'test-update'},
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(
            'test-update', factories.refresh(self.allocation).use_case
        )

    def test_update_allocation_admin_field_system_admin(self):
        self.as_system_admin()
        response = self.client.patch(
            f'/v1/allocations/{self.allocation.id}/', data={'national': True}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(factories.refresh(self.allocation).national)

    def test_update_allocation_admin_field_system_member(self):
        self.as_system_member()
        response = self.client.patch(
            f'/v1/allocations/{self.allocation.id}/', data={'national': True}
        )
        self.assertEqual(response.status_code, 404)

    def test_system_reader_cannot_update(self):
        self.as_system_reader()
        response = self.client.patch(
            f'/v1/allocations/{self.allocation.id}/',
            data={'use_case': 'test-update'},
        )
        self.assertEqual(response.status_code, 403)

    def test_approve_system_approver(self):
        self.as_system_approver()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/approve/'
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(choices.APPROVED, response.json['status'])
        self.assertEqual(
            common.SYSTEM_APPROVER["user_name"],
            factories.refresh(self.allocation).approver_email,
        )

    def test_approve_system_admin(self):
        # As at project scope, the admin role alone cannot approve
        self.as_system_admin()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/approve/'
        )
        self.assertEqual(response.status_code, 403)

    def test_approve_system_reader(self):
        self.as_system_reader()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/approve/'
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_system_admin(self):
        self.as_system_admin()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/delete/'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(choices.DELETED, response.json['status'])

    def test_delete_system_reader(self):
        self.as_system_reader()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/delete/'
        )
        self.assertEqual(response.status_code, 403)

    def test_create_system_admin(self):
        self.as_system_admin()
        response = self.client.post(
            '/v1/allocations/',
            data={
                'project_name': 'system-test-project',
                'project_description': 'project for testing',
                'start_date': '2000-01-01',
                'use_case': 'for testing',
                'usage_types': ['Other'],
                'supported_organisations': ['https://ror.org/12345678'],
            },
        )
        self.assertEqual(response.status_code, 201, response.json)
        allocation = factories.get(
            models.AllocationRequest, project_name='system-test-project'
        )
        self.assertEqual(common.SYSTEM_ADMIN["user_id"], allocation.created_by)
        self.assertEqual(
            common.SYSTEM_ADMIN["user_name"], response.json['contact_email']
        )

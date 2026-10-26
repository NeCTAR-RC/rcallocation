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

"""The endpoints added for the dashboard: decline, submit, approve and
amend with bodies, checks, nested writes and approver info on lists."""

import datetime

from rcallocation import checkers
from rcallocation import choices
from rcallocation.extensions import db
from rcallocation import models
from rcallocation.tests.unit.api.v1 import common
from rcallocation.tests.unit import factories


def quota_map(allocation):
    return {
        (q.resource.codename, q.group.zone_id): (q.requested_quota, q.quota)
        for q in allocation.all_quotas()
    }


class DeclineTests(common.AllocationApiTestCase):
    def test_decline(self):
        self.as_approver()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/decline/',
            json={'status_explanation': 'Not enough detail'},
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(choices.DECLINED, response.json['status'])
        self.assertEqual(
            'Not enough detail', response.json['status_explanation']
        )
        allocation = factories.refresh(self.allocation)
        self.assertEqual(
            common.APPROVER["user_name"], allocation.approver_email
        )
        self.assertEqual(1, factories.history_count(allocation))

    def test_decline_amendment(self):
        self.as_approver()
        allocation = factories.create_allocation(status=choices.UPDATE_PENDING)
        response = self.client.post(
            f'/v1/allocations/{allocation.id}/decline/',
            data={'reason': 'No'},
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(choices.UPDATE_DECLINED, response.json['status'])
        self.assertEqual('No', response.json['status_explanation'])

    def test_decline_no_body(self):
        self.as_approver()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/decline/'
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(choices.DECLINED, response.json['status'])

    def test_decline_wrong_state(self):
        self.as_approver()
        allocation = factories.create_allocation(status=choices.APPROVED)
        response = self.client.post(
            f'/v1/allocations/{allocation.id}/decline/'
        )
        self.assertEqual(response.status_code, 403)

    def test_decline_as_user(self):
        self.as_user()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/decline/'
        )
        self.assertEqual(response.status_code, 403)

    def test_decline_as_admin(self):
        self.as_admin()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/decline/'
        )
        self.assertEqual(response.status_code, 403)


class SubmitTests(common.AllocationApiTestCase):
    def _body(self, **extra):
        body = {
            'use_case': 'A better use case',
            'investigators': [
                {
                    'title': 'Dr',
                    'given_name': 'Ada',
                    'surname': 'Lovelace',
                    'email': 'ada@unimelb.edu.au',
                    'primary_organisation': 'Monash',
                }
            ],
            'grants': [
                {
                    'grant_type': 'arc',
                    'grant_subtype': 'arc-discovery',
                    'first_year_funded': 2024,
                    'last_year_funded': 2026,
                    'total_funding': 1000,
                }
            ],
            'publications': [
                {'output_type': 'AJ', 'doi': '10.1234/xyz', 'publication': ''}
            ],
            'quotas': [
                {
                    'zone': 'nectar',
                    'resource': 'compute.cores',
                    'requested_quota': 8,
                },
                {
                    'zone': 'melbourne',
                    'resource': 'volume.gigabytes',
                    'requested_quota': 100,
                },
            ],
        }
        body.update(extra)
        return body

    def test_submit(self):
        self.as_user()
        before = factories.refresh(self.allocation).submit_date
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/submit/', json=self._body()
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(choices.SUBMITTED, response.json['status'])
        self.assertEqual('A better use case', response.json['use_case'])
        allocation = factories.refresh(self.allocation)
        self.assertEqual(1, factories.history_count(allocation))
        self.assertGreater(allocation.submit_date, before)
        self.assertEqual(
            ['ada@unimelb.edu.au'], [i.email for i in allocation.investigators]
        )
        self.assertEqual(['arc'], [g.grant_type for g in allocation.grants])
        self.assertEqual(
            ['10.1234/xyz'], [p.doi for p in allocation.publications]
        )
        # Quotas are a full replacement
        self.assertEqual(
            {
                ('compute.cores', 'nectar'): (8, 0),
                ('volume.gigabytes', 'melbourne'): (100, 0),
            },
            quota_map(allocation),
        )
        self.assertFalse(allocation.provisioned)

    def test_submit_resubmits_declined(self):
        self.as_user()
        allocation = factories.create_allocation(
            contact_email=common.USER["user_name"], status=choices.DECLINED
        )
        response = self.client.post(
            f'/v1/allocations/{allocation.id}/submit/',
            json={'use_case': 'fixed'},
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(choices.SUBMITTED, response.json['status'])

    def test_submit_resubmits_declined_amendment(self):
        self.as_user()
        allocation = factories.create_allocation(
            contact_email=common.USER["user_name"],
            status=choices.UPDATE_DECLINED,
        )
        response = self.client.post(
            f'/v1/allocations/{allocation.id}/submit/',
            json={'use_case': 'fixed'},
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(choices.UPDATE_PENDING, response.json['status'])

    def test_submit_keeps_existing_related_by_id(self):
        ci = factories.create_investigator(self.allocation)
        self.as_user()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/submit/',
            json={
                'investigators': [
                    {
                        'id': ci.id,
                        'title': 'Prof.',
                        'given_name': 'Renamed',
                        'surname': 'Monash',
                        'email': 'merc.monash@monash.edu',
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 200, response.json)
        allocation = factories.refresh(self.allocation)
        self.assertEqual(1, len(allocation.investigators))
        self.assertEqual(ci.id, allocation.investigators[0].id)
        self.assertEqual('Renamed', allocation.investigators[0].given_name)

    def test_submit_by_admin_records_approver(self):
        self.as_admin()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/submit/',
            json={'notes': 'tidied', 'use_case': 'x'},
        )
        self.assertEqual(response.status_code, 200, response.json)
        allocation = factories.refresh(self.allocation)
        self.assertEqual(common.ADMIN["user_name"], allocation.approver_email)
        self.assertEqual('tidied', allocation.notes)

    def test_submit_gated_field_as_user(self):
        self.as_user()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/submit/',
            json={'associated_site': 'qcif'},
        )
        self.assertEqual(response.status_code, 403)

    def test_submit_wrong_state(self):
        self.as_user()
        allocation = factories.create_allocation(
            contact_email=common.USER["user_name"], status=choices.APPROVED
        )
        response = self.client.post(
            f'/v1/allocations/{allocation.id}/submit/', json={}
        )
        self.assertEqual(response.status_code, 403)

    def test_submit_not_owner(self):
        self.as_user2()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/submit/', json={}
        )
        self.assertEqual(response.status_code, 404)

    def test_submit_anonymous(self):
        self.as_anon()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/submit/', json={}
        )
        self.assertEqual(response.status_code, 403)

    def test_submit_validation(self):
        self.as_user()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/submit/',
            json={'grants': [{'grant_type': 'bogus'}]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('grants', response.json)

    def test_submit_unknown_quota_resource(self):
        self.as_user()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/submit/',
            json={'quotas': [{'zone': 'nectar', 'resource': 'no.such'}]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            {'quotas': ["Unknown resource 'no.such'"]}, response.json
        )

    def test_submit_quota_zone_not_offered(self):
        # volume is not offered in the nectar zone
        self.as_user()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/submit/',
            json={
                'quotas': [
                    {
                        'zone': 'nectar',
                        'resource': 'volume.gigabytes',
                        'requested_quota': 100,
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 400, response.json)
        self.assertEqual(
            {
                'quotas': [
                    "volume.gigabytes in zone 'nectar': "
                    "Resource not available in this zone"
                ]
            },
            response.json,
        )

    def test_submit_unlimited_managed(self):
        self.as_user()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/submit/',
            json={
                'quotas': [
                    {
                        'zone': 'nectar',
                        'resource': 'compute.cores',
                        'requested_quota': -1,
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 400, response.json)
        self.assertEqual(
            {
                'quotas': [
                    "compute.cores in zone 'nectar': Unlimited requested "
                    "quota not allowed for managed allocation"
                ]
            },
            response.json,
        )

    def test_submit_unlimited_unmanaged(self):
        allocation = factories.create_allocation(
            contact_email=common.USER["user_name"], managed=False
        )
        self.as_user()
        response = self.client.post(
            f'/v1/allocations/{allocation.id}/submit/',
            json={
                'quotas': [
                    {
                        'zone': 'nectar',
                        'resource': 'compute.cores',
                        'requested_quota': -1,
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(
            {('compute.cores', 'nectar'): (-1, 0)},
            quota_map(factories.refresh(allocation)),
        )


class ApproveWithChangesTests(common.AllocationApiTestCase):
    def test_approve_quota_zone_not_offered(self):
        self.as_approver()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/approve/',
            json={
                'quotas': [
                    {
                        'zone': 'melbourne',
                        'resource': 'compute.cores',
                        'quota': 16,
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 400, response.json)
        self.assertEqual(
            {
                'quotas': [
                    "compute.cores in zone 'melbourne': "
                    "Resource not available in this zone"
                ]
            },
            response.json,
        )

    def test_approve_unlimited_managed(self):
        self.as_approver()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/approve/',
            json={
                'quotas': [
                    {
                        'zone': 'nectar',
                        'resource': 'compute.cores',
                        'quota': -1,
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 400, response.json)
        self.assertEqual(
            {
                'quotas': [
                    "compute.cores in zone 'nectar': Unlimited quota not "
                    "allowed for managed allocation"
                ]
            },
            response.json,
        )

    def test_approve_unlimited_unmanaged(self):
        allocation = factories.create_allocation(managed=False)
        self.as_approver()
        response = self.client.post(
            f'/v1/allocations/{allocation.id}/approve/',
            json={
                'quotas': [
                    {
                        'zone': 'nectar',
                        'resource': 'compute.cores',
                        'quota': -1,
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(
            -1,
            quota_map(factories.refresh(allocation))[
                ('compute.cores', 'nectar')
            ][1],
        )

    def test_approve_with_changes(self):
        self.as_approver()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/approve/',
            json={
                'notes': 'approved with trimmed cores',
                'status_explanation': 'Looks good',
                'start_date': '2026-01-01',
                'end_date': '2026-12-31',
                'quotas': [
                    {
                        'zone': 'nectar',
                        'resource': 'compute.cores',
                        'quota': 16,
                    },
                    {
                        'zone': 'nectar',
                        'resource': 'compute.instances',
                        'quota': 4,
                    },
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(choices.APPROVED, response.json['status'])
        self.assertEqual('2026-01-01', response.json['start_date'])
        allocation = factories.refresh(self.allocation)
        self.assertEqual('approved with trimmed cores', allocation.notes)
        self.assertEqual('Looks good', allocation.status_explanation)
        self.assertEqual(datetime.date(2026, 12, 31), allocation.end_date)
        # Only the approved quotas remain; the allocated value was set.
        quotas = quota_map(allocation)
        self.assertEqual(
            {('compute.cores', 'nectar'), ('compute.instances', 'nectar')},
            set(quotas),
        )
        self.assertEqual(16, quotas[('compute.cores', 'nectar')][1])
        self.assertEqual(1, factories.history_count(allocation))
        # The history row kept the old quotas
        history = (
            db.session.query(models.AllocationRequest)
            .filter_by(parent_request_id=allocation.id)
            .one()
        )
        self.assertEqual(10, len(history.all_quotas()))

    def test_approve_sets_site(self):
        self.as_approver()
        allocation = factories.create_allocation(associated_site=None)
        response = self.client.post(
            f'/v1/allocations/{allocation.id}/approve/',
            json={'associated_site': 'qcif', 'national': True},
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual('qcif', response.json['associated_site'])
        self.assertTrue(response.json['national'])

    def test_approve_with_bundle_drops_single_zone_overrides(self):
        self.as_approver()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/approve/',
            json={
                'bundle': 'silver',
                'quotas': [
                    {
                        'zone': 'nectar',
                        'resource': 'compute.cores',
                        'quota': 16,
                    },
                    {
                        'zone': 'melbourne',
                        'resource': 'volume.gigabytes',
                        'quota': 50,
                    },
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.json)
        allocation = factories.refresh(self.allocation)
        # compute is not location specific so the bundle wins
        self.assertEqual(
            {('volume.gigabytes', 'melbourne')}, set(quota_map(allocation))
        )
        self.assertEqual('silver', response.json['bundle'])
        self.assertEqual(8000, response.json['su_budget'])

    def test_approve_warnings_block(self):
        factories.create_approver(
            common.APPROVER["user_name"],
            "The Approver",
            sites=[factories.get(models.Site, name='uom')],
        )
        allocation = factories.create_allocation(
            associated_site=factories.get(models.Site, name='uom')
        )
        self.as_approver()
        body = {
            'ignore_warnings': False,
            'quotas': [
                {'zone': 'monash', 'resource': 'volume.gigabytes', 'quota': 10}
            ],
        }
        response = self.client.post(
            f'/v1/allocations/{allocation.id}/approve/', json=body
        )
        self.assertEqual(response.status_code, 409, response.json)
        codes = [w['code'] for w in response.json['warnings']]
        self.assertIn('CINDER_NOT_LOCAL', codes)
        self.assertIn('APPROVER_NOT_AUTHORIZED', codes)
        # Nothing changed
        allocation = factories.refresh(allocation)
        self.assertEqual(choices.SUBMITTED, allocation.status)
        self.assertEqual(0, factories.history_count(allocation))
        self.assertEqual(
            0, quota_map(allocation)[('volume.gigabytes', 'monash')][1]
        )

        body['ignore_warnings'] = True
        response = self.client.post(
            f'/v1/allocations/{allocation.id}/approve/', json=body
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(choices.APPROVED, response.json['status'])

    def test_approve_form_encoded_still_works(self):
        self.as_approver()
        response = self.client.post(
            f'/v1/allocations/{self.allocation.id}/approve/',
            data={'notes': 'form'},
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual('form', response.json['notes'])


class AmendWithChangesTests(common.AllocationApiTestCase):
    def test_amend_with_changes(self):
        allocation = factories.create_allocation(
            contact_email=common.USER["user_name"], status=choices.APPROVED
        )
        self.as_user()
        response = self.client.post(
            f'/v1/allocations/{allocation.id}/amend/',
            json={
                'use_case': 'need more',
                'quotas': [
                    {
                        'zone': 'nectar',
                        'resource': 'compute.cores',
                        'requested_quota': 32,
                    }
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(choices.UPDATE_PENDING, response.json['status'])
        self.assertEqual('need more', response.json['use_case'])
        allocation = factories.refresh(allocation)
        self.assertEqual(
            {('compute.cores', 'nectar'): (32, 0)}, quota_map(allocation)
        )
        self.assertEqual(1, factories.history_count(allocation))

    def test_amend_without_body_keeps_quotas(self):
        allocation = factories.create_allocation(
            contact_email=common.USER["user_name"], status=choices.APPROVED
        )
        self.as_user()
        response = self.client.post(f'/v1/allocations/{allocation.id}/amend/')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(10, len(quota_map(factories.refresh(allocation))))


class ChecksTests(common.AllocationApiTestCase):
    def test_checks_owner(self):
        allocation = factories.create_allocation(
            contact_email=common.USER["user_name"], usage_types=[]
        )
        self.as_user()
        response = self.client.get(f'/v1/allocations/{allocation.id}/checks/')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual([], response.json['warnings'])
        self.assertIn('NO_SURVEY', [n['code'] for n in response.json['nags']])

    def test_checks_approving(self):
        allocation = factories.create_allocation(
            contact_email=common.USER["user_name"]
        )
        # The user asking for approver checks gets the plain ones
        self.as_user()
        response = self.client.get(
            f'/v1/allocations/{allocation.id}/checks/?approving=true'
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual([], response.json['warnings'])
        # An approver without an Approver record is told so
        self.as_approver()
        response = self.client.get(
            f'/v1/allocations/{allocation.id}/checks/?approving=true'
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertIn(
            'APPROVER_PROBLEM', [w['code'] for w in response.json['warnings']]
        )

    def _foreign_storage_allocation(self, status, quota, requested_quota):
        # A uom request with volume storage in monash, foreign to uom
        uom = factories.get(models.Site, name='uom')
        if not factories.first(
            models.Approver, username=common.APPROVER["user_name"]
        ):
            factories.create_approver(
                common.APPROVER["user_name"], "The Approver", sites=[uom]
            )
        allocation = factories.create_allocation(
            contact_email=common.USER["user_name"],
            status=status,
            associated_site=uom,
            create_quotas=False,
        )
        volume_st = factories.get(models.ServiceType, catalog_name='volume')
        group = factories.create_quota_group(
            allocation, volume_st, factories.get(models.Zone, name='monash')
        )
        factories.create_quota(
            group,
            factories.get(
                models.Resource,
                quota_name='gigabytes',
                service_type_id='volume',
            ),
            quota=quota,
            requested_quota=requested_quota,
        )
        return factories.refresh(allocation)

    def _warning_codes(self, allocation, approving):
        url = f'/v1/allocations/{allocation.id}/checks/'
        if approving:
            url += '?approving=true'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.json)
        return [w['code'] for w in response.json['warnings']]

    def test_checks_approving_pending_uses_requested_quota(self):
        for status in (choices.SUBMITTED, choices.UPDATE_PENDING):
            allocation = self._foreign_storage_allocation(
                status, quota=0, requested_quota=500
            )
            self.assertEqual(
                {'quota-volume.gigabytes__monash': 500},
                checkers.values_from_allocation(allocation),
            )
            self.as_approver()
            codes = self._warning_codes(allocation, approving=True)
            self.assertIn('CINDER_NOT_LOCAL', codes)
            self.assertIn('APPROVER_NOT_AUTHORIZED', codes)

    def test_checks_approving_approved_uses_allocated_quota(self):
        allocation = self._foreign_storage_allocation(
            choices.APPROVED, quota=0, requested_quota=500
        )
        self.assertEqual(
            {'quota-volume.gigabytes__monash': 0},
            checkers.values_from_allocation(allocation),
        )
        self.as_approver()
        self.assertEqual([], self._warning_codes(allocation, approving=True))

        allocation = self._foreign_storage_allocation(
            choices.APPROVED, quota=500, requested_quota=0
        )
        codes = self._warning_codes(allocation, approving=True)
        self.assertIn('CINDER_NOT_LOCAL', codes)
        self.assertIn('APPROVER_NOT_AUTHORIZED', codes)

    def test_checks_not_approving_unchanged(self):
        allocation = self._foreign_storage_allocation(
            choices.SUBMITTED, quota=0, requested_quota=500
        )
        # The approver-only storage checks do not run without approving
        self.as_approver()
        self.assertEqual([], self._warning_codes(allocation, approving=False))
        self.as_user()
        self.assertEqual([], self._warning_codes(allocation, approving=False))

    def test_checks_other_user(self):
        self.as_user2()
        response = self.client.get(
            f'/v1/allocations/{self.allocation.id}/checks/'
        )
        self.assertEqual(response.status_code, 404)

    def test_checks_anonymous(self):
        self.as_anon()
        response = self.client.get(
            f'/v1/allocations/{self.allocation.id}/checks/'
        )
        self.assertEqual(response.status_code, 403)


class NestedCreateTests(common.AllocationApiTestCase):
    def test_create_with_nested(self):
        self.as_user()
        response = self.client.post(
            '/v1/allocations/',
            json={
                'project_name': 'nested',
                'project_description': 'nested writes',
                'use_case': 'testing',
                'usage_types': ['Other'],
                'supported_organisations': ['Monash'],
                'investigators': [
                    {
                        'title': 'Dr',
                        'given_name': 'Ada',
                        'surname': 'Lovelace',
                        'email': 'ada@unimelb.edu.au',
                        'primary_organisation': 'https://ror.org/23456789',
                    }
                ],
                'quotas': [
                    {
                        'zone': 'nectar',
                        'resource': 'compute.cores',
                        'requested_quota': 4,
                    },
                    {
                        'zone': 'nectar',
                        'resource': 'compute.instances',
                        'requested_quota': 0,
                    },
                ],
            },
        )
        self.assertEqual(response.status_code, 201, response.json)
        allocation = factories.get(
            models.AllocationRequest, project_name='nested'
        )
        self.assertEqual(
            'ada@unimelb.edu.au', response.json['chief_investigator']
        )
        self.assertEqual(
            {('compute.cores', 'nectar'): (4, 0)}, quota_map(allocation)
        )
        self.assertEqual(
            [
                {
                    'zone': 'nectar',
                    'resource': 'compute.cores',
                    'quota': 0,
                    'requested_quota': 4,
                }
            ],
            response.json['quotas'],
        )

    def test_patch_ignores_nested(self):
        self.as_user()
        response = self.client.patch(
            f'/v1/allocations/{self.allocation.id}/',
            json={'quotas': [], 'investigators': [{'title': 'x'}]},
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(
            10, len(quota_map(factories.refresh(self.allocation)))
        )


class ApproverInfoListTests(common.AllocationApiTestCase):
    def test_include_approver_info(self):
        factories.create_allocation(parent_request_id=self.allocation.id)
        self.as_admin()
        response = self.client.get('/v1/allocations/?include=approver_info')
        self.assertEqual(response.status_code, 200)
        by_id = {a['id']: a for a in response.json['results']}
        live = by_id[self.allocation.id]
        self.assertEqual('New', live['approval_urgency'])
        self.assertEqual('None', live['expiry_state'])
        self.assertEqual(
            [self.allocation.associated_site.name], live['concerned_sites']
        )
        history = [a for a in response.json['results'] if a['parent_request']]
        self.assertNotIn('approval_urgency', history[0])

    def test_include_ignored_for_users(self):
        self.as_user()
        response = self.client.get('/v1/allocations/?include=approver_info')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('approval_urgency', response.json['results'][0])

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

import datetime

from rcallocation import choices
from rcallocation.common import context
from rcallocation.extensions import db
from rcallocation import manager
from rcallocation import models
from rcallocation.tests.unit import base
from rcallocation.tests.unit import factories
from rcallocation.tests.unit import fixtures
from rcallocation import utils


def column_dict(obj, exclude=()):
    return {
        c.name: getattr(obj, c.name)
        for c in obj.__table__.columns
        if c.name not in exclude
    }


class ManagerTestCase(base.TestCase):
    def setUp(self):
        super().setUp()
        fixtures.seed_reference_data()
        self.ctx = context.RequestContext(
            user_id="u1", user_name="bob@example.com", overwrite=False
        )
        self.manager = manager.Manager(self.ctx)


class TestCopyAllocation(ManagerTestCase):
    def test_history_copy_is_isomorphic(self):
        allocation = factories.create_allocation(
            modified_time=datetime.datetime(2024, 5, 1, 12, 0),
            submit_date=datetime.datetime(2024, 4, 1, 12, 0),
            ncris_facilities=['ALA'],
            ardc_support=['CVL'],
        )
        ci = factories.create_investigator(
            allocation,
            primary_organisation=factories.get(
                models.Organisation, short_name='Monash'
            ),
        )
        factories.create_grant(allocation)
        factories.create_publication(allocation)
        allocation = factories.refresh(allocation)
        before = column_dict(allocation)

        copy = self.manager.copy_allocation(allocation)
        db.session.commit()
        copy = factories.refresh(copy)
        allocation = factories.refresh(allocation)

        self.assertNotEqual(allocation.id, copy.id)
        self.assertEqual(allocation.id, copy.parent_request_id)
        self.assertEqual(
            {
                k: v
                for k, v in before.items()
                if k not in ("id", "parent_request_id")
            },
            column_dict(copy, exclude=("id", "parent_request_id")),
        )
        self.assertEqual(
            datetime.datetime(2024, 5, 1, 12, 0), copy.modified_time
        )
        # Children are cloned with new ids
        self.assertEqual(
            sorted(q.resource.codename for q in allocation.all_quotas()),
            sorted(q.resource.codename for q in copy.all_quotas()),
        )
        self.assertTrue(
            {q.id for q in allocation.all_quotas()}.isdisjoint(
                {q.id for q in copy.all_quotas()}
            )
        )
        self.assertEqual(1, len(copy.investigators))
        self.assertNotEqual(ci.id, copy.investigators[0].id)
        self.assertEqual(
            ci.primary_organisation_id,
            copy.investigators[0].primary_organisation_id,
        )
        self.assertEqual(1, len(copy.grants))
        self.assertEqual(1, len(copy.publications))
        # Shared references are linked, not copied
        self.assertEqual(
            [o.id for o in allocation.supported_organisations],
            [o.id for o in copy.supported_organisations],
        )
        self.assertEqual(
            ['ALA'], [f.short_name for f in copy.ncris_facilities]
        )
        self.assertEqual(['CVL'], [a.short_name for a in copy.ardc_support])
        self.assertEqual(len(allocation.usage_types), len(copy.usage_types))
        # The live record is untouched
        self.assertEqual(before, column_dict(allocation))


class TestSetQuotas(ManagerTestCase):
    def test_set_and_delete(self):
        allocation = factories.create_allocation(create_quotas=False)
        self.manager.set_quotas(
            allocation,
            {
                ('compute.cores', 'nectar'): 4,
                ('compute.instances', 'nectar'): 0,
            },
        )
        db.session.commit()
        allocation = factories.refresh(allocation)
        self.assertEqual(
            {'compute.cores': 4},
            {
                q.resource.codename: q.requested_quota
                for q in allocation.all_quotas()
            },
        )
        self.manager.set_quotas(allocation, {('compute.cores', 'nectar'): 0})
        db.session.commit()
        allocation = factories.refresh(allocation)
        self.assertEqual([], allocation.all_quotas())
        self.assertEqual([], allocation.quota_groups)

    def test_approving_sets_quota(self):
        allocation = factories.create_allocation(create_quotas=False)
        self.manager.set_quotas(
            allocation, {('compute.cores', 'nectar'): 4}, approving=True
        )
        db.session.commit()
        quota = factories.refresh(allocation).all_quotas()[0]
        self.assertEqual(4, quota.quota)
        self.assertEqual(0, quota.requested_quota)

    def test_bundle_keeps_location_specific_only(self):
        allocation = factories.create_allocation(
            bundle='gold', create_quotas=False
        )
        self.manager.set_quotas(
            allocation,
            {
                ('compute.cores', 'nectar'): 4,
                ('volume.gigabytes', 'melbourne'): 20,
            },
        )
        db.session.commit()
        allocation = factories.refresh(allocation)
        self.assertEqual(
            ['volume.gigabytes'],
            [q.resource.codename for q in allocation.all_quotas()],
        )
        # The effective quota list merges the bundle and the override
        codenames = [q['resource'] for q in allocation.quota_list()]
        self.assertIn('compute.cores', codenames)
        self.assertIn('volume.gigabytes', codenames)
        self.assertEqual(16000, allocation.su_budget)

    def test_replace(self):
        allocation = factories.create_allocation()
        self.manager.set_quotas(
            allocation, {('compute.cores', 'nectar'): 4}, replace=True
        )
        db.session.commit()
        allocation = factories.refresh(allocation)
        self.assertEqual(
            ['compute.cores'],
            [q.resource.codename for q in allocation.all_quotas()],
        )


class TestProjectName(ManagerTestCase):
    def test_availability(self):
        allocation = factories.create_allocation(project_name='My_Project')
        self.assertFalse(utils.is_project_name_available('my-project'))
        self.assertFalse(utils.is_project_name_available('MY_PROJECT'))
        self.assertTrue(utils.is_project_name_available('other'))
        # The record itself and its history are excluded
        self.assertTrue(
            utils.is_project_name_available('my-project', allocation)
        )
        self.manager.copy_allocation(allocation)
        db.session.commit()
        self.assertTrue(
            utils.is_project_name_available('my-project', allocation)
        )
        other = factories.create_allocation(project_name='other')
        self.assertFalse(utils.is_project_name_available('my-project', other))


class TestTransitions(ManagerTestCase):
    def test_submit_transitions(self):
        for before, after in (
            (choices.NEW, choices.SUBMITTED),
            (choices.SUBMITTED, choices.SUBMITTED),
            (choices.DECLINED, choices.SUBMITTED),
            (choices.UPDATE_PENDING, choices.UPDATE_PENDING),
            (choices.UPDATE_DECLINED, choices.UPDATE_PENDING),
        ):
            allocation = factories.create_allocation(
                status=before,
                submit_date=datetime.datetime(2020, 1, 1),
                notifications=False,
            )
            allocation = self.manager.submit(
                allocation, {'use_case': 'x'}, is_admin=False
            )
            self.assertEqual(after, allocation.status, before)
            self.assertGreater(
                allocation.submit_date, datetime.datetime(2020, 1, 1)
            )
            self.assertIsNone(allocation.estimated_number_users)

    def test_delete_is_idempotent(self):
        allocation = factories.create_allocation()
        self.manager.delete(allocation)
        self.manager.delete(allocation)
        self.assertEqual(choices.DELETED, allocation.status)
        self.assertEqual(1, factories.history_count(allocation))

    def test_update_notes_only_keeps_modified_time(self):
        allocation = factories.create_allocation(
            modified_time=datetime.datetime(2020, 1, 1)
        )
        self.manager.update_allocation(allocation, {'notes': 'n'}, True)
        self.assertEqual(
            datetime.datetime(2020, 1, 1), allocation.modified_time
        )
        self.manager.update_allocation(
            allocation, {'notes': 'n', 'use_case': 'u'}, True
        )
        self.assertGreater(
            allocation.modified_time, datetime.datetime(2020, 1, 1)
        )


class TestApproverInfo(ManagerTestCase):
    def test_sites_from_email(self):
        allocation = factories.create_allocation(
            associated_site=None,
            contact_email='someone@student.unimelb.edu.au',
        )
        self.assertEqual(
            ['uom'], [s.name for s in utils.get_interested_sites(allocation)]
        )
        info = self.manager.approver_info(allocation)
        self.assertEqual(['uom'], info['concerned_sites'])
        self.assertEqual('New', info['approval_urgency'])

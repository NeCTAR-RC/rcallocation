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

from unittest import mock

from oslo_config import cfg

from rcallocation import choices
from rcallocation.common import context
from rcallocation import manager
from rcallocation import notification
from rcallocation.notification import drivers
from rcallocation.tests.unit import base
from rcallocation.tests.unit import factories
from rcallocation.tests.unit import fixtures


class NotificationTestCase(base.TestCase):
    def setUp(self):
        super().setUp()
        fixtures.seed_reference_data()
        self.sent = []

        def fake_send(driver, allocation, subject, body):
            self.sent.append((allocation.id, subject, body))

        mock.patch.object(drivers.LoggingNotifier, "send", fake_send).start()
        self.ctx = context.RequestContext(
            user_id="approver",
            user_name="approver@example.com",
            overwrite=False,
        )


class TestNotifications(NotificationTestCase):
    def test_acknowledge_subject_and_body(self):
        allocation = factories.create_allocation(
            status=choices.SUBMITTED,
            project_description='Mapping the Outback',
            associated_site=factories.get(factories.models.Site, name='uom'),
            contact_email='bob@unimelb.edu.au',
        )
        notification.send_notifications(allocation)
        self.assertEqual(1, len(self.sent))
        _, subject, body = self.sent[0]
        self.assertEqual(
            'Allocation request [uom][Mapping the Outback]', subject
        )
        self.assertIn('Thank you for submitting your allocation request', body)
        self.assertIn(
            f'https://dashboard.rc.nectar.org.au/allocation/user_requests/'
            f'view/{allocation.id}/',
            body,
        )
        self.assertIn('Requested Resources', body)
        self.assertNotIn('{%', body)

    def test_subject_falls_back_to_ardc(self):
        allocation = factories.create_allocation(
            associated_site=None, contact_email='nobody@nowhere.example'
        )
        notification.send_notifications(allocation)
        self.assertTrue(
            self.sent[0][1].startswith('Allocation request [ARDC]')
        )

    def test_amendment_wording(self):
        allocation = factories.create_allocation(
            status=choices.UPDATE_PENDING, project_name='pt-1', project_id='p1'
        )
        notification.send_notifications(allocation)
        self.assertIn('extension/change', self.sent[0][2])
        self.assertIn('Requested Resources', self.sent[0][2])

    def test_bundle_wording(self):
        allocation = factories.create_allocation(
            status=choices.SUBMITTED, bundle='gold', create_quotas=False
        )
        notification.send_notifications(allocation)
        body = self.sent[0][2]
        self.assertIn('Resource Bundle', body)
        self.assertIn('gold', body)
        self.assertIn('Additional Requested Local Resources', body)

    def test_rejected(self):
        allocation = factories.create_allocation(
            status=choices.DECLINED, status_explanation='Needs work'
        )
        notification.send_notifications(allocation)
        _, subject, body = self.sent[0]
        self.assertIn('has been declined', body)
        self.assertIn('Needs work', body)
        self.assertIn(f'edit_request/{allocation.id}/', body)

    def test_approved_sends_nothing(self):
        allocation = factories.create_allocation(status=choices.APPROVED)
        notification.send_notifications(allocation)
        self.assertEqual([], self.sent)

    def test_new_promoted_to_submitted(self):
        allocation = factories.create_allocation(status=choices.NEW)
        notification.send_notifications(allocation)
        self.assertEqual(
            choices.SUBMITTED, factories.refresh(allocation).status
        )

    def test_disabled_on_allocation(self):
        allocation = factories.create_allocation(
            status=choices.NEW, notifications=False
        )
        notification.send_notifications(allocation)
        self.assertEqual([], self.sent)
        # Still progresses out of NEW, as the dashboard did
        self.assertEqual(
            choices.SUBMITTED, factories.refresh(allocation).status
        )

    def test_disabled_globally(self):
        cfg.CONF.set_override("enabled", False, group="notifications")
        allocation = factories.create_allocation(status=choices.SUBMITTED)
        notification.send_notifications(allocation)
        self.assertEqual([], self.sent)

    def test_failure_is_logged_not_raised(self):
        allocation = factories.create_allocation(status=choices.NEW)
        with mock.patch.object(
            drivers.LoggingNotifier, "send", side_effect=RuntimeError("boom")
        ):
            notification.send_notifications(allocation)
        # Not sent, so the request stays NEW
        self.assertEqual(choices.NEW, factories.refresh(allocation).status)

    def test_api_create_sends(self):
        mgr = manager.Manager(self.ctx)
        allocation = mgr.create_allocation(
            {
                'project_description': 'd',
                'use_case': 'u',
                'contact_email': 'bob@unimelb.edu.au',
            },
            is_admin=True,
        )
        self.assertEqual([allocation.id], [s[0] for s in self.sent])
        self.assertEqual(choices.SUBMITTED, allocation.status)

    def test_decline_sends_rejected(self):
        allocation = factories.create_allocation(status=choices.SUBMITTED)
        manager.Manager(self.ctx).decline(allocation, 'no')
        self.assertIn('declined', self.sent[0][2])

    def test_approve_sends_nothing(self):
        allocation = factories.create_allocation(status=choices.SUBMITTED)
        manager.Manager(self.ctx).approve(allocation)
        self.assertEqual([], self.sent)


class TestTaynacDriver(base.TestCase):
    def test_send(self):
        fixtures.seed_reference_data()
        cfg.CONF.set_override("cc", ["cc@example.com"], group="notifications")
        allocation = factories.create_allocation(contact_email='bob@x.org')
        taynac = mock.Mock()
        taynac.messages.send.return_value = mock.Mock(backend_id="42")
        with (
            mock.patch("rcallocation.common.keystone.KeystoneSession"),
            mock.patch(
                "rcallocation.common.clients.get_taynacclient",
                return_value=taynac,
            ),
        ):
            result = drivers.TaynacNotifier().send(allocation, "subj", "body")
        self.assertEqual("42", result)
        taynac.messages.send.assert_called_once_with(
            subject="subj",
            body="body",
            recipient="bob@x.org",
            cc=["cc@example.com"],
            tags=[f"allocation-{allocation.id}"],
        )

    def test_get_driver(self):
        self.assertIsInstance(
            notification.get_driver("logging"), drivers.LoggingNotifier
        )
        self.assertIsInstance(
            notification.get_driver("noop"), drivers.NoopNotifier
        )
        self.assertIsNone(drivers.NoopNotifier().send(None, "s", "b"))

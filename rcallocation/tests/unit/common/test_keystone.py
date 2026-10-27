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

from rcallocation.common import keystone
from rcallocation.common import projects
from rcallocation.notification import drivers
from rcallocation.tests.unit import base
from rcallocation.tests.unit import factories
from rcallocation.tests.unit import fixtures


class TestSharedSession(base.TestCase):
    def setUp(self):
        super().setUp()
        # Each load returns a new object, so reuse is only observed if
        # the shared session is cached.
        mock.patch(
            "keystoneauth1.loading.load_session_from_conf_options",
            side_effect=lambda *a, **kw: mock.Mock(),
        ).start()
        mock.patch(
            "keystoneauth1.loading.load_auth_from_conf_options",
            side_effect=lambda *a, **kw: mock.Mock(),
        ).start()

    def test_lookups_and_notifications_share_session(self):
        cfg.CONF.set_override("auth_strategy", "keystone")
        ksclient = mock.Mock()
        ksclient.role_assignments.list.return_value = []
        get_ksclient = mock.patch(
            "rcallocation.common.clients.get_keystoneclient",
            return_value=ksclient,
        ).start()
        get_taynac = mock.patch(
            "rcallocation.common.clients.get_taynacclient"
        ).start()

        projects.managed_project_ids("user-a")
        projects.managed_project_ids("user-b")
        fixtures.seed_reference_data()
        drivers.TaynacNotifier().send(
            factories.create_allocation(), "subj", "body"
        )

        sessions = [c.args[0] for c in get_ksclient.call_args_list]
        sessions.append(get_taynac.call_args.args[0])
        self.assertEqual(3, len(sessions))
        for session in sessions:
            self.assertIs(sessions[0], session)

    def test_reset_builds_new_session(self):
        first = keystone.get_session()
        self.assertIs(first, keystone.get_session())
        keystone.reset()
        self.assertIsNot(first, keystone.get_session())

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

import unittest

from rcallocation.common import context
from rcallocation.common import keystone


class TestRequestContext(unittest.TestCase):
    def test_anonymous(self):
        ctx = context.anonymous()
        self.assertTrue(ctx.is_anonymous)
        self.assertIsNone(ctx.user_id)

    def test_user_name_in_policy_values(self):
        ctx = context.RequestContext(
            user_id="u1", user_name="bob@example.com", overwrite=False
        )
        self.assertFalse(ctx.is_anonymous)
        self.assertEqual(
            "bob@example.com", ctx.to_policy_values()["user_name"]
        )

    def test_from_environ(self):
        environ = {
            "HTTP_X_USER_ID": "u1",
            "HTTP_X_USER_NAME": "bob@example.com",
            "HTTP_X_PROJECT_ID": "p1",
            "HTTP_X_ROLES": "member,allocationadmin",
        }
        ctx = context.RequestContext.from_environ(environ)
        self.assertIsInstance(ctx, context.RequestContext)
        self.assertEqual("u1", ctx.user_id)
        self.assertEqual("bob@example.com", ctx.user_name)
        self.assertEqual("p1", ctx.project_id)
        self.assertEqual(["member", "allocationadmin"], ctx.roles)


class TestKeystoneContext(unittest.TestCase):
    def _run(self, environ):
        captured = {}

        def app(env, start_response):
            captured.update(env)
            return []

        keystone.KeystoneContext(app)(environ, lambda *a: None)
        return captured

    def test_confirmed_token(self):
        env = self._run(
            {
                "HTTP_X_AUTH_TOKEN": "tok",
                "HTTP_X_IDENTITY_STATUS": "Confirmed",
                "HTTP_X_USER_ID": "u1",
            }
        )
        self.assertEqual("u1", env[keystone.REQUEST_CONTEXT_ENV].user_id)
        self.assertNotIn(keystone.INVALID_TOKEN_ENV, env)

    def test_invalid_token_flagged(self):
        env = self._run(
            {
                "HTTP_X_AUTH_TOKEN": "tok",
                "HTTP_X_IDENTITY_STATUS": "Invalid",
            }
        )
        self.assertTrue(env[keystone.INVALID_TOKEN_ENV])
        self.assertTrue(env[keystone.REQUEST_CONTEXT_ENV].is_anonymous)

    def test_no_token_is_anonymous(self):
        env = self._run({"HTTP_X_IDENTITY_STATUS": "Invalid"})
        self.assertNotIn(keystone.INVALID_TOKEN_ENV, env)
        self.assertTrue(env[keystone.REQUEST_CONTEXT_ENV].is_anonymous)

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

from oslo_config import cfg
import webob

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

    def test_unvalidated_token_not_flagged(self):
        # A token on a path that skipped keystone has no identity status.
        env = self._run({"HTTP_X_AUTH_TOKEN": "tok"})
        self.assertNotIn(keystone.INVALID_TOKEN_ENV, env)
        self.assertTrue(env[keystone.REQUEST_CONTEXT_ENV].is_anonymous)

    def test_only_invalid_status_flagged(self):
        for status in ("Confirmed", "", "invalid", "Bogus"):
            env = self._run(
                {
                    "HTTP_X_AUTH_TOKEN": "tok",
                    "HTTP_X_IDENTITY_STATUS": status,
                }
            )
            self.assertNotIn(keystone.INVALID_TOKEN_ENV, env, status)


class TestSkippingAuthProtocol(unittest.TestCase):
    SPOOFED_HEADERS = {
        "X-Auth-Token": "tok",
        "X-Identity-Status": "Confirmed",
        "X-User-Id": "u1",
        "X-User-Name": "bob@example.com",
        "X-User": "bob@example.com",
        "X-Project-Id": "p1",
        "X-Tenant-Id": "p1",
        "X-Domain-Id": "d1",
        "X-Roles": "admin,allocationadmin,allocationapprover",
        "X-Service-Roles": "service",
        "X-Is-Admin-Project": "True",
        "OpenStack-System-Scope": "all",
    }

    def setUp(self):
        super().setUp()
        self.addCleanup(cfg.CONF.reset)
        cfg.CONF.set_override(
            "delay_auth_decision", True, group="keystone_authtoken"
        )

    def _run(self, path, headers):
        captured = {}

        def app(env, start_response):
            captured.update(env)
            start_response("200 OK", [])
            return [b""]

        stack = keystone.SkippingAuthProtocol(
            keystone.KeystoneContext(app), {}
        )
        response = webob.Request.blank(path, headers=headers).get_response(
            stack
        )
        return response, captured

    def test_skipped_paths_strip_identity_headers(self):
        for path in ("/", "/healthcheck", "/v1/openapi.json", "/v1/docs/"):
            response, env = self._run(path, self.SPOOFED_HEADERS)
            self.assertEqual(200, response.status_code, path)
            self.assertNotIn(keystone.INVALID_TOKEN_ENV, env, path)
            ctx = env[keystone.REQUEST_CONTEXT_ENV]
            self.assertTrue(ctx.is_anonymous, path)
            self.assertIsNone(ctx.user_id, path)
            self.assertIsNone(ctx.project_id, path)
            self.assertIsNone(ctx.system_scope, path)
            self.assertEqual([], ctx.roles, path)
            for key in (
                "HTTP_X_IDENTITY_STATUS",
                "HTTP_X_USER_ID",
                "HTTP_X_ROLES",
                "HTTP_OPENSTACK_SYSTEM_SCOPE",
            ):
                self.assertNotIn(key, env, path)

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

from oslo_config import cfg
from oslo_policy import policy as oslo_policy

from rcallocation.common import context
from rcallocation.common import policies
from rcallocation import policy
from rcallocation.tests.unit import base


class TestPolicyDefaults(base.TestCase):
    def test_all_documented_rules_have_scope_types(self):
        for rule in policies.list_rules():
            if not isinstance(rule, oslo_policy.DocumentedRuleDefault):
                continue
            self.assertTrue(
                rule.scope_types,
                f"Policy rule {rule.name} has no scope_types",
            )
            self.assertTrue(
                set(rule.scope_types) <= {"system", "project"},
                f"Policy rule {rule.name} has unexpected scope_types "
                f"{rule.scope_types}",
            )

    def test_rules_register(self):
        # Catches dangling rule: references in check strings.
        enforcer = oslo_policy.Enforcer(cfg.CONF)
        enforcer.register_defaults(policies.list_rules())
        enforcer.load_rules()
        self.assertIn("read_admin", enforcer.rules)


class TestBaseRules(base.TestCase):
    def check(self, rule, ctx, target=None):
        return policy.get_enforcer().authorize(
            rule, target or {}, ctx, do_raise=False
        )

    def ctx(
        self,
        roles,
        system_scope=None,
        project_id="p1",
        user_name="bob@example.com",
    ):
        return context.RequestContext(
            user_id="u1",
            user_name=user_name,
            project_id=None if system_scope else project_id,
            roles=roles,
            system_scope=system_scope,
            overwrite=False,
        )

    def test_project_admin_role_grants_nothing(self):
        ctx = self.ctx(["admin", "member"])
        self.assertFalse(self.check(policies.ADMIN, ctx))
        self.assertFalse(self.check(policies.READ_ADMIN, ctx))
        self.assertFalse(self.check(policies.APPROVER, ctx))

    def test_allocationadmin(self):
        ctx = self.ctx(["allocationadmin"])
        self.assertTrue(self.check(policies.ADMIN, ctx))
        self.assertTrue(self.check(policies.READ_ADMIN, ctx))
        self.assertFalse(self.check(policies.APPROVER, ctx))

    def test_allocationapprover(self):
        ctx = self.ctx(["allocationapprover"])
        self.assertFalse(self.check(policies.ADMIN, ctx))
        self.assertTrue(self.check(policies.READ_ADMIN, ctx))
        self.assertTrue(self.check(policies.APPROVER, ctx))

    def test_system_admin(self):
        ctx = self.ctx(["admin"], system_scope="all")
        self.assertTrue(self.check(policies.ADMIN, ctx))
        self.assertTrue(self.check(policies.READ_ADMIN, ctx))
        self.assertFalse(self.check(policies.APPROVER, ctx))

    def test_system_reader(self):
        ctx = self.ctx(["reader"], system_scope="all")
        self.assertFalse(self.check(policies.ADMIN, ctx))
        self.assertTrue(self.check(policies.READ_ADMIN, ctx))

    def test_project_reader_is_not_read_admin(self):
        ctx = self.ctx(["reader", "member"])
        self.assertFalse(self.check(policies.READ_ADMIN, ctx))

    def test_owner_by_contact_email(self):
        ctx = self.ctx(["member"])
        target = {"contact_email": "bob@example.com", "is_owner": False}
        self.assertTrue(self.check(policies.OWNER, ctx, target))
        target = {"contact_email": "fred@example.com", "is_owner": False}
        self.assertFalse(self.check(policies.OWNER, ctx, target))

    def test_owner_by_project(self):
        ctx = self.ctx(["member"])
        target = {"contact_email": "fred@example.com", "is_owner": True}
        self.assertTrue(self.check(policies.OWNER, ctx, target))

    def test_anonymous(self):
        ctx = context.anonymous()
        self.assertTrue(self.check(policies.PUBLIC, ctx))
        self.assertFalse(self.check(policies.ADMIN, ctx))
        target = {"contact_email": "bob@example.com", "is_owner": False}
        self.assertFalse(self.check(policies.OWNER, ctx, target))
        self.assertTrue(self.check(policies.VERSIONS_PREFIX % "list", ctx))

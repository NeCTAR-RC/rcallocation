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

import os
import re
from unittest import mock

import flask_testing
from oslo_config import cfg
from oslo_policy import policy as oslo_policy
import sqlalchemy as sa

from rcallocation import app
from rcallocation.common import config
from rcallocation.common import context
from rcallocation.common import keystone
from rcallocation.common import projects
from rcallocation.extensions import db
from rcallocation import fortree
from rcallocation import policy


TESTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF_FILE = os.path.join(TESTS_DIR, "etc", "rcallocation.conf")
MAPPINGS_FILE = os.path.join(TESTS_DIR, "etc", "mappings.yaml")

PROJECT_ID = "ksprojectid1"
USER_ID = "ksuserid1"
USER_NAME = "bob@example.com"


def _sqlite_regexp(pattern, value):
    if value is None:
        return False
    return re.search(pattern, str(value)) is not None


class TestCase(flask_testing.TestCase):
    def create_app(self):
        application = app.create_app(
            {
                "SECRET_KEY": "secret",
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            },
            conf_file=CONF_FILE,
        )
        cfg.CONF.set_override(
            "mappings_file", MAPPINGS_FILE, group="allocations"
        )
        config.reset_mappings()
        return application

    def setUp(self):
        super().setUp()
        self.addCleanup(mock.patch.stopall)

        @sa.event.listens_for(db.engine, "connect")
        def _register_regexp(dbapi_connection, connection_record):
            dbapi_connection.create_function("regexp", 2, _sqlite_regexp)
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        db.create_all()

    def tearDown(self):
        super().tearDown()
        db.session.remove()
        db.drop_all()
        cfg.CONF.reset()
        policy.reset()
        projects.reset()
        fortree.reset()
        config.reset_mappings()


class TestKeystoneWrapper:
    """WSGI wrapper injecting a RequestContext for the chosen persona."""

    def __init__(
        self,
        app,
        roles=None,
        user_id=USER_ID,
        user_name=USER_NAME,
        project_id=PROJECT_ID,
        system_scope=None,
        domain_id=None,
        anonymous=False,
    ):
        self.app = app
        self.roles = roles or []
        self.user_id = user_id
        self.user_name = user_name
        self.system_scope = system_scope
        self.domain_id = domain_id
        self.project_id = None if (system_scope or domain_id) else project_id
        self.anonymous = anonymous

    def __call__(self, environ, start_response):
        if self.anonymous:
            cntx = context.anonymous()
        else:
            cntx = context.RequestContext(
                roles=self.roles,
                project_id=self.project_id,
                user_id=self.user_id,
                user_name=self.user_name,
                system_scope=self.system_scope,
                domain_id=self.domain_id,
                overwrite=False,
            )
        environ[keystone.REQUEST_CONTEXT_ENV] = cntx

        return self.app(environ, start_response)


class ApiTestCase(TestCase):
    ROLES = ["member"]
    USER_ID = USER_ID
    USER_NAME = USER_NAME
    PROJECT_ID = PROJECT_ID
    SYSTEM_SCOPE = None
    DOMAIN_ID = None
    ANONYMOUS = False

    def setUp(self):
        super().setUp()
        self._base_wsgi_app = self.app.wsgi_app
        self.use_persona()

    def use_persona(self, **overrides):
        """Switch the caller identity for subsequent requests."""
        persona = {
            "roles": self.ROLES,
            "user_id": self.USER_ID,
            "user_name": self.USER_NAME,
            "project_id": self.PROJECT_ID,
            "system_scope": self.SYSTEM_SCOPE,
            "domain_id": self.DOMAIN_ID,
            "anonymous": self.ANONYMOUS,
        }
        persona.update(overrides)
        self.app.wsgi_app = TestKeystoneWrapper(self._base_wsgi_app, **persona)

    def override_policy(self, rules):
        """Override policy rules, as an operator's policy.yaml would."""
        enforcer = policy.get_enforcer()
        enforcer.load_rules()
        enforcer.set_rules(
            oslo_policy.Rules.from_dict(rules), overwrite=False, use_conf=False
        )


class AdminApiTestCase(ApiTestCase):
    ROLES = ["allocationadmin", "member"]
    USER_NAME = "admin@example.com"


class ApproverApiTestCase(ApiTestCase):
    ROLES = ["allocationapprover", "member"]
    USER_NAME = "approver@example.com"


class SystemAdminApiTestCase(ApiTestCase):
    ROLES = ["admin", "member", "reader"]
    SYSTEM_SCOPE = "all"
    USER_NAME = "sysadmin@example.com"


class SystemReaderApiTestCase(ApiTestCase):
    ROLES = ["reader"]
    SYSTEM_SCOPE = "all"
    USER_NAME = "sysreader@example.com"


class AnonymousApiTestCase(ApiTestCase):
    ANONYMOUS = True

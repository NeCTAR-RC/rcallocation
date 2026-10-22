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

"""Shared base for the ported API tests.

The old ``AllocationAPITest`` had four users (bob, fred, an approver and
an admin) and used ``force_authenticate`` to switch between them. Here
each is a persona applied with ``as_<name>()`` before the request.
"""

from rcallocation import choices
from rcallocation.tests.unit import base
from rcallocation.tests.unit import factories
from rcallocation.tests.unit import fixtures


USER = {
    "user_id": "user1",
    "user_name": "bob",
    "project_id": "idproj1",
    "roles": ["member"],
}
USER2 = {
    "user_id": "user2",
    "user_name": "fred",
    "project_id": "idproj2",
    "roles": ["member"],
}
APPROVER = {
    "user_id": "approver",
    "user_name": "approver",
    "project_id": "idproj3",
    "roles": ["member", "allocationapprover"],
}
ADMIN = {
    "user_id": "admin",
    "user_name": "admin",
    "project_id": "idadmin-proj",
    "roles": ["member", "allocationadmin"],
}
SYSTEM_ADMIN = {
    "user_id": "sysadmin",
    "user_name": "system-admin",
    "project_id": None,
    "system_scope": "all",
    "roles": ["admin", "member", "reader"],
}
SYSTEM_READER = {
    "user_id": "sysreader",
    "user_name": "system-reader",
    "project_id": None,
    "system_scope": "all",
    "roles": ["reader"],
}
SYSTEM_APPROVER = {
    "user_id": "sysapprover",
    "user_name": "system-approver",
    "project_id": None,
    "system_scope": "all",
    "roles": ["allocationapprover"],
}
SYSTEM_MEMBER = {
    "user_id": "sysmember",
    "user_name": "system-member",
    "project_id": None,
    "system_scope": "all",
    "roles": ["member"],
}


class AllocationApiTestCase(base.ApiTestCase):
    """Seeds the reference data and one submitted request owned by bob."""

    ROLES = USER["roles"]
    USER_ID = USER["user_id"]
    USER_NAME = USER["user_name"]
    PROJECT_ID = USER["project_id"]

    def setUp(self):
        super().setUp()
        self.maxDiff = None
        fixtures.seed_reference_data()
        self.allocation = factories.create_allocation(
            contact_email=USER["user_name"],
            status=choices.SUBMITTED,
        )

    def persona(self, spec):
        self.use_persona(**spec)

    def as_user(self):
        self.persona(USER)

    def as_user2(self):
        self.persona(USER2)

    def as_approver(self):
        self.persona(APPROVER)

    def as_admin(self):
        self.persona(ADMIN)

    def as_anon(self):
        self.use_persona(anonymous=True)

    def as_system_admin(self):
        self.persona(SYSTEM_ADMIN)

    def as_system_reader(self):
        self.persona(SYSTEM_READER)

    def as_system_approver(self):
        self.persona(SYSTEM_APPROVER)

    def as_system_member(self):
        self.persona(SYSTEM_MEMBER)

    def ids(self, response):
        self.assertEqual(200, response.status_code, response.json)
        return {a["id"] for a in response.json["results"]}

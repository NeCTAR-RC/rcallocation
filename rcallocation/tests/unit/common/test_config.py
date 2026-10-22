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
import tempfile

from oslo_config import cfg

from rcallocation.common import config
from rcallocation.tests.unit import base


class TestConfig(base.TestCase):
    def test_keystone_authtoken_defaults(self):
        self.assertTrue(cfg.CONF.keystone_authtoken.delay_auth_decision)
        self.assertEqual(
            "allocations", cfg.CONF.keystone_authtoken.service_type
        )

    def test_mappings_loaded(self):
        mappings = config.get_mappings()
        self.assertEqual(["melbourne"], mappings.home_zones["uom"])
        self.assertEqual(["unimelb.edu.au"], mappings.site_members["uom"])
        self.assertEqual(["QRIScloud"], mappings.home_storage_zones["qcif"])

    def test_missing_mappings_file(self):
        mappings = config.load_mappings("/nonexistent/mappings.yaml")
        self.assertEqual({}, mappings.home_zones)
        self.assertEqual({}, mappings.site_members)

    def _write(self, text):
        fd, path = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        self.addCleanup(os.unlink, path)
        return path

    def test_invalid_mappings_values(self):
        path = self._write("home_zones:\n  melbourne: melbourne\n")
        self.assertRaises(config.MappingsError, config.load_mappings, path)

    def test_unknown_mappings_key(self):
        path = self._write("bogus:\n  a: [b]\n")
        self.assertRaises(config.MappingsError, config.load_mappings, path)

    def test_list_opts_groups(self):
        groups = [group for group, _ in config.list_opts()]
        for expected in (
            "DEFAULT",
            "api",
            "allocations",
            "database",
            "flask",
            "notifications",
            "sentry",
            "service_auth",
        ):
            self.assertIn(expected, groups)

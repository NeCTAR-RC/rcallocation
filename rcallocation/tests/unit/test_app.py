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

from rcallocation import app
from rcallocation.common import config
from rcallocation.common import keystone
from rcallocation.tests.unit import base


class TestApp(base.ApiTestCase):
    def test_discovery(self):
        response = self.client.get("/")
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {
                "versions": [
                    {
                        "id": "v1",
                        "status": "CURRENT",
                        "links": [
                            {"href": "http://localhost/v1/", "rel": "self"}
                        ],
                    }
                ]
            },
            response.json,
        )

    def test_healthcheck(self):
        response = self.client.get("/healthcheck")
        self.assertEqual(200, response.status_code)

    def test_openapi(self):
        response = self.client.get("/v1/openapi.json")
        self.assertEqual(200, response.status_code)
        self.assertEqual("3.0.3", response.json["openapi"])
        self.assertIn("/v1/versions/", response.json["paths"])

    def test_versions(self):
        response = self.client.get("/v1/versions/")
        self.assertEqual(200, response.status_code)
        version = cfg.CONF.api.version
        self.assertEqual(
            {
                "versions": [
                    {
                        "id": f"v{version}",
                        "status": "CURRENT",
                        "version": version,
                    }
                ]
            },
            response.json,
        )
        self.assertEqual("application/json", response.mimetype)

    def test_versions_anonymous(self):
        self.use_persona(anonymous=True)
        response = self.client.get("/v1/versions/")
        self.assertEqual(200, response.status_code)

    def test_missing_trailing_slash_redirects(self):
        response = self.client.get("/v1/versions")
        self.assertEqual(308, response.status_code)
        self.assertTrue(response.headers["Location"].endswith("/v1/versions/"))

    def test_not_found_body(self):
        response = self.client.get("/v1/nothing-here/")
        self.assertEqual(404, response.status_code)
        self.assertEqual({"detail": "Not found."}, response.json)

    def test_method_not_allowed_body(self):
        response = self.client.delete("/v1/versions/")
        self.assertEqual(405, response.status_code)
        self.assertEqual(
            {"detail": 'Method "DELETE" not allowed.'}, response.json
        )

    def test_invalid_token_rejected(self):
        response = self.client.get(
            "/v1/versions/",
            environ_overrides={"rcallocation.invalid_token": True},
        )
        self.assertEqual(401, response.status_code)
        self.assertEqual(
            {"detail": "Invalid or expired token."}, response.json
        )


class TestKeystoneAuthStrategy(base.TestCase):
    """The real keystone middleware stack, without a keystone server."""

    def create_app(self):
        config.init(conf_file=base.CONF_FILE)
        cfg.CONF.set_override("auth_strategy", "keystone")
        return app.create_app(
            {
                "SECRET_KEY": "secret",
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            },
            init_config=False,
        )

    def test_middleware_installed(self):
        self.assertIsInstance(self.app.wsgi_app, keystone.SkippingAuthProtocol)

    def test_skipped_paths_with_token(self):
        headers = {"X-Auth-Token": "tok"}
        for path in ("/", "/v1/openapi.json"):
            response = self.client.get(path, headers=headers)
            self.assertEqual(200, response.status_code, path)

    def test_healthcheck_with_token(self):
        response = self.client.get(
            "/healthcheck", headers={"X-Auth-Token": "tok"}
        )
        self.assertEqual(200, response.status_code)

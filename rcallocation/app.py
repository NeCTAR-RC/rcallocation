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

import flask
from oslo_config import cfg
from oslo_log import log as logging
from oslo_middleware import healthcheck
from oslo_middleware import http_proxy_to_wsgi
from oslo_middleware import request_id
from werkzeug.middleware import dispatcher

from rcallocation.api import root
from rcallocation.api import v1 as api_v1
from rcallocation.api.v1 import errors
from rcallocation.common import config
from rcallocation.common import exceptions
from rcallocation.common import keystone
from rcallocation.common import sentry
from rcallocation import extensions
from rcallocation import models  # noqa


CONF = cfg.CONF
LOG = logging.getLogger(__name__)

API_TITLE = "Nectar Allocation API"
OPENAPI_VERSION = "3.0.3"


def create_app(test_config=None, conf_file=None, init_config=True):
    # create and configure the app
    if init_config:
        config.init(conf_file=conf_file)
    app = flask.Flask(__name__)
    app.json.sort_keys = False
    app.config.from_mapping(
        API_TITLE=API_TITLE,
        API_VERSION=CONF.api.version,
        OPENAPI_VERSION=OPENAPI_VERSION,
        OPENAPI_URL_PREFIX="/v1",
        OPENAPI_JSON_PATH="openapi.json",
        OPENAPI_SWAGGER_UI_PATH="docs" if CONF.api.enable_swagger_ui else None,
        OPENAPI_SWAGGER_UI_URL="https://cdn.jsdelivr.net/npm/swagger-ui-dist/",
        API_SPEC_OPTIONS={
            "components": {
                "securitySchemes": {
                    "token": {
                        "type": "apiKey",
                        "in": "header",
                        "name": "X-Auth-Token",
                    }
                }
            },
            "security": [{"token": []}],
        },
    )
    if test_config is None:
        engine_options = {
            "pool_pre_ping": True,
            "pool_recycle": CONF.database.connection_recycle_time,
        }
        connection = CONF.database.connection or ""
        if not connection.startswith("sqlite"):
            engine_options["pool_size"] = CONF.database.pool_size
            engine_options["max_overflow"] = CONF.database.max_overflow
        app.config.from_mapping(
            SECRET_KEY=CONF.flask.secret_key,
            SQLALCHEMY_DATABASE_URI=connection,
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            SQLALCHEMY_ENGINE_OPTIONS=engine_options,
        )
    else:
        app.config.update(test_config)

    if init_config:
        config.setup_logging(CONF)
        sentry.setup()

    register_extensions(app)
    api = errors.Api(app)
    app.extensions["rcallocation_api"] = api
    errors.register_handlers(app)
    api_v1.register(api)
    root.register(app)
    app.before_request(reject_invalid_token)

    hc_app = healthcheck.Healthcheck.app_factory(
        {}, oslo_config_project='rcallocation'
    )
    app.wsgi_app = dispatcher.DispatcherMiddleware(
        app.wsgi_app, {'/healthcheck': hc_app}
    )

    # Each wrapper applied here runs before the ones applied above it, so
    # the request flows proxy headers -> request id -> auth_token ->
    # context -> healthcheck dispatcher -> app. RequestId must run before
    # the context is built: RequestContext.from_environ() reads the
    # request id it sets, which keeps the id in log lines equal to the
    # x-openstack-request-id response header.
    if CONF.auth_strategy == "keystone":
        if not CONF.keystone_authtoken.delay_auth_decision:
            LOG.warning(
                "[keystone_authtoken] delay_auth_decision is false: "
                "anonymous read access to the API will not work"
            )
        app.wsgi_app = keystone.KeystoneContext(app.wsgi_app)
        app.wsgi_app = keystone.SkippingAuthProtocol(app.wsgi_app, {})
    elif CONF.auth_strategy == "noauth":
        app.wsgi_app = keystone.NoAuthContext(app.wsgi_app)

    app.wsgi_app = request_id.RequestId(app.wsgi_app)
    app.wsgi_app = http_proxy_to_wsgi.HTTPProxyToWSGI(app.wsgi_app)

    return app


def register_extensions(app):
    """Register Flask extensions."""
    extensions.db.init_app(app)
    extensions.migrate.init_app(
        app, extensions.db, directory=os.path.join(app.root_path, "migrations")
    )


def reject_invalid_token():
    """Answer 401 when keystone rejected the token that was presented.

    Requests without any token continue as anonymous; only a token that
    failed validation is refused here.
    """
    if flask.request.environ.get(keystone.INVALID_TOKEN_ENV):
        raise exceptions.InvalidToken()

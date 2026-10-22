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

"""Error responses shaped like Django REST Framework's.

flask-smorest answers ``HTTPException`` with a ``{"code", "status",
"message"}`` payload. The old API returned ``{"detail": "..."}`` for
generic errors and the bare validation structure for 400s, and
python-nectarallocationclient turns those bodies into exception messages,
so this module reproduces them.
"""

import flask
import flask_smorest
import marshmallow as ma
from oslo_log import log as logging
from oslo_policy import policy as oslo_policy

from rcallocation.common import exceptions


LOG = logging.getLogger(__name__)

DETAILS = {
    400: "Bad request.",
    401: "Authentication credentials were not provided.",
    403: "You do not have permission to perform this action.",
    404: "Not found.",
    406: "Could not satisfy the request Accept header.",
    415: "Unsupported media type in request.",
    500: "A server error occurred.",
}


class DetailSchema(ma.Schema):
    detail = ma.fields.String(metadata={"description": "Error detail"})


class Api(flask_smorest.Api):
    ERROR_SCHEMA = DetailSchema

    def handle_http_exception(self, error):
        code = error.code or 500
        data = getattr(error, "data", None) or {}
        headers = data.get("headers") or {}
        if code == 405:
            detail = f'Method "{flask.request.method}" not allowed.'
        elif "messages" in data:
            # webargs abort() carrying validation messages
            return data["messages"], code, headers
        else:
            detail = data.get("message") or DETAILS.get(
                code, error.description
            )
        return {"detail": detail}, code, headers


def register_handlers(app):
    @app.errorhandler(exceptions.RcAllocationException)
    def handle_service_error(exc):
        return flask.jsonify(exc.body()), exc.status_code

    @app.errorhandler(oslo_policy.PolicyNotAuthorized)
    def handle_policy_error(exc):
        # Views normally convert this themselves; this is a safety net.
        return flask.jsonify(exceptions.PermissionDenied().body()), 403

    @app.errorhandler(Exception)
    def handle_unexpected(exc):
        if app.testing or app.debug:
            raise exc
        LOG.exception("Unhandled error serving %s", flask.request.path)
        return flask.jsonify({"detail": DETAILS[500]}), 500

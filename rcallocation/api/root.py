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

"""Unauthenticated version discovery document at ``/``."""

import flask


blueprint = flask.Blueprint("root", __name__)


@blueprint.route("/")
def discovery():
    base = flask.request.url_root.rstrip("/")
    return flask.jsonify(
        {
            "versions": [
                {
                    "id": "v1",
                    "status": "CURRENT",
                    "links": [{"href": f"{base}/v1/", "rel": "self"}],
                }
            ]
        }
    )


def register(app):
    app.register_blueprint(blueprint)

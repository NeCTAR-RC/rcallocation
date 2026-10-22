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

"""Drive python-nectarallocationclient against the Flask test client.

A ``requests`` transport adapter routes every HTTP call the client makes
through ``app.test_client()``, so the real client code (form-encoded
bodies, pagination following, error mapping) is exercised end to end
without a network or keystone. The caller identity still comes from the
test persona wrapper, so the ``X-Auth-Token`` the client sends is ignored.
"""

from urllib import parse

from keystoneauth1 import session as ks_session
from keystoneauth1 import token_endpoint
from nectarallocationclient import client as allocation_client
import requests
from requests import adapters
from requests import structures


BASE_URL = "http://localhost/v1"

_HOP_HEADERS = {"content-length", "host", "connection", "accept-encoding"}


class FlaskTestClientAdapter(adapters.BaseAdapter):
    def __init__(self, app):
        super().__init__()
        self.client = app.test_client()

    def send(
        self,
        request,
        stream=False,
        timeout=None,
        verify=True,
        cert=None,
        proxies=None,
    ):
        parts = parse.urlsplit(request.url)
        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() not in _HOP_HEADERS
        }
        rv = self.client.open(
            path=parts.path,
            query_string=parts.query,
            method=request.method,
            headers=headers,
            data=request.body,
        )
        response = requests.Response()
        response.status_code = rv.status_code
        response.reason = rv.status.partition(" ")[2]
        response.headers = structures.CaseInsensitiveDict(rv.headers.items())
        response._content = rv.get_data()
        response.url = request.url
        response.request = request
        response.encoding = "utf-8"
        return response

    def close(self):
        pass


def make_session(app):
    rs = requests.Session()
    adapter = FlaskTestClientAdapter(app)
    rs.mount("http://", adapter)
    rs.mount("https://", adapter)
    auth = token_endpoint.Token(BASE_URL, "fake-token")
    return ks_session.Session(session=rs, auth=auth)


def make_client(app):
    return allocation_client.Client(
        "1", session=make_session(app), endpoint_override=BASE_URL
    )

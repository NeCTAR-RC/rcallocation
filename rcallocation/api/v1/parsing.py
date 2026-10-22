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

"""Request body parsing that accepts JSON or form-encoded bodies.

python-nectarallocationclient sends POST and PATCH bodies as
``application/x-www-form-urlencoded`` (keystoneauth only JSON-encodes the
``json=`` argument and the client passes ``data=``). Django REST Framework
accepted both transparently, so the parser used by every ``@blp.arguments``
decorator keeps the documented ``json`` location but falls back to the form
data, normalising it the way DRF's HTML input handling did:

* repeated keys become lists for ``List`` fields;
* an empty string for a non-string field means ``None`` when the field
  allows it, otherwise the key is treated as absent;
* ``"True"`` and ``"False"`` are left for marshmallow's ``Boolean`` field,
  which already accepts them.

Validation failures are raised as :class:`ValidationError` so the response
is DRF's ``{"field": ["message"]}`` with status 400 rather than webargs'
422 envelope.
"""

import marshmallow as ma
from webargs import flaskparser
from webargs import multidictproxy

from rcallocation.common import exceptions


class FormProxy(multidictproxy.MultiDictProxy):
    def __init__(self, multidict, schema):
        super().__init__(multidict, schema)
        self._fields = {}
        for name, field in schema.fields.items():
            key = field.data_key if field.data_key is not None else name
            self._fields[key] = field

    def __getitem__(self, key):
        value = super().__getitem__(key)
        field = self._fields.get(key)
        if field is None or value is ma.missing:
            return value
        if key in self.multiple_keys:
            return [v for v in value if v != ""]
        if value == "" and not isinstance(field, ma.fields.String):
            return None if field.allow_none else ma.missing
        return value


class Parser(flaskparser.FlaskParser):
    DEFAULT_VALIDATION_STATUS = 400

    def load_json(self, req, schema):
        data = super().load_json(req, schema)
        if data is not ma.missing:
            return data
        if req.form:
            return FormProxy(req.form, schema)
        return ma.missing

    def handle_error(
        self, error, req, schema, *, error_status_code, error_headers
    ):
        messages = error.messages
        if isinstance(messages, dict) and len(messages) == 1:
            ((location, inner),) = messages.items()
            if location in self.__location_map__:
                messages = inner
        if isinstance(messages, dict) and "_schema" in messages:
            messages = dict(messages)
            messages["non_field_errors"] = messages.pop("_schema")
        raise exceptions.ValidationError(messages)

    def _handle_invalid_json_error(self, error, req, *args, **kwargs):
        raise exceptions.ValidationError(
            {"detail": f"JSON parse error - {error}"}
        )

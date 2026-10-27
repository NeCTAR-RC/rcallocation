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

import datetime
import re

import marshmallow as ma
from marshmallow import validate


UTC = datetime.UTC


def _drf_messages():
    """Use Django REST Framework's wording for common field errors.

    The messages reach users through python-nectarallocationclient and the
    dashboard, so keep them as they were.
    """
    ma.fields.Field.default_error_messages.update(
        {
            "required": "This field is required.",
            "null": "This field may not be null.",
        }
    )
    ma.fields.Integer.default_error_messages.update(
        {"invalid": "A valid integer is required."}
    )
    ma.fields.Float.default_error_messages.update(
        {"invalid": "A valid number is required."}
    )
    ma.fields.Boolean.default_error_messages.update(
        {"invalid": "Must be a valid boolean."}
    )
    ma.fields.String.default_error_messages.update(
        {"invalid": "Not a valid string."}
    )
    ma.fields.Email.default_error_messages.update(
        {"invalid": "Enter a valid email address."}
    )
    ma.fields.Date.default_error_messages.update(
        {
            "invalid": "Date has wrong format. Use one of these formats "
            "instead: YYYY-MM-DD.",
            "format": "Date has wrong format. Use one of these formats "
            "instead: YYYY-MM-DD.",
        }
    )
    ma.fields.DateTime.default_error_messages.update(
        {
            "invalid": "Datetime has wrong format. Use one of these formats "
            "instead: YYYY-MM-DDThh:mm[:ss[.uuuuuu]][+HH:MM|-HH:MM|Z].",
        }
    )
    ma.fields.List.default_error_messages.update(
        {"invalid": 'Expected a list of items but got type "{input}".'}
    )


_drf_messages()


class BaseSchema(ma.Schema):
    """Schema base matching DRF's input handling.

    DRF silently ignored unknown and read-only keys in request bodies, so
    load schemas exclude unknown fields rather than rejecting them.
    """

    class Meta:
        unknown = ma.EXCLUDE


class DRFDateTime(ma.fields.DateTime):
    """Datetimes serialised the way DRF did.

    Values are stored as naive UTC. Output is ISO 8601 with ``Z`` in place
    of ``+00:00`` (DRF's default). Input accepts any ISO 8601 string;
    naive values are taken as UTC and aware ones converted to UTC.
    """

    def _serialize(self, value, attr, obj, **kwargs):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        else:
            value = value.astimezone(UTC)
        return value.isoformat().replace("+00:00", "Z")

    def _deserialize(self, value, attr, data, **kwargs):
        if isinstance(value, datetime.datetime):
            parsed = value
        else:
            try:
                parsed = datetime.datetime.fromisoformat(
                    str(value).replace("Z", "+00:00")
                )
            except (TypeError, ValueError) as exc:
                raise self.make_error("invalid", input=value) from exc
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(UTC).replace(tzinfo=None)
        return parsed


class IntOrDigits(ma.fields.Integer):
    """Integer that also accepts the digit strings form bodies carry."""

    def _deserialize(self, value, attr, data, **kwargs):
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            value = int(value)
        return super()._deserialize(value, attr, data, **kwargs)


def choice(choices, **kwargs):
    """A OneOf validator with DRF's wording."""
    return validate.OneOf(
        list(choices), error='"{input}" is not a valid choice.', **kwargs
    )


def max_length(n):
    return validate.Length(
        max=n, error=f"Ensure this field has no more than {n} characters."
    )


def min_value(v):
    return validate.Range(
        min=v, error=f"Ensure this value is greater than or equal to {v}."
    )


def value_range(low, high, error=None):
    return validate.Range(
        min=low,
        max=high,
        error=error or f"Ensure this value is between {low} and {high}.",
    )


def not_blank():
    return validate.Length(min=1, error="This field may not be blank.")


DOI_PATTERN = re.compile("^10.\\d{4,9}/[^\x00-\x1f\x7f-\x9f\\s]+$")


def doi():
    return validate.Regexp(
        DOI_PATTERN,
        error="""Invalid DOI.  A DOI looks like
                                      '10.<digits>/<characters>' with
                                      the restriction that there are no
                                      whitespace or control chars in
                                      <characters>""",
    )


def url_validator():
    return validate.URL(schemes={"http", "https"}, error="Enter a valid URL.")

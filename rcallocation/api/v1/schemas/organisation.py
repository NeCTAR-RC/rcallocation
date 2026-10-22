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

import marshmallow as ma

from rcallocation.api.v1.schemas import base
from rcallocation.api.v1.schemas import fields
from rcallocation import countries
from rcallocation import models


def _country():
    return ma.validate.OneOf(
        sorted(countries.ISO_ALPHA2),
        error='"{input}" is not a valid choice.',
    )


class OrganisationSchema(base.BaseSchema):
    """Public representation (old OrganisationSerializer)."""

    id = ma.fields.Integer(dump_only=True)
    ror_id = ma.fields.String()
    full_name = ma.fields.String()
    short_name = ma.fields.String()
    url = ma.fields.String()
    country = ma.fields.String()
    parent = fields.PrimaryKeyField(models.Organisation, allow_none=True)
    precedes = fields.ManyPrimaryKeyField(models.Organisation)
    enabled = ma.fields.Boolean()
    vetted = ma.fields.Boolean(dump_only=True)


class AdminOrganisationSchema(OrganisationSchema):
    proposed_by = ma.fields.String()
    vetted_by = fields.PrimaryKeyField(models.Approver, allow_none=True)


class AdminOrganisationWriteSchema(base.BaseSchema):
    ror_id = ma.fields.String(load_default="", validate=base.max_length(32))
    full_name = ma.fields.String(
        required=True, validate=[base.not_blank(), base.max_length(200)]
    )
    short_name = ma.fields.String(
        load_default="", validate=base.max_length(16)
    )
    url = ma.fields.String(load_default="", validate=base.max_length(64))
    country = ma.fields.String(required=True, validate=_country())
    parent = fields.PrimaryKeyField(models.Organisation, allow_none=True)
    precedes = fields.ManyPrimaryKeyField(models.Organisation)
    enabled = ma.fields.Boolean(load_default=True)
    proposed_by = ma.fields.String(
        load_default="", validate=base.max_length(64)
    )
    vetted_by = fields.PrimaryKeyField(models.Approver, allow_none=True)


class ProposedOrganisationSchema(base.BaseSchema):
    """A 'type in' proposal from a non-admin user."""

    full_name = ma.fields.String(
        required=True, validate=[base.not_blank(), base.max_length(200)]
    )
    short_name = ma.fields.String(
        required=True, validate=[base.not_blank(), base.max_length(16)]
    )
    url = ma.fields.String(
        required=True,
        validate=[base.not_blank(), base.max_length(64), base.url_validator()],
    )
    country = ma.fields.String(required=True, validate=_country())

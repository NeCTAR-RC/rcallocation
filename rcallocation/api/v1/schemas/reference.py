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

"""Schemas for reference data: zones, sites, service types, resources,
bundles, approvers, usage types, NCRIS facilities, ARDC support."""

import marshmallow as ma

from rcallocation.api.v1.schemas import base
from rcallocation.api.v1.schemas import fields
from rcallocation import choices
from rcallocation import models


class ZoneSchema(base.BaseSchema):
    name = ma.fields.String(
        required=True, validate=[base.not_blank(), base.max_length(32)]
    )
    display_name = ma.fields.String(
        required=True, validate=base.max_length(64)
    )
    enabled = ma.fields.Boolean(load_default=True)


class SiteSchema(base.BaseSchema):
    id = ma.fields.Integer(dump_only=True)
    name = ma.fields.String(
        required=True, validate=[base.not_blank(), base.max_length(32)]
    )
    display_name = ma.fields.String(
        required=True, validate=base.max_length(64)
    )
    enabled = ma.fields.Boolean(load_default=True)


class ServiceTypeField(fields.LookupField):
    def represent(self, obj):
        return obj.catalog_name

    def lookup(self, value):
        from rcallocation.extensions import db

        service_type = db.session.get(models.ServiceType, str(value))
        if service_type is None:
            raise ma.ValidationError(
                f'Invalid pk "{value}" - object does not exist.'
            )
        return service_type


class ResourceSchema(base.BaseSchema):
    id = ma.fields.Integer(dump_only=True)
    name = ma.fields.String(required=True, validate=base.max_length(64))
    service_type = ServiceTypeField(required=True)
    quota_name = ma.fields.String(required=True, validate=base.max_length(32))
    unit = ma.fields.String(required=True, validate=base.max_length(32))
    requestable = ma.fields.Boolean(load_default=True)
    help_text = ma.fields.String(allow_none=True)
    resource_type = ma.fields.String(
        load_default=choices.RESOURCE_INTEGER,
        validate=base.choice([c for c, _ in choices.RESOURCE_TYPES]),
    )
    default = base.IntOrDigits(allow_none=True)


class ServiceTypeSchema(base.BaseSchema):
    catalog_name = ma.fields.String(
        required=True, validate=[base.not_blank(), base.max_length(32)]
    )
    name = ma.fields.String(required=True, validate=base.max_length(64))
    description = ma.fields.String(allow_none=True)
    zones = fields.ManyLookupField(fields.ZoneField())
    notes = ma.fields.String(allow_none=True)
    order = base.IntOrDigits(allow_none=True, validate=base.min_value(0))
    experimental = ma.fields.Boolean(load_default=False)
    location_specific = ma.fields.Boolean(load_default=False)
    resource_set = ma.fields.Nested(
        ResourceSchema, many=True, dump_only=True, attribute="resources"
    )


class BundleSchema(base.BaseSchema):
    id = ma.fields.Integer(dump_only=True)
    name = ma.fields.String(
        required=True, validate=[base.not_blank(), base.max_length(64)]
    )
    description = ma.fields.String(
        required=True, validate=base.max_length(255)
    )
    zone = fields.ZoneField(required=True)
    order = base.IntOrDigits(required=True)
    su_per_year = base.IntOrDigits(required=True)
    quotas = ma.fields.Method("get_quotas", dump_only=True)

    def get_quotas(self, obj):
        return obj.quota_list()


class ApproverSchema(base.BaseSchema):
    id = ma.fields.Integer(dump_only=True)
    username = ma.fields.Email(required=True)
    display_name = ma.fields.String(
        required=True, validate=base.max_length(64)
    )
    sites = fields.ManyPrimaryKeyField(models.Site)


class UsageTypeSchema(base.BaseSchema):
    id = ma.fields.Integer(dump_only=True)
    name = ma.fields.String(
        required=True, validate=[base.not_blank(), base.max_length(40)]
    )
    enabled = ma.fields.Boolean(load_default=True)


class NCRISFacilitySchema(base.BaseSchema):
    id = ma.fields.Integer(dump_only=True)
    name = ma.fields.String(
        required=True, validate=[base.not_blank(), base.max_length(200)]
    )
    short_name = ma.fields.String(
        required=True, validate=[base.not_blank(), base.max_length(200)]
    )


class ARDCSupportSchema(base.BaseSchema):
    id = ma.fields.Integer(dump_only=True)
    name = ma.fields.String(
        required=True, validate=[base.not_blank(), base.max_length(200)]
    )
    short_name = ma.fields.String(
        required=True, validate=[base.not_blank(), base.max_length(200)]
    )
    project = ma.fields.Boolean(load_default=True)
    project_id = ma.fields.String(
        load_default="", validate=base.max_length(20)
    )
    enabled = ma.fields.Boolean(load_default=True)
    rank = base.IntOrDigits(load_default=100)
    explain = ma.fields.Boolean(load_default=False)

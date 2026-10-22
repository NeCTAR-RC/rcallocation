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

"""Chief investigators, publications and grants."""

import marshmallow as ma

from rcallocation.api.v1.schemas import allocation as allocation_schemas
from rcallocation.api.v1.schemas import base


class ChiefInvestigatorSchema(allocation_schemas.NestedInvestigatorSchema):
    id = ma.fields.Integer(dump_only=True)
    allocation = base.IntOrDigits(required=True, attribute="allocation_id")


class PublicationSchema(allocation_schemas.NestedPublicationSchema):
    id = ma.fields.Integer(dump_only=True)
    allocation = base.IntOrDigits(required=True, attribute="allocation_id")


class GrantSchema(allocation_schemas.NestedGrantSchema):
    id = ma.fields.Integer(dump_only=True)
    allocation = base.IntOrDigits(required=True, attribute="allocation_id")

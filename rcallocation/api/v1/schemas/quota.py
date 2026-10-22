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


class QuotaSchema(base.BaseSchema):
    """A quota row as ``/v1/quotas/`` returns it.

    ``resource`` is the resource id here (unlike the codename strings in
    an allocation's ``quotas`` list) and ``zone`` the zone name.
    """

    id = ma.fields.Integer()
    zone = ma.fields.Method("get_zone")
    allocation = ma.fields.Method("get_allocation")
    requested_quota = ma.fields.Integer()
    quota = ma.fields.Integer()
    resource = ma.fields.Integer(attribute="resource_id")

    def get_zone(self, obj):
        try:
            return obj.group.zone_id
        except AttributeError:
            return ''

    def get_allocation(self, obj):
        try:
            return obj.group.allocation_id
        except AttributeError:
            return ''


class QuotaCreateSchema(base.BaseSchema):
    allocation = base.IntOrDigits(required=True)
    resource = base.IntOrDigits(required=True)
    zone = ma.fields.String(required=True)
    quota = base.IntOrDigits(load_default=0, validate=base.min_value(-1))
    requested_quota = base.IntOrDigits(
        load_default=0, validate=base.min_value(-1)
    )

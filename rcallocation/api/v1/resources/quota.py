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

"""Quota row endpoints (``/v1/quotas/``)."""

from rcallocation.api.v1 import base
from rcallocation.api.v1 import filtering
from rcallocation.api.v1.resources import allocation as allocation_resource
from rcallocation.api.v1.schemas import quota as schemas
from rcallocation import choices
from rcallocation.common import exceptions
from rcallocation.common import policies
from rcallocation.extensions import db
from rcallocation import manager
from rcallocation import models


Quota = models.Quota
QuotaGroup = models.QuotaGroup

blp = base.v1_blueprint(
    "quotas", __name__, "quotas", description="Allocation quota rows"
)


class QuotaFilterSet(filtering.FilterSet):
    filters = {
        "resource": filtering.F(Quota.resource_id),
        "group__allocation": filtering.F(
            QuotaGroup.allocation_id, joins=[Quota.group]
        ),
        "group__zone": filtering.F(QuotaGroup.zone_id, joins=[Quota.group]),
        "group__service_type": filtering.F(
            QuotaGroup.service_type_id, joins=[Quota.group]
        ),
    }


class QuotaResource(allocation_resource.AllocationResource):
    POLICY_PREFIX = policies.QUOTA_PREFIX
    schema = schemas.QuotaSchema()
    admin_schema = None
    public_schema = None
    filterset = QuotaFilterSet
    public_filterset = None

    def visible_query(self):
        query = db.session.query(Quota)
        if self.caller_kind == base.ANONYMOUS:
            return query
        if self.authorize("list:all", do_raise=False):
            return query
        return query.filter(
            Quota.group.has(QuotaGroup.allocation.has(self.own_filter()))
        )

    def get_visible(self, quota_id):
        return self.get_or_404(Quota, quota_id, query=self.visible_query())


@blp.route("/")
class QuotaList(QuotaResource):
    def get(self):
        self.require("list")
        query = self.filter(self.visible_query()).order_by(Quota.id)
        return self.paginate(query)

    def post(self):
        self.require("create")
        data = self.body(schemas.QuotaCreateSchema())
        quota = manager.Manager(self.context).create_quota(
            data, is_write_admin=self.is_write_admin
        )
        return self.dump(quota), 201


@blp.route("/<int:quota_id>/")
class QuotaItem(QuotaResource):
    def get(self, quota_id):
        self.require("get")
        return self.dump(self.get_visible(quota_id))

    def put(self, quota_id):
        self.require_authenticated()
        raise exceptions.MethodNotAllowed("PUT")

    def patch(self, quota_id):
        self.require_authenticated()
        raise exceptions.MethodNotAllowed("PATCH")

    def delete(self, quota_id):
        self.require_authenticated()
        quota = self.get_visible(quota_id)
        self.require_object("delete", quota)
        allocation = quota.group.allocation
        self.require_live(allocation)
        self.require_state(allocation, choices.PENDING_STATUSES)
        manager.Manager(self.context).delete_quota(quota)
        return "", 204

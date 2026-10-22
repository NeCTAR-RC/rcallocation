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

"""Reference data endpoints.

Each resource is world readable and admin writable, with DELETE answering
405 (403 for callers who may not write), as the old ``NoDestroyViewSet``
did. Approvers are the exception: only admins and approvers may read
them.
"""

from rcallocation.api.v1 import base
from rcallocation.api.v1 import filtering
from rcallocation.api.v1.schemas import reference as schemas
from rcallocation.common import config
from rcallocation.common import exceptions
from rcallocation.common import policies
from rcallocation.extensions import db
from rcallocation import manager
from rcallocation import models


class ReferenceResource(base.Resource):
    model = None
    order_by = None
    unique = ()
    unique_together = ()
    write_schema = None
    #: Primary key type; non-matching ids answer 404 after the role check
    pk_type = int

    def lookup(self, ident):
        if self.pk_type is int:
            try:
                ident = int(ident)
            except (TypeError, ValueError):
                raise exceptions.NotFound()
        return self.get_or_404(self.model, ident)

    def query(self):
        query = db.session.query(self.model)
        if self.order_by is not None:
            query = query.order_by(*self.order_by)
        return query

    def _list(self):
        self.require("list")
        return self.paginate(self.filter(self.query()))

    def _create(self):
        self.require("create")
        data = self.body(self.write_schema)
        obj = manager.Manager(self.context).create_simple(
            self.model,
            data,
            unique=self.unique,
            unique_together=self.unique_together,
        )
        return self.dump(obj), 201

    def _get(self, ident):
        self.require("get")
        return self.dump(self.lookup(ident))

    def _update(self, ident, partial):
        # Role check first so a non-admin gets 403 before 404 (as DRF did).
        self.require("update")
        obj = self.lookup(ident)
        schema = type(self.write_schema)(partial=partial)
        data = self.body(schema)
        obj = manager.Manager(self.context).update_simple(
            obj,
            data,
            unique=self.unique,
            unique_together=self.unique_together,
        )
        return self.dump(obj)

    def _delete(self):
        # Non-admins get 403, admins find there is no such method.
        self.require("update")
        raise exceptions.MethodNotAllowed("DELETE")


class ReferenceList(ReferenceResource):
    def get(self):
        return self._list()

    def post(self):
        return self._create()


class ReferenceItem(ReferenceResource):
    def get(self, ident):
        return self._get(ident)

    def put(self, ident):
        return self._update(ident, partial=False)

    def patch(self, ident):
        return self._update(ident, partial=True)

    def delete(self, ident):
        return self._delete()


# -- sites -------------------------------------------------------------------

sites_blp = base.v1_blueprint(
    "sites", __name__, "sites", description="Nectar sites"
)


class SiteBase(ReferenceResource):
    POLICY_PREFIX = policies.SITE_PREFIX
    model = models.Site
    schema = schemas.SiteSchema()
    write_schema = schemas.SiteSchema()
    order_by = (models.Site.id,)
    unique = ("name",)


@sites_blp.route("/")
class SiteList(SiteBase, ReferenceList):
    pass


@sites_blp.route("/<ident>/")
class SiteItem(SiteBase, ReferenceItem):
    pass


# -- zones -------------------------------------------------------------------

zones_blp = base.v1_blueprint(
    "zones", __name__, "zones", description="Resource zones"
)


class ZoneBase(ReferenceResource):
    POLICY_PREFIX = policies.ZONE_PREFIX
    model = models.Zone
    schema = schemas.ZoneSchema()
    write_schema = schemas.ZoneSchema()
    order_by = (models.Zone.display_name,)
    unique = ("name",)
    pk_type = str


@zones_blp.route("/")
class ZoneList(ZoneBase, ReferenceList):
    pass


@zones_blp.route("/compute_homes/")
class ZoneComputeHomes(ZoneBase):
    def get(self):
        self.require("list")
        return config.get_mappings().home_zones


@zones_blp.route("/<ident>/")
class ZoneItem(ZoneBase, ReferenceItem):
    pass


# -- service types -------------------------------------------------------------

service_types_blp = base.v1_blueprint(
    "service_types",
    __name__,
    "service-types",
    description="Service types grouping quota resources",
)


class ServiceTypeBase(ReferenceResource):
    POLICY_PREFIX = policies.SERVICE_TYPE_PREFIX
    model = models.ServiceType
    schema = schemas.ServiceTypeSchema()
    write_schema = schemas.ServiceTypeSchema()
    order_by = (models.ServiceType.order, models.ServiceType.name)
    unique = ("catalog_name",)
    pk_type = str


@service_types_blp.route("/")
class ServiceTypeList(ServiceTypeBase, ReferenceList):
    pass


@service_types_blp.route("/<ident>/")
class ServiceTypeItem(ServiceTypeBase, ReferenceItem):
    pass


# -- resources -------------------------------------------------------------------

resources_blp = base.v1_blueprint(
    "resources", __name__, "resources", description="Quota resources"
)


class ResourceFilterSet(filtering.FilterSet):
    filters = {
        "service_type": filtering.F(models.Resource.service_type_id),
        "requestable": filtering.F(models.Resource.requestable),
        "quota_name": filtering.F(models.Resource.quota_name),
    }


class ResourceBase(ReferenceResource):
    POLICY_PREFIX = policies.RESOURCE_PREFIX
    model = models.Resource
    schema = schemas.ResourceSchema()
    write_schema = schemas.ResourceSchema()
    order_by = (models.Resource.id,)
    unique_together = (("service_type", "quota_name"),)
    filterset = ResourceFilterSet


@resources_blp.route("/")
class ResourceList(ResourceBase, ReferenceList):
    pass


@resources_blp.route("/<ident>/")
class ResourceItem(ResourceBase, ReferenceItem):
    pass


# -- bundles -----------------------------------------------------------------------

bundles_blp = base.v1_blueprint(
    "bundles", __name__, "bundles", description="Resource bundles"
)


class BundleBase(ReferenceResource):
    POLICY_PREFIX = policies.BUNDLE_PREFIX
    model = models.Bundle
    schema = schemas.BundleSchema()
    write_schema = schemas.BundleSchema()
    order_by = (models.Bundle.order,)
    unique = ("name",)


@bundles_blp.route("/")
class BundleList(BundleBase, ReferenceList):
    pass


@bundles_blp.route("/<ident>/")
class BundleItem(BundleBase, ReferenceItem):
    pass


# -- NCRIS facilities ---------------------------------------------------------------

ncris_blp = base.v1_blueprint(
    "ncris_facilities",
    __name__,
    "ncris-facilities",
    description="NCRIS facilities",
)


class NCRISFacilityBase(ReferenceResource):
    POLICY_PREFIX = policies.NCRIS_FACILITY_PREFIX
    model = models.NCRISFacility
    schema = schemas.NCRISFacilitySchema()
    write_schema = schemas.NCRISFacilitySchema()
    order_by = (models.NCRISFacility.id,)
    unique = ("name", "short_name")


@ncris_blp.route("/")
class NCRISFacilityList(NCRISFacilityBase, ReferenceList):
    pass


@ncris_blp.route("/<ident>/")
class NCRISFacilityItem(NCRISFacilityBase, ReferenceItem):
    pass


# -- ARDC support ---------------------------------------------------------------------

ardc_blp = base.v1_blueprint(
    "ardc_projects",
    __name__,
    "ardc-projects",
    description="ARDC support programs and projects",
)


class ARDCSupportFilterSet(filtering.FilterSet):
    filters = {
        "enabled": filtering.F(models.ARDCSupport.enabled),
        "project": filtering.F(models.ARDCSupport.project),
    }


class ARDCSupportBase(ReferenceResource):
    POLICY_PREFIX = policies.ARDC_SUPPORT_PREFIX
    model = models.ARDCSupport
    schema = schemas.ARDCSupportSchema()
    write_schema = schemas.ARDCSupportSchema()
    order_by = (models.ARDCSupport.id,)
    unique = ("name", "short_name")
    filterset = ARDCSupportFilterSet


@ardc_blp.route("/")
class ARDCSupportList(ARDCSupportBase, ReferenceList):
    pass


@ardc_blp.route("/<ident>/")
class ARDCSupportItem(ARDCSupportBase, ReferenceItem):
    pass


# -- usage types ---------------------------------------------------------------------

usage_types_blp = base.v1_blueprint(
    "usage_types", __name__, "usage-types", description="Usage types"
)


class UsageTypeFilterSet(filtering.FilterSet):
    filters = {
        "enabled": filtering.F(models.UsageType.enabled),
        "name": filtering.F(models.UsageType.name, ["exact", "iexact"]),
    }


class UsageTypeBase(ReferenceResource):
    POLICY_PREFIX = policies.USAGE_TYPE_PREFIX
    model = models.UsageType
    schema = schemas.UsageTypeSchema()
    write_schema = schemas.UsageTypeSchema()
    order_by = (models.UsageType.id,)
    filterset = UsageTypeFilterSet


@usage_types_blp.route("/")
class UsageTypeList(UsageTypeBase, ReferenceList):
    pass


@usage_types_blp.route("/<ident>/")
class UsageTypeItem(UsageTypeBase, ReferenceItem):
    pass


# -- approvers ----------------------------------------------------------------------

approvers_blp = base.v1_blueprint(
    "approvers", __name__, "approvers", description="Allocation approvers"
)


class ApproverFilterSet(filtering.FilterSet):
    filters = {
        "username": filtering.F(models.Approver.username, ["exact", "iexact"]),
    }


class ApproverBase(ReferenceResource):
    POLICY_PREFIX = policies.APPROVER_PREFIX
    model = models.Approver
    schema = schemas.ApproverSchema()
    write_schema = schemas.ApproverSchema()
    order_by = (models.Approver.id,)
    unique = ("username",)
    filterset = ApproverFilterSet


@approvers_blp.route("/")
class ApproverList(ApproverBase, ReferenceList):
    pass


@approvers_blp.route("/<ident>/")
class ApproverItem(ApproverBase, ReferenceItem):
    pass


BLUEPRINTS = [
    sites_blp,
    zones_blp,
    service_types_blp,
    resources_blp,
    bundles_blp,
    ncris_blp,
    ardc_blp,
    usage_types_blp,
    approvers_blp,
]

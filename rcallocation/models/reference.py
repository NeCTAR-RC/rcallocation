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

"""Reference data: sites, approvers, zones, service types, resources,
bundles, usage types, NCRIS facilities and ARDC support programs."""

from rcallocation import choices
from rcallocation.extensions import db
from rcallocation.models import base


class Site(db.Model):
    """A Site represents site in the Nectar federation that the allocation
    system knows about.
    """

    __tablename__ = "site"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), nullable=False, unique=True)
    display_name = db.Column(db.String(64), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self):
        return f"<Site {self.name}>"


class Approver(db.Model):
    """An Approver is a person who is authorized to approve local
    or national allocations for or on behalf of a Site.  An
    approver may be authorized to approve for multiple sites.
    This information is "advisory"; i.e. it is used to warn an
    approver if they are about to make decisions that require
    another site's authority.

    This represents the current state only.  It is not advisable
    to attempt to use it to determine which Site has approved
    an allocation request.
    """

    __tablename__ = "approver"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(254), nullable=False, unique=True)
    display_name = db.Column(db.String(64), nullable=False)

    sites = db.relationship(
        Site,
        secondary=base.approver_site,
        lazy="selectin",
        order_by=Site.id,
    )

    def __repr__(self):
        return f"<Approver {self.username}>"


class Zone(db.Model):
    """A Zone represents a resource pool in which quotas may be set.
    There is a distinguished Zone ("nectar") for resources or capabilities
    that are deemed to be global / Nectar-wide.

    The relationship between these zones and nova "availability zones"
    is not necessarily 1-to-1, even discounting the "nectar" zone.
    """

    __tablename__ = "zone"

    name = db.Column(db.String(32), primary_key=True)
    display_name = db.Column(db.String(64), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self):
        return f"<Zone {self.name}>"


class ServiceType(db.Model):
    """A ServiceType is a group of related Resources provided by a
    logical service.  For example the "Compute" service type groups
    the instance count and VCPU count resources and the resources that
    represent the permission to launch memory and cpu-intensive flavors.
    """

    __tablename__ = "service_type"

    catalog_name = db.Column(db.String(32), primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    description = db.Column(base.LongText, nullable=True)
    notes = db.Column(base.LongText, nullable=True)
    order = db.Column(db.Integer, nullable=True)
    experimental = db.Column(db.Boolean, nullable=False, default=False)
    location_specific = db.Column(db.Boolean, nullable=False, default=False)

    zones = db.relationship(
        Zone,
        secondary=base.service_type_zone,
        lazy="selectin",
        order_by=Zone.display_name,
    )
    resources = db.relationship(
        "Resource",
        back_populates="service_type",
        lazy="selectin",
        order_by="Resource.id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # A column clause, not a string: ``order`` is a reserved word and
        # a quoted name in text would be a string literal on MySQL.
        db.CheckConstraint(
            db.column("order") >= 0, name="ck_service_type_order"
        ),
    )

    def __repr__(self):
        return f"<ServiceType {self.catalog_name}>"


class Resource(db.Model):
    """A Resource represents a resource or capability that is controlled
    / rationed by way of quotas.  Resources that are numerically quantifiable
    have resource type "integer" and unit; e.g RAM is measured in gigabytes.
    Resources that represent a capability have a resource type "boolean".
    """

    __tablename__ = "resource"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    service_type_id = db.Column(
        db.String(32),
        db.ForeignKey("service_type.catalog_name", ondelete="CASCADE"),
        nullable=False,
    )
    quota_name = db.Column(db.String(32), nullable=False)
    unit = db.Column(db.String(32), nullable=False)
    requestable = db.Column(db.Boolean, nullable=False, default=True)
    help_text = db.Column(base.LongText, nullable=True)
    resource_type = db.Column(
        db.String(10), nullable=False, default=choices.RESOURCE_INTEGER
    )
    default = db.Column(db.Integer, nullable=True)

    service_type = db.relationship(
        ServiceType, back_populates="resources", lazy="joined"
    )

    __table_args__ = (
        db.UniqueConstraint(
            "service_type_id", "quota_name", name="uq_resource_st_quota_name"
        ),
    )

    @property
    def codename(self):
        return f"{self.service_type_id}.{self.quota_name}"

    @classmethod
    def by_codename(cls, codename):
        """Find the Resource for a 'service_name.resource_name' codename."""
        parts = codename.split(".")
        if len(parts) != 2:
            return None
        return (
            db.session.query(cls)
            .filter_by(service_type_id=parts[0], quota_name=parts[1])
            .first()
        )

    def __repr__(self):
        return f"<Resource {self.codename}>"


class Bundle(db.Model):
    """A Bundle is a collection of BundleQuotas

    Each Bundle can have one or more BundleQuotas and a Bundle can
    be associated with an AllocationRequest to assign these resource
    quotas.

    zone : The zone associated with all BundleQuotas
    order : The order of bundles when listed for display.
    """

    __tablename__ = "bundle"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, unique=True)
    description = db.Column(db.String(255), nullable=False)
    zone_id = db.Column(
        db.String(32), db.ForeignKey("zone.name"), nullable=False
    )
    order = db.Column(db.Integer, nullable=False)
    su_per_year = db.Column(db.Integer, nullable=False)

    zone = db.relationship(Zone, lazy="joined")
    bundle_quotas = db.relationship(
        "BundleQuota",
        back_populates="bundle",
        lazy="selectin",
        order_by="BundleQuota.id",
        cascade="all, delete-orphan",
    )

    def get_quota(self, resource_codename):
        for bq in self.bundle_quotas:
            if bq.resource.codename == resource_codename:
                return bq.quota
        return None

    def quota_list(self):
        return [bq.quota_dict() for bq in self.bundle_quotas]

    def __repr__(self):
        return f"<Bundle {self.name}>"


class BundleQuota(db.Model):
    """Defines a limit for a resource of a Bundle"""

    __tablename__ = "bundle_quota"

    id = db.Column(db.Integer, primary_key=True)
    bundle_id = db.Column(
        db.Integer,
        db.ForeignKey("bundle.id", ondelete="CASCADE"),
        nullable=False,
    )
    resource_id = db.Column(
        db.Integer,
        db.ForeignKey("resource.id", ondelete="CASCADE"),
        nullable=False,
    )
    quota = db.Column(db.Integer, nullable=False, default=0)

    bundle = db.relationship(Bundle, back_populates="bundle_quotas")
    resource = db.relationship(Resource, lazy="joined")

    __table_args__ = (
        db.UniqueConstraint(
            "bundle_id", "resource_id", name="uq_bundle_quota_bundle_resource"
        ),
        db.CheckConstraint("quota >= -1", name="ck_bundle_quota_quota"),
    )

    def quota_dict(self):
        return {
            'zone': self.bundle.zone_id,
            'resource': self.resource.codename,
            'quota': self.quota,
            'requested_quota': self.quota,
        }


class UsageType(db.Model):
    __tablename__ = "usage_type"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(40), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=base.utcnow)

    def __repr__(self):
        return f"<UsageType {self.name}>"


class NCRISFacility(db.Model):
    __tablename__ = "ncris_facility"

    id = db.Column(db.Integer, primary_key=True)
    #: Full NCRIS facility name
    name = db.Column(db.String(200), nullable=False, unique=True)
    #: Common short name or acronym
    short_name = db.Column(db.String(200), nullable=False, unique=True)

    def __repr__(self):
        return f"<NCRISFacility {self.short_name}>"


class ARDCSupport(db.Model):
    __tablename__ = "ardc_support"

    id = db.Column(db.Integer, primary_key=True)
    #: Full ARDC program or project name
    name = db.Column(db.String(200), nullable=False, unique=True)
    #: Common short name or acronym
    short_name = db.Column(db.String(200), nullable=False, unique=True)
    #: True for projects, false for programs
    project = db.Column(db.Boolean, nullable=False, default=True)
    project_id = db.Column(db.String(20), nullable=False, default="")
    #: False hides the program or project from users
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    #: Primary ranking in menus; smaller values mean earlier
    rank = db.Column(db.Integer, nullable=False, default=100)
    #: When true, the ARDC Support Details field should provide details
    explain = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return f"<ARDCSupport {self.short_name}>"

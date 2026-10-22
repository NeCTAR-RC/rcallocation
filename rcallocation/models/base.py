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

"""Shared model plumbing: the ``db`` handle, types and association tables.

Conventions (matching the Django schema this replaces): 32-bit integer
surrogate keys, ``String(n)`` for bounded text, ``LongText`` for unbounded
text, naive UTC datetimes. Many-to-many association tables use composite
primary keys instead of Django's surrogate ``id``.
"""

import datetime

from sqlalchemy.dialects import mysql

from rcallocation.extensions import db


def utcnow():
    """Naive UTC now, the representation stored in the database."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


LongText = db.Text().with_variant(mysql.LONGTEXT(), "mysql")


approver_site = db.Table(
    "approver_site",
    db.Column(
        "approver_id",
        db.Integer,
        db.ForeignKey("approver.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "site_id",
        db.Integer,
        db.ForeignKey("site.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

service_type_zone = db.Table(
    "service_type_zone",
    db.Column(
        "service_type_id",
        db.String(32),
        db.ForeignKey("service_type.catalog_name", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "zone_id",
        db.String(32),
        db.ForeignKey("zone.name", ondelete="CASCADE"),
        primary_key=True,
    ),
)

organisation_precedes = db.Table(
    "organisation_precedes",
    db.Column(
        "from_organisation_id",
        db.Integer,
        db.ForeignKey("organisation.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "to_organisation_id",
        db.Integer,
        db.ForeignKey("organisation.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


def _allocation_m2m(name, target_column, target_fk, target_type=db.Integer):
    return db.Table(
        name,
        db.Column(
            "allocation_id",
            db.Integer,
            db.ForeignKey("allocation_request.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        db.Column(
            target_column,
            target_type,
            db.ForeignKey(target_fk, ondelete="CASCADE"),
            primary_key=True,
        ),
    )


allocation_usage_type = _allocation_m2m(
    "allocation_usage_type", "usage_type_id", "usage_type.id"
)
allocation_ncris_facility = _allocation_m2m(
    "allocation_ncris_facility", "ncris_facility_id", "ncris_facility.id"
)
allocation_ardc_support = _allocation_m2m(
    "allocation_ardc_support", "ardc_support_id", "ardc_support.id"
)
allocation_organisation = _allocation_m2m(
    "allocation_organisation", "organisation_id", "organisation.id"
)

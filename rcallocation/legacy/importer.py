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

"""Copy the allocation tables from the nectar-dashboard database.

The dashboard's Django app stored the same entities in ``rcallocation_*``
tables with surrogate ids on every many-to-many table. This copies the
rows into the service's schema in dependency order, keeping primary keys
and timestamps, so history chains and references stay intact. Self
references (organisation parents, allocation history parents) are filled
in a second pass.

Run with ``rcallocation-manage import-legacy --source-connection URL``.
A dry run only reports counts and dangling references.
"""

import dataclasses

from flask import current_app
from oslo_log import log as logging
import sqlalchemy as sa

from rcallocation.extensions import db


LOG = logging.getLogger(__name__)


@dataclasses.dataclass
class TableSpec:
    legacy: str
    target: str
    rename: dict = dataclasses.field(default_factory=dict)
    drop: tuple = ()
    #: Self-referencing column filled in a second pass
    deferred: str = None


TABLES = [
    TableSpec("rcallocation_site", "site"),
    TableSpec("rcallocation_approver", "approver"),
    TableSpec("rcallocation_approver_sites", "approver_site", drop=("id",)),
    TableSpec("rcallocation_zone", "zone"),
    TableSpec("rcallocation_servicetype", "service_type"),
    TableSpec(
        "rcallocation_servicetype_zones",
        "service_type_zone",
        rename={"servicetype_id": "service_type_id"},
        drop=("id",),
    ),
    TableSpec("rcallocation_resource", "resource"),
    TableSpec("rcallocation_bundle", "bundle"),
    TableSpec("rcallocation_bundlequota", "bundle_quota"),
    TableSpec("rcallocation_usagetype", "usage_type"),
    TableSpec("rcallocation_ncrisfacility", "ncris_facility"),
    TableSpec("rcallocation_ardcsupport", "ardc_support"),
    TableSpec(
        "rcallocation_organisation", "organisation", deferred="parent_id"
    ),
    TableSpec(
        "rcallocation_organisation_precedes",
        "organisation_precedes",
        drop=("id",),
    ),
    TableSpec(
        "rcallocation_allocationrequest",
        "allocation_request",
        deferred="parent_request_id",
    ),
    TableSpec(
        "rcallocation_allocationrequest_usage_types",
        "allocation_usage_type",
        rename={
            "allocationrequest_id": "allocation_id",
            "usagetype_id": "usage_type_id",
        },
        drop=("id",),
    ),
    TableSpec(
        "rcallocation_allocationrequest_ncris_facilities",
        "allocation_ncris_facility",
        rename={
            "allocationrequest_id": "allocation_id",
            "ncrisfacility_id": "ncris_facility_id",
        },
        drop=("id",),
    ),
    TableSpec(
        "rcallocation_allocationrequest_ardc_support",
        "allocation_ardc_support",
        rename={
            "allocationrequest_id": "allocation_id",
            "ardcsupport_id": "ardc_support_id",
        },
        drop=("id",),
    ),
    TableSpec(
        "rcallocation_allocationrequest_supported_organisations",
        "allocation_organisation",
        rename={"allocationrequest_id": "allocation_id"},
        drop=("id",),
    ),
    TableSpec("rcallocation_quotagroup", "quota_group"),
    TableSpec("rcallocation_quota", "quota"),
    TableSpec("rcallocation_chiefinvestigator", "chief_investigator"),
    TableSpec("rcallocation_publication", "publication"),
    TableSpec("rcallocation_grant", "grant"),
]

# (table, column, referenced table) pairs checked for dangling references
REFERENCE_CHECKS = [
    (
        "rcallocation_allocationrequest",
        "parent_request_id",
        "rcallocation_allocationrequest",
    ),
    (
        "rcallocation_allocationrequest",
        "associated_site_id",
        "rcallocation_site",
    ),
    ("rcallocation_allocationrequest", "bundle_id", "rcallocation_bundle"),
    ("rcallocation_organisation", "parent_id", "rcallocation_organisation"),
    ("rcallocation_organisation", "vetted_by_id", "rcallocation_approver"),
    (
        "rcallocation_chiefinvestigator",
        "primary_organisation_id",
        "rcallocation_organisation",
    ),
    (
        "rcallocation_quotagroup",
        "allocation_id",
        "rcallocation_allocationrequest",
    ),
    ("rcallocation_quota", "group_id", "rcallocation_quotagroup"),
]


class ImportError_(Exception):
    pass


@dataclasses.dataclass
class Summary:
    dry_run: bool
    counts: dict = dataclasses.field(default_factory=dict)
    copied: dict = dataclasses.field(default_factory=dict)
    orphans: dict = dataclasses.field(default_factory=dict)
    ignored_columns: dict = dataclasses.field(default_factory=dict)
    checks: list = dataclasses.field(default_factory=list)

    def format(self):
        lines = ["Dry run" if self.dry_run else "Import complete", ""]
        width = max(len(t) for t in self.counts) if self.counts else 10
        lines.append(f"{'legacy table':<{width}}  source  copied")
        for table, count in self.counts.items():
            copied = self.copied.get(table, "-")
            lines.append(f"{table:<{width}}  {count:>6}  {copied!s:>6}")
        if self.ignored_columns:
            lines.append("")
            lines.append("Ignored source columns (no target column):")
            for table, columns in self.ignored_columns.items():
                lines.append(f"  {table}: {', '.join(sorted(columns))}")
        lines.append("")
        if self.orphans:
            lines.append("Dangling references in the source:")
            for key, count in self.orphans.items():
                lines.append(f"  {key}: {count}")
        else:
            lines.append("No dangling references in the source.")
        for check in self.checks:
            lines.append(check)
        return "\n".join(lines)


def _schema_is_current():
    """True when the target database is at the latest alembic revision."""
    from alembic.config import Config
    from alembic import migration as alembic_migration
    from alembic import script as alembic_script

    directory = current_app.extensions["migrate"].directory
    config = Config()
    config.set_main_option("script_location", directory)
    heads = set(alembic_script.ScriptDirectory.from_config(config).get_heads())
    with db.engine.connect() as connection:
        current = alembic_migration.MigrationContext.configure(
            connection
        ).get_current_revision()
    return current in heads


def _target_empty():
    with db.engine.connect() as connection:
        for spec in TABLES:
            table = db.metadata.tables[spec.target]
            count = connection.execute(
                sa.select(sa.func.count()).select_from(table)
            ).scalar()
            if count:
                return False
    return True


def _reflect_source(engine):
    metadata = sa.MetaData()
    names = {spec.legacy for spec in TABLES} | {
        t for _, _, t in REFERENCE_CHECKS
    }
    inspector = sa.inspect(engine)
    existing = set(inspector.get_table_names())
    missing = sorted(names - existing)
    if missing:
        raise ImportError_(
            f"Source database is missing tables: {', '.join(missing)}"
        )
    metadata.reflect(bind=engine, only=sorted(names))
    return metadata


def _count(connection, table):
    return connection.execute(
        sa.select(sa.func.count()).select_from(table)
    ).scalar()


def _orphans(connection, metadata, summary):
    for table_name, column, ref_name in REFERENCE_CHECKS:
        table = metadata.tables[table_name]
        ref = metadata.tables[ref_name]
        column_obj = table.c[column]
        query = (
            sa.select(sa.func.count())
            .select_from(table)
            .where(
                column_obj.is_not(None),
                ~column_obj.in_(sa.select(ref.c.id)),
            )
        )
        count = connection.execute(query).scalar()
        if count:
            summary.orphans[f"{table_name}.{column}"] = count


def _convert_row(spec, row, target_columns, summary):
    data = {}
    for key, value in row.items():
        if key in spec.drop:
            continue
        key = spec.rename.get(key, key)
        if key not in target_columns:
            summary.ignored_columns.setdefault(spec.legacy, set()).add(key)
            continue
        data[key] = value
    return data


def _copy_table(source, spec, metadata, batch_size, summary, write):
    legacy = metadata.tables[spec.legacy]
    target = db.metadata.tables[spec.target]
    target_columns = set(target.c.keys())
    deferred_updates = []
    copied = 0
    with source.connect() as read:
        result = read.execute(sa.select(legacy)).mappings()
        batch = []
        for row in result:
            data = _convert_row(spec, dict(row), target_columns, summary)
            if spec.deferred and data.get(spec.deferred) is not None:
                deferred_updates.append((data["id"], data[spec.deferred]))
                data[spec.deferred] = None
            batch.append(data)
            if len(batch) >= batch_size:
                write.execute(target.insert(), batch)
                copied += len(batch)
                batch = []
        if batch:
            write.execute(target.insert(), batch)
            copied += len(batch)
        if deferred_updates:
            column = target.c[spec.deferred]
            for ident, value in deferred_updates:
                write.execute(
                    target.update()
                    .where(target.c.id == ident)
                    .values({column: value})
                )
    summary.copied[spec.legacy] = copied


def _verify(summary, connection):
    for spec in TABLES:
        target = db.metadata.tables[spec.target]
        count = _count(connection, target)
        expected = summary.counts[spec.legacy]
        status = "ok" if count == expected else "MISMATCH"
        if status != "ok":
            summary.checks.append(
                f"{spec.target}: {count} rows, expected {expected} ({status})"
            )
    quota = db.metadata.tables["quota"]
    total = connection.execute(
        sa.select(
            sa.func.coalesce(sa.func.sum(quota.c.quota), 0),
            sa.func.coalesce(sa.func.sum(quota.c.requested_quota), 0),
        )
    ).one()
    summary.checks.append(
        f"quota totals: quota={total[0]} requested_quota={total[1]}"
    )


def run(
    source_connection,
    dry_run=False,
    batch_size=1000,
    allow_non_empty=False,
    check_schema=True,
):
    """Copy every legacy table into the service database.

    Returns a :class:`Summary`. Raises :class:`ImportError_` when the
    source is incomplete or the target is not ready.
    """
    summary = Summary(dry_run=dry_run)
    source = sa.create_engine(source_connection)
    metadata = _reflect_source(source)

    with source.connect() as connection:
        for spec in TABLES:
            summary.counts[spec.legacy] = _count(
                connection, metadata.tables[spec.legacy]
            )
        _orphans(connection, metadata, summary)

    if check_schema and not _schema_is_current():
        raise ImportError_(
            "Target database schema is not at the latest revision; run "
            "'rcallocation-manage db upgrade' first."
        )
    if not allow_non_empty and not _target_empty():
        raise ImportError_(
            "Target database already holds allocation data; pass "
            "--allow-non-empty to copy anyway."
        )
    if dry_run:
        return summary

    # One transaction for the whole copy: a failure part way through
    # leaves the target empty instead of half populated.
    with db.engine.begin() as write:
        for spec in TABLES:
            LOG.info("Copying %s -> %s", spec.legacy, spec.target)
            _copy_table(source, spec, metadata, batch_size, summary, write)
        _verify(summary, write)
    return summary

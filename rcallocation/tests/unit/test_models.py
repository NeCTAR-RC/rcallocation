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

"""Schema checks that SQLite cannot catch.

The unit tests run on SQLite, where a CHECK constraint comparing the
string literal ``"order"`` with a number passes silently. MySQL rejects
every insert against such a constraint, so the DDL is compiled for the
MySQL dialect here and inspected.
"""

import importlib.util
import io
import pathlib

from alembic import migration
from alembic import operations
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy import schema

import rcallocation
from rcallocation.extensions import db
from rcallocation.tests.unit import base


MIGRATIONS = (
    pathlib.Path(rcallocation.__file__).parent / "migrations" / "versions"
)


def _mysql_ddl(table):
    return str(schema.CreateTable(table).compile(dialect=mysql.dialect()))


class ModelDDLTest(base.TestCase):
    def test_check_constraints_reference_columns(self):
        for table in db.metadata.sorted_tables:
            checks = [
                c
                for c in table.constraints
                if isinstance(c, sa.CheckConstraint)
            ]
            if not checks:
                continue
            ddl = _mysql_ddl(table)
            self.assertNotIn(
                '"',
                ddl,
                f"{table.name}: a double quoted name in MySQL DDL is a "
                "string literal, use sa.column() in the constraint",
            )
            for check in checks:
                self.assertIn(f"CONSTRAINT {check.name} CHECK", ddl)

    def test_service_type_order_check(self):
        ddl = _mysql_ddl(db.metadata.tables["service_type"])
        self.assertIn("CHECK (`order` >= 0)", ddl)

    def test_datetimes_keep_microseconds(self):
        ddl = _mysql_ddl(db.metadata.tables["allocation_request"])
        self.assertIn("submit_date DATETIME(6) NOT NULL", ddl)
        self.assertIn("modified_time DATETIME(6) NOT NULL", ddl)
        ddl = _mysql_ddl(db.metadata.tables["usage_type"])
        self.assertIn("created_at DATETIME(6) NOT NULL", ddl)


class MigrationDDLTest(base.TestCase):
    def _offline_sql(self, path):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        buf = io.StringIO()
        context = migration.MigrationContext.configure(
            dialect_name="mysql",
            opts={"as_sql": True, "output_buffer": buf},
        )
        with operations.Operations.context(context):
            module.upgrade()
        return buf.getvalue()

    def test_migrations_render_check_constraints_for_mysql(self):
        for path in sorted(MIGRATIONS.glob("*.py")):
            sql = self._offline_sql(path)
            for line in sql.splitlines():
                if "CHECK" in line:
                    self.assertNotIn('"', line, f"{path.name}: {line}")

    def test_initial_schema_service_type_order_check(self):
        sql = self._offline_sql(MIGRATIONS / "40d50e265707_initial_schema.py")
        self.assertIn("CHECK (`order` >= 0)", sql)

    def test_datetime_microseconds_migration(self):
        sql = self._offline_sql(
            MIGRATIONS / "5b2e9c4a1f37_datetime_microseconds.py"
        )
        for table, column in (
            ("allocation_request", "submit_date"),
            ("allocation_request", "modified_time"),
            ("usage_type", "created_at"),
        ):
            self.assertIn(
                f"ALTER TABLE {table} CHANGE {column} {column} "
                "DATETIME(6) NOT NULL",
                sql,
            )

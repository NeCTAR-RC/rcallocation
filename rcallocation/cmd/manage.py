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

import click
from flask.cli import FlaskGroup

from rcallocation import app


@click.group(cls=FlaskGroup, create_app=app.create_app)
def cli():
    """Management script for the rcallocation service.

    Flask-Migrate adds the ``db`` command group (``db upgrade``,
    ``db migrate``, ``db current`` ...).
    """


@cli.command("import-legacy")
@click.option(
    "--source-connection",
    required=True,
    envvar="RCALLOCATION_LEGACY_SOURCE",
    help="SQLAlchemy URL of the nectar-dashboard database to copy from.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Report what would be copied without writing anything.",
)
@click.option("--batch-size", default=1000, show_default=True, type=int)
@click.option(
    "--allow-non-empty",
    is_flag=True,
    help="Copy even if the target database already holds rows.",
)
@click.option(
    "--no-schema-check",
    is_flag=True,
    help="Skip checking that the target schema is at the latest revision.",
)
def import_legacy(
    source_connection, dry_run, batch_size, allow_non_empty, no_schema_check
):
    """Copy the allocation tables from the old dashboard database."""
    from rcallocation.legacy import importer

    try:
        summary = importer.run(
            source_connection,
            dry_run=dry_run,
            batch_size=batch_size,
            allow_non_empty=allow_non_empty,
            check_schema=not no_schema_check,
        )
    except importer.ImportError_ as exc:
        raise click.ClickException(str(exc))
    click.echo(summary.format())

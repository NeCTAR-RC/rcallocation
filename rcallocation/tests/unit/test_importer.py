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

"""import-legacy against a SQLite copy of the Django schema."""

import datetime
import os
import tempfile

import sqlalchemy as sa

from rcallocation.extensions import db
from rcallocation.legacy import importer
from rcallocation import models
from rcallocation.tests.unit import base


LEGACY_DDL = """
CREATE TABLE rcallocation_site (id INTEGER PRIMARY KEY, name VARCHAR(32),
    display_name VARCHAR(64), enabled BOOL);
CREATE TABLE rcallocation_approver (id INTEGER PRIMARY KEY,
    username VARCHAR(254), display_name VARCHAR(64));
CREATE TABLE rcallocation_approver_sites (id INTEGER PRIMARY KEY,
    approver_id INTEGER, site_id INTEGER);
CREATE TABLE rcallocation_zone (name VARCHAR(32) PRIMARY KEY,
    display_name VARCHAR(64), enabled BOOL);
CREATE TABLE rcallocation_servicetype (catalog_name VARCHAR(32) PRIMARY KEY,
    name VARCHAR(64), description TEXT, notes TEXT, "order" INTEGER,
    experimental BOOL, location_specific BOOL);
CREATE TABLE rcallocation_servicetype_zones (id INTEGER PRIMARY KEY,
    servicetype_id VARCHAR(32), zone_id VARCHAR(32));
CREATE TABLE rcallocation_resource (id INTEGER PRIMARY KEY, name VARCHAR(64),
    service_type_id VARCHAR(32), quota_name VARCHAR(32), unit VARCHAR(32),
    requestable BOOL, help_text TEXT, resource_type VARCHAR(10),
    "default" INTEGER);
CREATE TABLE rcallocation_bundle (id INTEGER PRIMARY KEY, name VARCHAR(64),
    description VARCHAR(255), zone_id VARCHAR(32), "order" INTEGER,
    su_per_year INTEGER);
CREATE TABLE rcallocation_bundlequota (id INTEGER PRIMARY KEY,
    bundle_id INTEGER, resource_id INTEGER, quota INTEGER);
CREATE TABLE rcallocation_usagetype (id INTEGER PRIMARY KEY, name VARCHAR(40),
    enabled BOOL, created_at DATETIME);
CREATE TABLE rcallocation_ncrisfacility (id INTEGER PRIMARY KEY,
    name VARCHAR(200), short_name VARCHAR(200));
CREATE TABLE rcallocation_ardcsupport (id INTEGER PRIMARY KEY,
    name VARCHAR(200), short_name VARCHAR(200), project BOOL,
    project_id VARCHAR(20), enabled BOOL, rank INTEGER, explain BOOL);
CREATE TABLE rcallocation_organisation (id INTEGER PRIMARY KEY,
    ror_id VARCHAR(32), full_name VARCHAR(200), short_name VARCHAR(16),
    url VARCHAR(64), country VARCHAR(2), parent_id INTEGER, enabled BOOL,
    proposed_by VARCHAR(64), vetted_by_id INTEGER);
CREATE TABLE rcallocation_organisation_precedes (id INTEGER PRIMARY KEY,
    from_organisation_id INTEGER, to_organisation_id INTEGER);
CREATE TABLE rcallocation_allocationrequest (id INTEGER PRIMARY KEY,
    parent_request_id INTEGER, status VARCHAR(1), status_explanation TEXT,
    created_by VARCHAR(100), submit_date DATETIME, modified_time DATETIME,
    project_name VARCHAR(64), project_description VARCHAR(200),
    contact_email VARCHAR(254), start_date DATE, end_date DATE,
    estimated_project_duration INTEGER, convert_trial_project BOOL,
    approver_email VARCHAR(254), use_case TEXT, usage_patterns TEXT,
    geographic_requirements TEXT, project_id VARCHAR(36),
    estimated_number_users INTEGER, direct_access_user_estimate INTEGER,
    estimated_service_count INTEGER, estimated_service_active_users INTEGER,
    multiple_allocations_check BOOL, direct_access_user_past_year INTEGER,
    active_service_count INTEGER, service_active_users_past_year INTEGER,
    users_figure_type VARCHAR(10), has_sensitive_data VARCHAR(20),
    data_classification_level VARCHAR(10),
    institutional_data_review VARCHAR(10), field_of_research_1 VARCHAR(6),
    for_percentage_1 INTEGER, field_of_research_2 VARCHAR(6),
    for_percentage_2 INTEGER, field_of_research_3 VARCHAR(6),
    for_percentage_3 INTEGER, nectar_support VARCHAR(255),
    ardc_explanation VARCHAR(1024), ncris_support VARCHAR(255),
    ncris_explanation VARCHAR(1024), associated_site_id INTEGER,
    national BOOL, special_approval VARCHAR(1024), provisioned BOOL,
    notes TEXT, notifications BOOL, managed BOOL, bundle_id INTEGER,
    nectar_benefit_description TEXT, nectar_research_impact TEXT,
    legacy_leftover VARCHAR(10));
CREATE TABLE rcallocation_allocationrequest_usage_types (id INTEGER PRIMARY KEY,
    allocationrequest_id INTEGER, usagetype_id INTEGER);
CREATE TABLE rcallocation_allocationrequest_ncris_facilities (
    id INTEGER PRIMARY KEY, allocationrequest_id INTEGER,
    ncrisfacility_id INTEGER);
CREATE TABLE rcallocation_allocationrequest_ardc_support (
    id INTEGER PRIMARY KEY, allocationrequest_id INTEGER,
    ardcsupport_id INTEGER);
CREATE TABLE rcallocation_allocationrequest_supported_organisations (
    id INTEGER PRIMARY KEY, allocationrequest_id INTEGER,
    organisation_id INTEGER);
CREATE TABLE rcallocation_quotagroup (id INTEGER PRIMARY KEY,
    allocation_id INTEGER, zone_id VARCHAR(32), service_type_id VARCHAR(32));
CREATE TABLE rcallocation_quota (id INTEGER PRIMARY KEY, group_id INTEGER,
    resource_id INTEGER, requested_quota INTEGER, quota INTEGER);
CREATE TABLE rcallocation_chiefinvestigator (id INTEGER PRIMARY KEY,
    allocation_id INTEGER, title VARCHAR(60), given_name VARCHAR(200),
    surname VARCHAR(200), email VARCHAR(254), primary_organisation_id INTEGER,
    additional_researchers TEXT);
CREATE TABLE rcallocation_publication (id INTEGER PRIMARY KEY,
    output_type VARCHAR(2), publication VARCHAR(512), doi VARCHAR(256),
    crossref_metadata TEXT, allocation_id INTEGER);
CREATE TABLE rcallocation_grant (id INTEGER PRIMARY KEY,
    grant_type VARCHAR(128), grant_subtype VARCHAR(128),
    funding_body_scheme VARCHAR(255), grant_id VARCHAR(200),
    first_year_funded INTEGER, last_year_funded INTEGER,
    total_funding FLOAT, allocation_id INTEGER);
"""

ALLOCATION_DEFAULTS = dict(
    status='A',
    created_by='u1',
    submit_date=datetime.datetime(2023, 1, 1, 10, 0, 0),
    modified_time=datetime.datetime(2023, 6, 1, 10, 0, 0),
    project_description='Legacy project',
    contact_email='bob@example.com',
    estimated_project_duration=12,
    convert_trial_project=0,
    approver_email='',
    use_case='use case',
    usage_patterns='',
    geographic_requirements='',
    for_percentage_1=100,
    for_percentage_2=0,
    for_percentage_3=0,
    nectar_support='',
    ardc_explanation='',
    ncris_support='',
    ncris_explanation='',
    national=0,
    special_approval='',
    provisioned=1,
    notifications=1,
    managed=1,
    legacy_leftover='x',
)


class TestImporter(base.TestCase):
    def setUp(self):
        super().setUp()
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.unlink, self.path)
        self.url = f"sqlite:///{self.path}"
        engine = sa.create_engine(self.url)
        with engine.begin() as conn:
            for statement in LEGACY_DDL.strip().split(";"):
                if statement.strip():
                    conn.execute(sa.text(statement))
            self._populate(conn)
        engine.dispose()

    def _insert(self, conn, table, rows):
        columns = ", ".join(f'"{k}"' for k in rows[0].keys())
        params = ", ".join(f":{k}" for k in rows[0].keys())
        conn.execute(
            sa.text(f'INSERT INTO {table} ({columns}) VALUES ({params})'),
            rows,
        )

    def _populate(self, conn):
        self._insert(
            conn,
            'rcallocation_site',
            [
                dict(id=1, name='uom', display_name='Melbourne', enabled=1),
                dict(id=2, name='qcif', display_name='QCIF', enabled=1),
            ],
        )
        self._insert(
            conn,
            'rcallocation_approver',
            [
                dict(id=1, username='app@x.org', display_name='App'),
            ],
        )
        self._insert(
            conn,
            'rcallocation_approver_sites',
            [
                dict(id=7, approver_id=1, site_id=2),
            ],
        )
        self._insert(
            conn,
            'rcallocation_zone',
            [
                dict(name='nectar', display_name='Nectar', enabled=1),
                dict(name='melbourne', display_name='Melbourne', enabled=1),
            ],
        )
        self._insert(
            conn,
            'rcallocation_servicetype',
            [
                dict(
                    catalog_name='compute',
                    name='Compute',
                    description=None,
                    notes=None,
                    order=1,
                    experimental=0,
                    location_specific=0,
                ),
                dict(
                    catalog_name='volume',
                    name='Volume',
                    description='d',
                    notes=None,
                    order=2,
                    experimental=0,
                    location_specific=1,
                ),
                dict(
                    catalog_name='rating',
                    name='Rating',
                    description=None,
                    notes=None,
                    order=3,
                    experimental=0,
                    location_specific=0,
                ),
            ],
        )
        self._insert(
            conn,
            'rcallocation_servicetype_zones',
            [
                dict(id=1, servicetype_id='compute', zone_id='nectar'),
                dict(id=2, servicetype_id='volume', zone_id='melbourne'),
                dict(id=3, servicetype_id='rating', zone_id='nectar'),
            ],
        )
        self._insert(
            conn,
            'rcallocation_resource',
            [
                dict(
                    id=10,
                    name='Cores',
                    service_type_id='compute',
                    quota_name='cores',
                    unit='cores',
                    requestable=1,
                    help_text=None,
                    resource_type='integer',
                    default=None,
                ),
                dict(
                    id=11,
                    name='Gigabytes',
                    service_type_id='volume',
                    quota_name='gigabytes',
                    unit='GB',
                    requestable=1,
                    help_text=None,
                    resource_type='integer',
                    default=None,
                ),
                dict(
                    id=12,
                    name='Budget',
                    service_type_id='rating',
                    quota_name='budget',
                    unit='SU',
                    requestable=1,
                    help_text=None,
                    resource_type='integer',
                    default=None,
                ),
            ],
        )
        self._insert(
            conn,
            'rcallocation_bundle',
            [
                dict(
                    id=3,
                    name='gold',
                    description='Gold',
                    zone_id='nectar',
                    order=1,
                    su_per_year=16000,
                ),
            ],
        )
        self._insert(
            conn,
            'rcallocation_bundlequota',
            [
                dict(id=1, bundle_id=3, resource_id=10, quota=200),
            ],
        )
        self._insert(
            conn,
            'rcallocation_usagetype',
            [
                dict(
                    id=1,
                    name='Other',
                    enabled=1,
                    created_at=datetime.datetime(2022, 1, 1),
                ),
            ],
        )
        self._insert(
            conn,
            'rcallocation_ncrisfacility',
            [
                dict(id=1, name='Atlas of Living Australia', short_name='ALA'),
            ],
        )
        self._insert(
            conn,
            'rcallocation_ardcsupport',
            [
                dict(
                    id=1,
                    name='CVL long',
                    short_name='CVL',
                    project=1,
                    project_id='',
                    enabled=1,
                    rank=30,
                    explain=0,
                ),
            ],
        )
        self._insert(
            conn,
            'rcallocation_organisation',
            [
                dict(
                    id=1,
                    ror_id='https://ror.org/1',
                    full_name='Parent Uni',
                    short_name='PU',
                    url='',
                    country='AU',
                    parent_id=None,
                    enabled=1,
                    proposed_by='',
                    vetted_by_id=None,
                ),
                dict(
                    id=2,
                    ror_id='',
                    full_name='Child Institute',
                    short_name='CI',
                    url='https://ci.edu',
                    country='AU',
                    parent_id=1,
                    enabled=1,
                    proposed_by='someone',
                    vetted_by_id=1,
                ),
            ],
        )
        self._insert(
            conn,
            'rcallocation_organisation_precedes',
            [
                dict(id=1, from_organisation_id=2, to_organisation_id=1),
            ],
        )
        live = dict(
            ALLOCATION_DEFAULTS,
            id=100,
            parent_request_id=None,
            project_name='proj',
            project_id='pid',
            associated_site_id=1,
            bundle_id=3,
            start_date=datetime.date(2023, 1, 1),
            end_date=datetime.date(2024, 1, 1),
        )
        history = dict(
            ALLOCATION_DEFAULTS,
            id=101,
            parent_request_id=100,
            status='E',
            project_name='proj',
            project_id='pid',
            associated_site_id=None,
            bundle_id=None,
            start_date=None,
            end_date=None,
            modified_time=datetime.datetime(2023, 1, 1, 10),
            provisioned=0,
        )
        self._insert(conn, 'rcallocation_allocationrequest', [live, history])
        self._insert(
            conn,
            'rcallocation_allocationrequest_usage_types',
            [
                dict(id=1, allocationrequest_id=100, usagetype_id=1),
            ],
        )
        self._insert(
            conn,
            'rcallocation_allocationrequest_ncris_facilities',
            [dict(id=1, allocationrequest_id=100, ncrisfacility_id=1)],
        )
        self._insert(
            conn,
            'rcallocation_allocationrequest_ardc_support',
            [dict(id=1, allocationrequest_id=100, ardcsupport_id=1)],
        )
        self._insert(
            conn,
            'rcallocation_allocationrequest_supported_organisations',
            [
                dict(id=1, allocationrequest_id=100, organisation_id=2),
                dict(id=2, allocationrequest_id=101, organisation_id=2),
            ],
        )
        self._insert(
            conn,
            'rcallocation_quotagroup',
            [
                dict(
                    id=50,
                    allocation_id=100,
                    zone_id='melbourne',
                    service_type_id='volume',
                ),
                dict(
                    id=51,
                    allocation_id=101,
                    zone_id='melbourne',
                    service_type_id='volume',
                ),
            ],
        )
        self._insert(
            conn,
            'rcallocation_quota',
            [
                dict(
                    id=500,
                    group_id=50,
                    resource_id=11,
                    requested_quota=100,
                    quota=80,
                ),
                dict(
                    id=501,
                    group_id=51,
                    resource_id=11,
                    requested_quota=100,
                    quota=0,
                ),
            ],
        )
        self._insert(
            conn,
            'rcallocation_chiefinvestigator',
            [
                dict(
                    id=1,
                    allocation_id=100,
                    title='Dr',
                    given_name='A',
                    surname='B',
                    email='a@b.org',
                    primary_organisation_id=2,
                    additional_researchers='',
                ),
            ],
        )
        self._insert(
            conn,
            'rcallocation_publication',
            [
                dict(
                    id=1,
                    output_type='AJ',
                    publication='',
                    doi='10.1/x',
                    crossref_metadata='{}',
                    allocation_id=100,
                ),
            ],
        )
        self._insert(
            conn,
            'rcallocation_grant',
            [
                dict(
                    id=1,
                    grant_type='arc',
                    grant_subtype='arc-discovery',
                    funding_body_scheme='',
                    grant_id='g1',
                    first_year_funded=2020,
                    last_year_funded=2024,
                    total_funding=1000.0,
                    allocation_id=100,
                ),
            ],
        )

    def test_dry_run(self):
        summary = importer.run(self.url, dry_run=True, check_schema=False)
        self.assertTrue(summary.dry_run)
        self.assertEqual(2, summary.counts['rcallocation_allocationrequest'])
        self.assertEqual({}, summary.orphans)
        self.assertEqual({}, summary.copied)
        self.assertEqual(0, db.session.query(models.AllocationRequest).count())
        text = summary.format()
        self.assertIn("Dry run", text)
        self.assertIn("No dangling references", text)

    def test_import(self):
        summary = importer.run(self.url, check_schema=False)
        self.assertFalse(summary.dry_run)
        self.assertEqual(
            summary.counts['rcallocation_allocationrequest'],
            summary.copied['rcallocation_allocationrequest'],
        )
        self.assertEqual(
            {'legacy_leftover'},
            summary.ignored_columns['rcallocation_allocationrequest'],
        )
        self.assertEqual(
            ["quota totals: quota=80 requested_quota=200"], summary.checks
        )

        live = db.session.get(models.AllocationRequest, 100)
        history = db.session.get(models.AllocationRequest, 101)
        self.assertEqual(100, history.parent_request_id)
        self.assertEqual(datetime.datetime(2023, 6, 1, 10), live.modified_time)
        self.assertEqual('gold', live.bundle.name)
        self.assertEqual('uom', live.associated_site.name)
        self.assertEqual(['Other'], [u.name for u in live.usage_types])
        self.assertEqual(
            ['ALA'], [f.short_name for f in live.ncris_facilities]
        )
        self.assertEqual(['CVL'], [a.short_name for a in live.ardc_support])
        self.assertEqual(
            ['Child Institute'],
            [o.full_name for o in live.supported_organisations],
        )
        self.assertEqual(80, live.get_quota('volume.gigabytes'))
        self.assertEqual(1, len(history.all_quotas()))
        self.assertEqual('a@b.org', live.chief_investigator_email)
        self.assertEqual(
            'Child Institute',
            live.investigators[0].primary_organisation.full_name,
        )
        self.assertEqual(['10.1/x'], [p.doi for p in live.publications])
        self.assertEqual(['g1'], [g.grant_id for g in live.grants])

        child = db.session.get(models.Organisation, 2)
        self.assertEqual(1, child.parent_id)
        self.assertEqual(['Parent Uni'], [o.full_name for o in child.precedes])
        self.assertEqual('app@x.org', child.vetted_by.username)
        approver = db.session.get(models.Approver, 1)
        self.assertEqual(['qcif'], [s.name for s in approver.sites])
        compute = db.session.get(models.ServiceType, 'compute')
        self.assertEqual(['nectar'], [z.name for z in compute.zones])
        self.assertEqual(16000, live.su_budget)

    def test_refuses_non_empty_target(self):
        importer.run(self.url, check_schema=False)
        self.assertRaises(
            importer.ImportError_, importer.run, self.url, check_schema=False
        )

    def test_failure_rolls_back_everything(self):
        # A row the target's CHECK constraint rejects, in the fifth table
        # copied; the tables copied before it must not survive.
        engine = sa.create_engine(self.url)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    'UPDATE rcallocation_servicetype SET "order" = -1 '
                    "WHERE catalog_name = 'rating'"
                )
            )
        engine.dispose()
        self.assertRaises(
            sa.exc.IntegrityError,
            importer.run,
            self.url,
            check_schema=False,
        )
        self.assertEqual(0, db.session.query(models.Site).count())
        self.assertTrue(importer._target_empty())

    def test_missing_source_table(self):
        engine = sa.create_engine(self.url)
        with engine.begin() as conn:
            conn.execute(sa.text("DROP TABLE rcallocation_grant"))
        engine.dispose()
        with self.assertRaises(importer.ImportError_) as ctx:
            importer.run(self.url, dry_run=True, check_schema=False)
        self.assertIn("rcallocation_grant", str(ctx.exception))

    def test_orphans_reported(self):
        engine = sa.create_engine(self.url)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "UPDATE rcallocation_chiefinvestigator "
                    "SET primary_organisation_id = 999"
                )
            )
        engine.dispose()
        summary = importer.run(self.url, dry_run=True, check_schema=False)
        self.assertEqual(
            {'rcallocation_chiefinvestigator.primary_organisation_id': 1},
            summary.orphans,
        )
        self.assertIn("Dangling references", summary.format())

    def test_schema_check(self):
        # The test database was created with create_all, not alembic.
        self.assertRaises(importer.ImportError_, importer.run, self.url)

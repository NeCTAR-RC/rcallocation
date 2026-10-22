# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- Run all tests: `tox -e py314`
- Run a single test module: `tox -e py314 -- rcallocation.tests.unit.api.v1.test_allocations`
- Run with coverage: `tox -e cover` (90% minimum)
- Run lint checks: `tox -e pep8`
- Generate config sample: `tox -e genconfig`
- Generate policy sample: `tox -e genpolicy`
- Release notes: `reno new <slug>` (OpenStack convention); commits are conventional commits with `git commit -s`; changes go through gerrit (`.gitreview`), no local branches.

Always run tests before committing code.

## Project overview

`rcallocation` is the Nectar Research Cloud allocation system API: a standalone
Flask service (flask-smorest + marshmallow, Flask-SQLAlchemy + Flask-Migrate,
oslo.config, keystonemiddleware, oslo.policy) that replaced the Django REST
Framework API embedded in the `nectar-dashboard` Horizon plugin. The REST
contract under `/v1/` must stay compatible with `python-nectarallocationclient`:
DRF-style LimitOffset pagination envelopes, django-filter style query lookups
(`parent_request__isnull=True`), form-encoded or JSON request bodies, and
DRF-style error bodies (`{"detail": ...}` or `{"field": ["msg"]}`).

## Architecture

- `rcallocation/app.py` `create_app()`: oslo.config → Flask → flask-smorest `Api`
  → `/v1` blueprints → healthcheck, proxy and request-id middleware → keystone
  middleware (`auth_strategy = keystone|noauth|testing`).
- `rcallocation/common/`: `config.py` (oslo.config options, YAML mappings loader),
  `context.py` (RequestContext with `is_anonymous` and `user_name` for policy),
  `keystone.py` (KeystoneContext, SkippingAuthProtocol, NoAuthContext),
  `policies.py` (oslo.policy rules `rcallocation:<resource>:<action>`),
  `exceptions.py`.
- `rcallocation/api/v1/`: `base.py` (`Blueprint`, `Resource` MethodView with
  `authorize`, `paginate`, `filter`), `parsing.py` (JSON-or-form body parser),
  `pagination.py` (DRF LimitOffset port), `filtering.py` (django-filter emulation),
  `errors.py` (DRF-shaped error bodies), `schemas/`, `resources/`.
- `rcallocation/models/`: SQLAlchemy models. Allocations are versioned through a
  `parent_request` snapshot chain: the live row keeps its id, each change copies
  the whole graph into a history row pointing back at it.
- `rcallocation/manager.py`: business logic (state transitions, history copies,
  quota handling, nested writes). Views stay thin.
- `rcallocation/notification/`: stevedore drivers (`taynac`, `logging`, `noop`)
  and Jinja2 email templates.
- `rcallocation/legacy/importer.py`: `rcallocation-manage import-legacy`, copies
  the old `rcallocation_*` tables from the dashboard database.

## Policy roles

Project-scoped tokens: only `allocationadmin` and `allocationapprover` grant
elevated access, never plain `admin`. Approve and decline need
`allocationapprover`. System-scoped `admin` and `reader` are honoured.
Anonymous callers may read allocations, quotas and reference data.

## Testing patterns

- `rcallocation/tests/unit/base.py`: `TestCase` (in-memory SQLite) and
  `ApiTestCase` with `TestKeystoneWrapper` personas (`ROLES`, `USER_NAME`,
  `PROJECT_ID`, `SYSTEM_SCOPE`, `ANONYMOUS`) and `use_persona()`.
- `rcallocation/tests/unit/contract/`: drives the real
  `python-nectarallocationclient` against the Flask test client.

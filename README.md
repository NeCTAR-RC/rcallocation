# rcallocation

The Nectar Research Cloud allocation system API.

`rcallocation` is a standalone OpenStack-style service that holds allocation
requests, approvals, quotas and their history, and exposes them through a
keystone-authenticated REST API under `/v1/`. It replaces the Django REST
Framework API that used to be embedded in the `nectar-dashboard` Horizon plugin
and is consumed by `python-nectarallocationclient`, the dashboard and other
Nectar services.

## Running

```
rcallocation-manage db upgrade          # create or upgrade the schema
rcallocation-api                         # development server
gunicorn rcallocation.wsgi:application   # production
```

Configuration lives in `/etc/rcallocation/rcallocation.conf` (see
`tox -e genconfig` for a sample) and the site and zone mappings in
`/etc/rcallocation/mappings.yaml` (see `etc/rcallocation/mappings.yaml.sample`).
Policy defaults can be inspected with `tox -e genpolicy`.

## Development

```
tox -e py314          # unit and contract tests
tox -e pep8           # style checks (pre-commit)
tox -e cover          # coverage report, 90% minimum
```

API documentation is in `docs/api/`; the service also serves an OpenAPI
description at `/v1/openapi.json`.

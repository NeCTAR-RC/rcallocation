# Allocation actions

Allocation requests move through their states with `POST` actions on
`/allocations/<id>/`. Each action that changes a request first copies the
current record (and its quotas, investigators, grants and publications) into
a history record whose `parent_request` points at the live one, so the live
record keeps its id.

| Action | Who | From states | Result |
|---|---|---|---|
| `submit/` | the contact, a project member or admin | N, E, R, X, J | E (or X for amendments), acknowledgement email |
| `approve/` | approver | E, X | A |
| `decline/` | approver | E, X | R (or J for amendments), decline email |
| `amend/` | the contact, a project member or admin | A, R | X, acknowledgement email |
| `delete/` | admin | any live record | D |

Plain `PATCH /allocations/<id>/` still updates a pending request in place
without recording history, as the `openstack allocation set` command does.
A `PATCH` that only changes `notes` leaves `modified_time` untouched.

## Request bodies

`submit/`, `amend/` and `POST /allocations/` take the same fields as
`PATCH`, plus optional nested lists that replace the related records in the
same transaction:

```
{
  "use_case": "...",
  "quotas": [
    {"zone": "nectar", "resource": "compute.cores", "requested_quota": 8}
  ],
  "investigators": [
    {"id": 12, "title": "Dr", "given_name": "Ada", "surname": "Lovelace",
     "email": "ada@example.edu", "primary_organisation": "https://ror.org/..."}
  ],
  "grants": [...],
  "publications": [...],
  "ignore_warnings": true
}
```

Items with an `id` update that record, items without one are created and
records not listed are deleted. `quotas` is the full set of quota rows:
a value of zero removes a row, and on a bundle allocation only location
specific service types keep overrides. `resource` is a codename such as
`compute.cores` or a resource id.

`approve/` takes the fields an approver may set (`status_explanation`,
`associated_site`, `national`, `special_approval`, `bundle`,
`estimated_project_duration`, `start_date`, `end_date`, `notes`) and
`quotas` with `quota` values (the allocated amounts).

`decline/` takes `status_explanation` (alias `reason`).

## Warnings

With `"ignore_warnings": false` the approver sanity checks run over the
proposed values before anything is saved. If they produce warnings the
request is rejected with `409` and nothing changes:

```
{"warnings": [{"code": "CINDER_NOT_LOCAL", "message": "..."}]}
```

The default is `true`, so existing clients are unaffected.

### GET /allocations/<id>/checks/

Runs the checks over the stored record and returns

```
{"warnings": [{"code": ..., "message": ...}],
 "nags": [{"code": ..., "message": ...}]}
```

`warnings` are the approver checks (only populated for approvers and
admins asking with `?approving=true`), `nags` the reminders shown to users
renewing an allocation.

## GET /allocations/?include=approver_info

Admins and approvers can ask for `approval_urgency`, `expiry_state` and
`concerned_sites` on every live record in a listing, the same values
`GET /allocations/<id>/approver_info/` returns.

## GET /allocations/?mine=true

Restricts a listing to the caller's own view: requests they are the contact
for, the approved allocation of the project their token is scoped to, and
every allocation of the projects they hold the tenantmanager role on.

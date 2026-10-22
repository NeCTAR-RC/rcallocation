# Allocation API version history

## 1.3
Served by the standalone `rcallocation` service under `/v1/`.
* Added `POST /allocations/<id>/submit/` to edit and resubmit a request
  while recording history, see [actions](actions.md)
* Added `POST /allocations/<id>/decline/`
* `POST /allocations/<id>/approve/` and `/amend/` accept an optional body
  of changes applied in the same transaction
* Added `GET /allocations/<id>/checks/` returning approver warnings and
  renewal nags
* Added `GET /usage-types/`
* Write actions accept nested `quotas`, `investigators`, `grants` and
  `publications`
* Added `su_budget` and `parent_request` to the authenticated `Allocation`
  representation and `requested_quota` to each entry of `quotas`
* Added `mine=true` and `include=approver_info` to `GET /allocations/`
* Added `search`, `enabled`, `country__in`, `exclude_all`, `vetted` and
  `proposed_by` filters to `/organisations/`, `username` to `/approvers/`
  and a `vetted` field on organisations

## 1.2
* Added `bundle` field to `Allocation` object
* Added new API to manage [Bundles](bundles.md) at /bundles

## 1.1
* Added new API for [Organisations](organisations.md) at /organisations
* Removed /institutions API, this has been replaced with `Organisations`
* Added `supported_organisations` field to `Allocation` object
* Added `primary_organisation` to `ChiefInvestigator` object
* Removed `institution` field from `ChiefInvestigator` object

## 1.0
Initial release

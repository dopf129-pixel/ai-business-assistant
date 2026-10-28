# Q06 — Manual tariff profile persistence acceptance (2026-10-27)

## Scope

This checkpoint implements only the persistent repository contract for manually confirmed seller-price commission profiles. Telegram input and price-scenario wiring are deferred to Q07–Q08. No current Ozon point is extended into a hypothetical price range.

## Implementation

- `PlanningWorkspaceRepository` owns the additive schema-v3 migration and all CRUD transactions for `planning_tariff_profiles`, `planning_tariff_profile_revisions` and `planning_tariff_profile_idempotency`. The existing database is reused; no second DB or new dependency was introduced.
- Profiles are scoped by active owner/store and exact product/offer/SKU. FBO only, seller price in integer cents, RUB, manual owner confirmation, bounded inclusive bands and effective dates are allowlisted. Content revisions are append-only; mutable archive status uses a separate state revision.
- Create/update/archive use tenant-scoped idempotency records and CAS. Update cannot change identity. Limits bound payload bytes, profiles, revisions and list page size. Invalid or unavailable state fails closed.
- Saved plan payload schema/calculation v1/v2 are unchanged. New records share existing storage and backup/restore root.

## Verification

Environment: Windows, Python 3.12.10; existing isolated interpreter, no package installation; a new `%TEMP%` root was used for synthetic SQLite and pytest basetemp; `PYTHONPATH=app`, dotenv and credential environment disabled; no network or live API.

Command profile: six focused files — new tariff profile tests, planning repository regression suite, tariff resolver/source, scenario source and current-product economics source.

Result: **115 passed in 2.26s**. `py_compile` passed for the modified repository and test module. `git diff --check` passed. SHA-256 for all five tracked `data/*.json` files were unchanged in the isolated run. Synthetic trigger tests proved profile/revision/idempotency writes and the schema-v2→v3 migration roll back atomically on failure.

## Limitations / next stage

This checkpoint is not yet exposed in Telegram and does not itself calculate a target price. Q07 must bind the preview/confirm/edit/cancel draft ticket to current owner, store, SKU and revision; Q08 must freeze the selected tariff revision in a saved scenario. Overall PR still needs full pytest, cross-platform exact-head CI and independent review. No merge, deployment or real bot was performed.

# Period Profit Mapping Review Monitoring v1 — v154–v158

Date: 2026-08-29

Architecture Review Required: **Yes** — this batch adds a safety-critical long-lived monitoring/reopen lifecycle around mapping review closure.

## Goal

A review that was safely closed after replacement activation must not be treated as permanently valid. Catalog drift can appear later. The system therefore needs a read-only checkpoint, refresh, reopen decision, and handoff back into the existing human re-review workflow.

Workflow:

`v153 completion report → v154 closure checkpoint → v155 quality refresh → v156 still-closed evaluation / v157 reopened state → v158 existing human re-review candidate`

## v154 — closure checkpoint

A checkpoint can be created only from a fully closed v153 completion report with:

- exact scope/revision/mapping lineage;
- catalog available;
- freshness `FRESH`;
- no unresolved reasons;
- no remap, activation, Ozon mutation, profit adjustment, or execution permissions.

The checkpoint is read-only and records that future monitoring is required.

## v155 — monitoring refresh

The workflow reuses the existing `PeriodProfitMappingQualityService.report()` and requires the active revision and mapping to remain exactly the ones captured at closure.

Malformed drift evidence fails closed. No fuzzy matching, substring matching, semantic guessing, or automatic operation classification is added.

## v156 — still closed

If refreshed evidence remains catalog-available, drift-free, fresh, and `review_required=False`, the checkpoint remains closed.

This is descriptive only.

## v157 — reopen

Any of the following reopens review:

- catalog unavailable;
- missing mapped type IDs;
- renamed mapped operations;
- other catalog drift;
- freshness no longer `FRESH`;
- existing quality service requires review.

Reopen does not modify registry state and grants no save/activation/remap permission.

## v158 — handoff to existing re-review

A reopened state re-fetches current quality, active mapping, and current catalog, verifies exact lineage, and delegates to existing `build_mapping_rereview_candidate()`.

That existing candidate requires human confirmation. This batch does not create replacement mappings, does not authorize mappings, and does not activate anything automatically.

## Safety invariants

Unchanged:

- exact type-ID/name evidence only;
- no fuzzy or substring classification;
- no automatic remap;
- no automatic activation;
- no hidden registry write;
- no Ozon mutation;
- no profit adjustment or fee double counting;
- return mapping evidence still does not mean full returns economics;
- Product Decisions execution remains manual.

## Tests

`tests/test_period_profit_mapping_review_monitoring_batch_v154_v158.py`

Coverage includes closed-checkpoint eligibility, exact lineage binding, clean monitoring, drift reopening, handoff to the existing human re-review candidate, and malformed monitoring evidence fail-closed behavior.

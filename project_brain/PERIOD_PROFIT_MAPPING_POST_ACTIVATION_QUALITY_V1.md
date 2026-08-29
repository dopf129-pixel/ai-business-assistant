# Period Profit Mapping Post-Activation Quality v1 — v149–v153

Date: 2026-08-29

Architecture Review Required: **Yes** — safety-critical review closure workflow; batch spans contract, tests, and Project Brain documentation.

## Goal

After an explicitly reviewed replacement mapping is activated, the system must not assume that drift has been resolved merely because activation succeeded.

The activated revision must be re-checked through the existing read-only `PeriodProfitMappingQualityService` against the current real Ozon accrual catalog.

Workflow:

`v148 activation audit → v149 validation request → v150 refreshed quality → v151 closure evaluation → v152 unresolved fail-closed state → v153 completion report`

## v149 — exact post-activation validation request

The request accepts only a verified v148 activation audit produced after explicit human APPLY. It binds validation to exact:

- scope;
- active revision ID;
- mapping ID.

It keeps automatic remap, automatic activation, profit adjustment, and Ozon mutation disabled.

## v150 — refreshed quality evidence

`refresh_post_activation_quality()` calls the existing `PeriodProfitMappingQualityService.report()` after activation.

The scope quality entry must point to the exact revision and mapping from v149. If active lineage changed, the workflow fails closed.

The workflow reuses existing exact type-ID catalog drift evidence. It does not add fuzzy matching, substring classification, semantic guessing, or automatic remap.

## v151 — review closure

Review is closed only when all of the following are true:

- current catalog is available;
- no mapped type IDs are missing;
- no operation names have drifted;
- no catalog drift is reported;
- mapping freshness is `FRESH`;
- existing quality service no longer requires review.

Closure is descriptive/read-only and does not mutate registry state.

## v152 — unresolved fail-closed state

If evidence is incomplete or unsafe, review remains unresolved. Reasons are deterministic and may include:

- `CATALOG_UNAVAILABLE`;
- `MISSING_TYPE_IDS`;
- `RENAMED_OPERATIONS`;
- `CATALOG_DRIFT`;
- `FRESHNESS_NOT_FRESH`;
- `REVIEW_STILL_REQUIRED`.

An unresolved review never triggers remap, save, activation, Ozon mutation, or profit adjustment.

## v153 — completion report

The completion report binds v149, v150, and v151/v152 artifacts to the same exact scope/revision/mapping lineage.

It reports whether the replacement review lifecycle is closed or remains unresolved, plus current catalog availability, freshness, quality score, and unresolved reasons.

## Safety invariants

Unchanged:

- no fuzzy matching;
- no substring classification;
- no automatic operation semantics;
- no automatic remap;
- no automatic activation;
- no Ozon mutation;
- mapping evidence does not change profit;
- no fee double counting;
- return evidence still does not imply `returns_included=True`;
- Product Decisions execution remains manual.

## Tests

Targeted file:

`tests/test_period_profit_mapping_post_activation_quality_batch_v149_v153.py`

Coverage includes verified-audit requirement, exact lineage binding, successful clean closure, catalog outage, drift/stale unresolved state, completion report lineage, and tampered lineage rejection.

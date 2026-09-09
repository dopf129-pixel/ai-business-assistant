# Period Profit Return COGS downstream integrity gates

Production basis: `6e08187ae7fde85f0985fd0082876c4c0f1f2574`.

## Decision

The Return COGS pipeline already had canonical accounting, recognition, authorization, exact-once commit, and final-application gates. This package adds defense-in-depth integrity wrappers around the two most downstream boundaries so that internally inconsistent evidence cannot be promoted merely because an earlier service emitted a true confirmation boolean.

The new wrappers do not create business facts, write repositories, mutate Ozon, or infer monetary values. They only reject inconsistent evidence before commit readiness is exposed and before committed Return COGS is reflected in seller-facing Period Profit.

## Commit integrity gate

`PeriodProfitReturnCogsCommitIntegrityService` wraps the existing `PeriodProfitReturnCogsApplicationCommitReadinessService`.

It never upgrades a blocked result. It can only preserve the underlying readiness/commit result or downgrade it to `PERIOD_PROFIT_RETURN_COGS_APPLICATION_COMMIT_BLOCKED` when downstream evidence is internally inconsistent.

The gate rechecks:

- canonical `PERIOD_PROFIT_RETURN_COGS_APPLICATION_ELIGIBILITY_READY` when the eligibility confirmation boolean is true;
- exact candidate identity coverage by recognition records;
- exact candidate identity coverage by authorization records;
- unique positive recognition history IDs;
- canonical recognition record status, explicit recognition confirmation, and `COGS_RECOVERY_RECOGNIZED` state;
- finite non-negative recognized amount, RUB currency, and recovery accounting date;
- unique authorization coverage by recognition history ID;
- canonical authorization record status, explicit authorization confirmation, and `PROFIT_APPLICATION_AUTHORIZED` state;
- `application_already_applied=False` before commit;
- finite non-negative authorized amount, RUB currency, and recovery accounting date;
- explicit monetary authority treatment `EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL`;
- `monetary_authority_non_overlap_confirmed is True`;
- `compensation_non_overlap_confirmed is True`;
- exact recognition ↔ authorization identity/date/amount reconciliation;
- durable commit row `error is False` and explicit commit confirmation when the underlying service reports committed;
- exact recognition/authorization version binding for durable commit rows;
- exact identity/date/currency coverage for durable commit records;
- complete durable-commit coverage of all recognition versions.

A non-finite amount such as `NaN` or `Infinity` is invalid evidence, never a number that can participate in readiness.

The wrapper exposes `return_cogs_profit_application_integrity_confirmed` only for an internally coherent downstream evidence set.

## Final application integrity gate

`PeriodProfitReturnCogsFinalIntegrityService` wraps the existing `PeriodProfitReturnCogsFinalApplicationService`.

When commit is not confirmed, it delegates to the existing non-applied path and does not manufacture a blocker. When commit is confirmed, it performs a separate pre-application integrity pass before the existing final calculation is allowed to run.

The final integrity gate requires exact identity-set equality between:

1. `candidate_records`;
2. accounting recognition records;
3. profit-application authorization records;
4. durable commit records.

This closes the aggregate-subset gap: a complete recognition/authorization/commit chain for only a subset of candidates cannot be accepted merely because its aggregate committed total matches the subset's eligible amount.

For every candidate identity, the final integrity gate also rechecks:

- authorization row `error is False`;
- monetary authority exclusion from account net accrual;
- monetary-authority non-overlap confirmation;
- compensation non-overlap confirmation;
- durable commit row `error is False` and explicit commit confirmation;
- finite non-negative recognized, authorized, and committed amounts;
- exact amount equality across recognition → authorization → commit;
- RUB currency across all three records;
- exact recovery accounting date equality across all three records.

Only after this wrapper passes does the existing final-application service perform its recognition/authorization/commit history binding, aggregate committed-vs-eligible comparison, tax-policy recomputation, and seller-facing Period Profit recomputation.

A successful final result additionally exposes:

- `return_cogs_final_candidate_coverage_confirmed=True`;
- `return_cogs_final_monetary_authority_reconfirmed=True`.

These flags are observability only. They are not authorization to commit or mutate anything.

## Production wiring

`period_profit_factory.py` now wires the pipeline as:

`... → application eligibility → commit readiness → commit integrity → PeriodProfitQueryService → final application → final integrity → PeriodProfitFinalApplicationQueryService`.

The underlying existing services remain responsible for their original contracts. The integrity wrappers are deliberately separate so that financial arithmetic is not mixed with evidence-consistency validation.

## Failure semantics

The package is fail-closed for, among other cases:

- true eligibility boolean with non-ready canonical eligibility status;
- missing or duplicate candidate identity;
- candidate set larger than recognition or authorization coverage;
- malformed recognition or authorization row;
- non-ready recognition/authorization record status;
- missing explicit recognition/authorization confirmation;
- stale or already-applied authorization record;
- missing monetary-authority exclusion;
- missing monetary-authority or compensation non-overlap confirmation;
- recognition/authorization identity, date, or amount mismatch;
- durable commit row whose `error` field is unknown rather than explicitly false;
- missing durable commit coverage;
- NaN/Infinity monetary values;
- final candidate set larger than the exact recognition/authorization/commit set;
- final monetary-authority or compensation-overlap evidence disappearing after commit.

Unknown remains unknown. It is not normalized to zero or to a successful boolean.

## Safety invariants

- Ozon remains READ-ONLY.
- `ReturnedToOzon` remains candidate evidence only; it is not proof of `SALEABLE_RESTORED`.
- `unknown != zero`.
- No Return COGS amount is derived from `quantity × guessed unit cost`.
- Missing accounting/business facts are not auto-filled.
- Recognition does not imply authorization.
- Authorization does not imply commit.
- Commit readiness does not imply durable commit.
- Durable commit does not bypass candidate-set or monetary-authority reconciliation at final application.
- No new seller-facing accounting write path is introduced.
- Seller-facing Period Profit remains `read_only=True`, `executed=False`.

## Regression coverage

Regression tests prove that:

- a complete canonical ready chain remains ready through commit integrity;
- a true eligibility boolean paired with blocked canonical eligibility status is downgraded to commit-blocked;
- non-finite authorization amounts are rejected;
- unknown monetary-authority non-overlap remains unconfirmed;
- recognition/authorization coverage of only a subset of candidates is rejected;
- durable commit rows without explicit `error=False` are rejected;
- final application accepts a complete exact candidate-to-commit chain;
- final application rejects a candidate subset even when the downstream aggregate chain matches itself;
- final application rechecks compensation non-overlap;
- final application rejects non-finite committed amounts;
- final application rejects a commit row whose error state is unknown;
- factory contract tests prove both integrity wrappers are wired in production.

The first feature-head run for this package failed only because the legacy factory contract test still asserted direct raw-service wiring. The test was updated to assert the new wrapper topology; the production integrity checks themselves were not weakened.

## SHA-bound verification evidence

Code package:

- feature head `80f697bfb853175fd0ea45d7f145298c78dae140` — Verify #1733 passed with compile, deterministic schema, full test suite, SHA-bound report, and artifact upload; artifact `verification-80f697bfb853175fd0ea45d7f145298c78dae140`, digest `sha256:86fb9a5530b0a72fcd7cfd803b126201d32bd31d2e6516fb1f0242bbded5f3fe`;
- PR #491 synthetic merge `bfdf3eb0cb430f5303f44cd48667f73261764d87` — Verify #1734 passed; artifact `verification-bfdf3eb0cb430f5303f44cd48667f73261764d87`, digest `sha256:29dc3f9183c50035e097b7a54e4ed4c178db8f5d345014fb27768ee483ae093f`;
- squash production main `6e08187ae7fde85f0985fd0082876c4c0f1f2574` — Verify #1735 passed; artifact `verification-6e08187ae7fde85f0985fd0082876c4c0f1f2574`, digest `sha256:fde356adf84ca4cbb80b1f74d683ee8aadc310cec545259e689a47c9c8f8bd25`.

Verification evidence is SHA-bound and must never be transferred between revisions.

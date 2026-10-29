# Decision 065 — immutable owner decisions for price experiments

Date: 2026-10-29
Topic: explain experiment outcomes and preserve the owner's chosen next step.

## Decision

- Derive recommendations from the immutable, validated W28 result; do not introduce a second calculator or source read.
- Rank only the newest result revision for each evaluated candidate. A set is rankable only when candidates share the exact baseline collection/readiness revision, frozen cost/tax basis, threshold and shared snapshot references. Keep all exact ties; omit a maximum when evidence groups differ.
- Persist owner choices in `planning_price_experiment_decisions`, an additive tenant-scoped append-only table in the existing Planning Workspace. Each row binds to the exact latest candidate result phase/revision and current experiment state revision. Use a strict schema allowlist, content hash, SQLite immediate transaction, idempotency, CAS, maximum 100 decisions per experiment, and immutable update/delete triggers.
- Supported choices: `KEEP_BASELINE_PRICE`, `SELECT_EVALUATED_CANDIDATE`, `CONTINUE_TEST`, `STOP_WITHOUT_PRICE_CHANGE`. Selecting a candidate requires the latest candidate comparison to be evaluated. Final choices may complete a candidate-review experiment only while the bound result remains current; `CONTINUE_TEST` leaves it in review.
- No decision action sends an Ozon API request, changes a seller price, or stores free-form owner text.

## Reason

Recommendations must remain bounded to evidence the experiment actually measured, and the owner's choice must remain auditable without overwriting prior choices or making an external price change. A separate append-only record preserves the W28 calculation snapshot and the existing tenant repository as the only persistence authority.

## Status

Implemented in W29 with Planning Workspace database migration v11→v12. Linked W26–W29 profile: 98 passed; see `UNIT_ECONOMICS_W29_RECOMMENDATION_DECISIONS_2026-10-29.md`.

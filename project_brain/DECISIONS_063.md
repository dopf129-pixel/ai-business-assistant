# Decision 063 — bounded rounding-aware minimum-price search

Date: 2026-10-28
Topic: preserve minimum-price semantics for rounded tariff-aware targets.

## Decision

- Do not assume that a canonical profit/target predicate is monotonic at each cent. Fee components and taxes are rounded, so the predicate can briefly reach the target, fall below it, and reach it again.
- For frozen fixed-commission tariff segments, compute a conservative upper bound for the continuous target gap. Prune only segments proven unable to reach the target within the canonical rounding envelope.
- Search remaining intervals left-first and use the canonical forward calculator to verify candidate cents. Verify representative points against the bound before relying on it.
- Unsupported formulae, an inconsistent bound, invalid forward data, or exhausted evaluation budgets must fail closed; do not claim an unproven minimum.
- Every batch solver call, including local row edits and multi-row target/advertising recalculations, receives its per-SKU and remaining shared forward-calculation budget before calculation starts. Exhaustion is surfaced as a bounded partial result; it is not treated as an ordinary target miss.

## Reason

A binary search can skip an earlier qualifying cent when rounded commission, advertising, tax or profit temporarily toggles the target predicate. Returning such a later value as the minimum would be incorrect. Bounded left-first search keeps the existing canonical calculator authoritative while keeping worst-case work capped.

## Status

Implemented in `UnitPriceTargetPlanningService` and `UnitPriceBatchPlanService`. Regressions cover the previously failing cent boundary, unsupported/non-monotonic forward behavior, evaluation cap and shared batch cap. R8 review follow-up permits an explicit target change to retry snapshot-backed rows that exhausted a prior solver search; missing/stale sources and unsupported schemes remain excluded, and all retries still receive the remaining bounded budget. The linked R8 profile passed (165 tests); full pytest and exact-head Verify are pending. Prior R6–R7 results (164 linked tests, 3,996 full-suite tests on `b2f01fb3`, Verify `40664676434` on `dbd87c7d`) apply to their earlier code head. See `UNIT_PRICE_REVIEW_HANDOFF_Q35_2026-10-27.md` for current status.

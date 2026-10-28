# Decision 063 — bounded rounding-aware minimum-price search

Date: 2026-10-28
Topic: preserve minimum-price semantics for rounded tariff-aware targets.

## Decision

- Do not assume that a canonical profit/target predicate is monotonic at each cent. Fee components and taxes are rounded, so the predicate can briefly reach the target, fall below it, and reach it again.
- For frozen fixed-commission tariff segments, compute a conservative upper bound for the continuous target gap. Prune only segments proven unable to reach the target within the canonical rounding envelope.
- Search remaining intervals left-first and use the canonical forward calculator to verify candidate cents. Verify representative points against the bound before relying on it.
- Unsupported formulae, an inconsistent bound, invalid forward data, or exhausted evaluation budgets must fail closed; do not claim an unproven minimum.
- A multi-SKU batch passes its remaining shared forward-calculation budget into each solver call before calculation starts.

## Reason

A binary search can skip an earlier qualifying cent when rounded commission, advertising, tax or profit temporarily toggles the target predicate. Returning such a later value as the minimum would be incorrect. Bounded left-first search keeps the existing canonical calculator authoritative while keeping worst-case work capped.

## Status

Implemented in `UnitPriceTargetPlanningService` and `UnitPriceBatchPlanService`. Regressions cover the previously failing cent boundary, unsupported/non-monotonic forward behavior, evaluation cap and shared batch cap. The focused linked profile passed (149 tests), isolated full suite passed (3,990 tests), and exact-head Verify `40654624761` passed on `40a23315`. See `UNIT_PRICE_REVIEW_HANDOFF_Q35_2026-10-27.md` for current status.

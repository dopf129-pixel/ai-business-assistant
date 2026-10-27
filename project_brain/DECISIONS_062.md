# Decision 062 — FBO observed buyout estimate for unit-price modeling

Date: 2026-10-27
Topic: derive a SKU-scoped, noncanonical buyout estimate from bounded Seller API evidence.

## Decision

- Derive an observed window rate from exact-SKU FBO posting and Returns evidence as `delivered_units / (delivered_units + confirmed_customer_non_buyout_units) * 100`. Keep the sample count and delivered/returned unit counts visible.
- A window is eligible only when the FBO and Returns selections are complete, pagination is complete, each matched posting has a terminal delivered/cancelled status, unit totals reconcile, cancellations are classifiable, and no ambiguous cancellation remains. Missing or partial evidence remains unavailable; never infer successful units from Analytics ordered units or source row counts.
- Use delivered units as the model denominator only when the strict source gate above passes. Keep Performance report-date CPC and the FBO posting/return-change cohort as distinct time bases; allow the explicitly labeled model with warnings, but do not call it canonical per-sale profit, official Ozon Analytics buyout, or causal evidence.
- Show units returned in the selected window separately. Do not subtract return costs from modelled profit per unit in this feature. Clearly disclose that this omission makes the figure an incomplete planning model and that later status changes may change the cohort.
- The estimate is computed from a user-requested, bounded, read-only collection. Do not add a scheduler or Ozon mutation. Persist only allowlisted aggregates/source metadata; never persist raw posting IDs, return IDs, product names or credentials.
- Candidate comparison is allowed only under the existing identity/source/assumption compatibility gates; outcomes stay immutable and model-labeled.

## Reason

The owner chose to calculate SKU buyout percentage instead of manually entering successful sales. FBO posting and Returns facts provide a non-paid, SKU-scoped input, but their status-window semantics differ from Performance report dates and do not establish final accounting profit. An explicit estimate with a strict completeness gate and visible return-cost limitation is useful for planning without disguising uncertain source facts as an Ozon KPI or store result.

## Status

Implemented in Q30 with synthetic public-handler acceptance. No live account/API result is claimed. Q31 linked regressions passed (1,374 tests across 175 modules; bounded checks 3 passed). Full repository pytest and exact-head CI are pending in Q33.

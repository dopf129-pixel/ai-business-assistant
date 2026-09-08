# Period Profit effective-dated product cost

Production basis: `151e945e7388094607879d16427330d9ab89d7b9`.

## Decision

Period Profit must not treat the current `product_costs` value as an eternal historical fact once seller-confirmed cost history exists.

`product_cost_history` is the seller-confirmed effective-date timeline. A row is effective from `effective_from` until a later confirmed version for the same product identity becomes effective.

For reconciled physical sales, COGS is calculated per sale accrual-date bucket:

`product_cost = sum(physical_quantity_on_date * confirmed_cost_effective_on_date)`

This keeps prior Period Profit stable when a future batch has a different себестоимость.

## Compatibility and fail-closed behavior

- If seller-confirmed history exists and an applicable version is available for the sale accrual date, use it.
- If a history timeline exists but there is no version effective yet for a requested earlier date, fail closed. `unknown != zero` and today's cost is not backfilled into that period.
- If no history timeline exists at all, the unique current `product_costs` row remains a compatibility fallback. This preserves existing installations until seller-confirmed history is seeded.
- Once history is seeded, changing only the current cost does not rewrite past or future Period Profit. A new seller-confirmed cost version must be recorded with the date from which it applies.

## Scope

This is effective-date costing, not FIFO/lot allocation. If multiple purchase batches with different costs overlap in inventory, the current evidence model cannot prove which lot a specific Ozon sale consumed. Do not describe it as exact lot attribution without additional inventory lineage evidence.

Ozon remains READ-ONLY. The change affects only local cost evidence and Period Profit calculation.

## Reconciliation invariants retained

- Ozon account-level finance remains the money authority.
- Physical sale quantity remains reconciled by exact posting + SKU, including re-accrual deduplication.
- Signed Ozon finance amounts are not changed by cost versioning.
- Return COGS recognition/authorization/commit rules are unchanged.
- Seller-facing Period Profit remains read-only and non-executing.

## Regression coverage

`app/tests/test_period_profit_effective_cost_timeline.py` covers:

- preservation of an old 21 RUB cost after a later confirmed cost version becomes effective;
- fail-closed behavior before the first confirmed historical version;
- legacy current-cost compatibility when no history exists;
- physical COGS split across sale accrual dates with different effective costs.

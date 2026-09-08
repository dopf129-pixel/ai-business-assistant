# Period Profit bounded historical product cost

Production basis: `bd05122aef83e7d734e04ebdd8042a5e6d6c21ff`.

## Decision

Period Profit COGS requires seller-confirmed historical cost evidence whose validity is explicitly bounded.

`product_cost_history` stores:

- `effective_from` — first confirmed date;
- `effective_through` — last confirmed date for that evidence row;
- seller-confirmed cost, currency, identity and source.

For Period Profit, a history row is usable only when the finance sale-accrual date is inside the inclusive interval:

`effective_from <= accrual_date <= effective_through`

A missing `effective_through` is not interpreted as infinity. Open-ended historical rows remain storable for compatibility, but they are insufficient evidence for Period Profit and fail closed.

## Unknown is not current cost

The mutable `product_costs` row describes current product economics. It is not historical evidence for an earlier Period Profit period.

Therefore Period Profit does not use either of the former compatibility paths:

- `LEGACY_CURRENT_COST_NO_HISTORY`;
- `LEGACY_SERVICE_COMPATIBILITY`.

If bounded historical evidence is missing, ambiguous, outside its confirmed interval or invalid, COGS is unknown and Period Profit fails closed. `unknown != zero`, and unknown also does not mean today's cost.

## Re-accrual semantics

Ozon finance can expose multiple positive accrual events for one physical `(posting_number, sku)`.

Physical quantity is still counted exactly once using the established authority chain:

1. realization;
2. FBO posting list;
3. exact FBO/FBS posting detail;
4. fail closed.

The finance `accrual_date` is a finance-period date. The current evidence model does not prove that it is the physical shipment or delivery date.

For one re-accrued physical posting, all observed positive accrual dates must resolve to the same bounded seller-confirmed cost version. If any date is unknown, or the dates cross different cost versions, Period Profit fails closed instead of selecting whichever accrual event happened to be encountered first.

Distinct physical postings may resolve to different bounded cost versions within one requested period. Their COGS is summed after quantity reconciliation.

## Scope

This is bounded effective-date evidence, not FIFO or lot allocation. It does not claim which inventory batch a specific Ozon sale consumed when batches overlap.

No Ozon mutation is introduced. Ozon remains READ-ONLY.

The following invariants are unchanged:

- account-level Ozon finance remains the money authority;
- signed finance amounts are not rewritten by cost evidence;
- return COGS still requires no-double-counting, recognition, authorization and commit before inclusion;
- seller-facing Period Profit remains read-only and non-executing.

## Storage compatibility

`ProductCostService.create_table()` migrates existing local SQLite databases by adding nullable `effective_through` when the column is absent.

Existing history rows are not silently assigned an invented end date. They therefore remain unbounded until explicit seller evidence supplies a valid upper boundary. Period Profit will not use those open-ended rows as confirmed historical COGS.

`record_historical_cost(..., effective_through=...)` rejects an invalid or reversed interval.

## Regression coverage

`app/tests/test_period_profit_effective_cost_timeline.py` covers:

- bounded historical cost inside its confirmed interval;
- separate later bounded versions;
- fail-closed behavior before and after confirmed coverage;
- open-ended history rejected by Period Profit;
- current cost without history rejected by Period Profit;
- reversed history interval rejected;
- distinct physical sales using different bounded versions;
- repeated positive accrual events within one cost version counting physical quantity once;
- re-accrual crossing cost versions failing closed;
- missing effective-cost resolver failing closed.

Existing re-accrual quantity regression remains authoritative for the invariant that repeated positive finance events do not multiply physical quantity.

## SHA-bound verification evidence

Production change lifecycle:

- feature head `9aa35b8e8b3c0a423daa686832e73f12c2a23b5f` — full Verify passed;
- actual PR #461 synthetic merge `61173a551f66989c37468ecbf8a79106dfe54bbb` — full Verify passed; artifact `verification-61173a551f66989c37468ecbf8a79106dfe54bbb`;
- squash production main `bd05122aef83e7d734e04ebdd8042a5e6d6c21ff` — full Verify passed.

Verification evidence is SHA-bound and is never transferred between revisions.

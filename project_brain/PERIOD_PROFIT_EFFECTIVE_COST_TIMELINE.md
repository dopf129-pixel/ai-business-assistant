# Period Profit seller-confirmed product cost timeline

Production basis: `d74856ca669e695bb8feaed0f03192e275c6998c`.

## Decision

Period Profit COGS uses explicit seller-confirmed cost evidence. Two evidence forms are intentionally different:

1. bounded historical evidence for a closed period;
2. an explicit operational cost switch entered by the seller for future calculations.

Mutable `product_costs` values are not historical Period Profit authority.

## Bounded historical evidence

`product_cost_history` stores seller-confirmed historical evidence with:

- `effective_from` — first confirmed date;
- `effective_through` — last confirmed date;
- cost, currency, product identity and source.

A bounded history row is usable only when the finance sale-accrual date is inside the inclusive interval:

`effective_from <= accrual_date <= effective_through`

A missing `effective_through` is not interpreted as infinity. Open-ended historical rows remain insufficient evidence for Period Profit and fail closed.

## Seller operational cost switch

Telegram exposes a `Себестоимость` flow:

1. seller opens the cost menu;
2. the menu displays the seller-facing article (`offer_id`, for example `hook-2`), while the callback keeps the exact internal SKU;
3. seller selects the article and the bot confirms both article and SKU;
4. seller enters the new unit cost in RUB;
5. the bot records an append-only seller-confirmed operational switch in local SQLite.

The seller-facing article is presentation only. Cost authority remains attached to the exact product identity including SKU, so changing display text does not change Period Profit matching semantics.

Operational switches are stored in `product_cost_switch_history`. A later seller switch supersedes an earlier switch only from the later switch's effective date. Earlier Period Profit dates continue to resolve using the evidence that was effective then.

The mutable `product_costs` row is updated at the same time for current-economics compatibility, but Period Profit does not use that mutable row as historical authority.

Ozon is not changed by this flow. Product selection reads the locally cached catalog and all Ozon integration remains READ-ONLY.

## Activation date

Current Period Profit finance evidence is date-granular: it proves `accrual_date`, not an intra-day sale timestamp.

Therefore a seller cost entered during a calendar day becomes effective on the next calendar date as seen by the bot runtime. This prevents sales/accruals already attributed to the confirmation day from being re-costed retroactively.

The bot reports the exact activation date after saving the cost.

A literal intra-day cost boundary must not be inferred without finer-grained sale-time evidence.

## Resolution order

For a requested accrual date:

1. if an explicit operational switch is effective, the latest applicable seller switch is authoritative;
2. otherwise Period Profit may use bounded historical evidence covering that date;
3. otherwise COGS is unknown and Period Profit fails closed.

There is no current-cost fallback. `unknown != zero` and unknown does not mean today's mutable cost.

## Re-accrual semantics

Ozon finance can expose multiple positive accrual events for one physical `(posting_number, sku)`.

Physical quantity is still counted exactly once using the established authority chain:

1. realization;
2. FBO posting list;
3. exact FBO/FBS posting detail;
4. fail closed.

The finance `accrual_date` is a finance-period date. The current evidence model does not prove that it is the physical shipment or delivery timestamp.

For one re-accrued physical posting, all observed positive accrual dates must resolve to the same seller-confirmed cost version. A version can be either one bounded historical row or one operational switch. If any date is unknown, or the accrual dates cross different versions, Period Profit fails closed instead of choosing one event opportunistically.

Repeated finance accrual does not multiply physical quantity or COGS.

## Scope and invariants

This is explicit effective-date evidence, not FIFO or lot allocation. It does not claim which physical inventory batch a sale consumed when batches overlap.

The following invariants remain unchanged:

- Ozon remains READ-ONLY;
- account-level Ozon finance remains the money authority;
- signed finance amounts are not rewritten by cost evidence;
- return COGS still requires no-double-counting, recognition, authorization and commit before inclusion;
- seller-facing Period Profit remains read-only and non-executing;
- missing or ambiguous COGS evidence fails closed.

## Storage behavior

`ProductCostService.create_table()` maintains `product_cost_history` and migrates older databases with nullable `effective_through` when needed.

`PeriodProfitEffectiveCostService` creates `product_cost_switch_history` on initialization. No manual Ozon-side migration exists or is required.

`record_historical_cost(..., effective_through=...)` rejects invalid or reversed bounded intervals.

`record_cost_switch(...)` appends a seller-confirmed operational switch and updates the mutable current-cost row in the same local SQLite transaction. Duplicate `product_id + effective_from` switch versions fail closed rather than silently overwrite evidence.

## Regression coverage

Bounded-history tests cover:

- cost inside a confirmed interval;
- separate bounded versions;
- before/after coverage fail closed;
- open-ended history rejected;
- current cost without evidence rejected;
- reversed interval rejected;
- different physical sales using different versions;
- re-accrual inside one version counting quantity once;
- re-accrual crossing versions failing closed;
- missing effective-cost resolver failing closed.

Seller-switch tests additionally cover:

- switch overriding bounded history only from the switch date;
- later switch superseding an earlier switch without rewriting past dates;
- Telegram numeric input creating a switch for the next calendar date;
- invalid Telegram input performing no write;
- re-accrual crossing an operational switch failing closed;
- re-accrual entirely inside one operational switch counting one physical quantity and one COGS amount;
- seller article (`offer_id`) displayed in the menu while callback preserves the exact SKU;
- selection confirmation showing article and SKU without changing internal product identity.

## SHA-bound verification evidence

Bounded-history production lifecycle remains recorded on its original SHAs.

Telegram seller-cost production lifecycle:

- failed feature candidate `40371cb43c36d5a05fdc6ee0495487f91c9a34fa` — Verify #1582 failed with 2382 passed / 2 failed; this SHA remains failed evidence;
- corrected feature head `6a60905dbb56e88a2662dc316303031e75fea2b6` — full Verify #1584 passed, 2384 passed / 0 failed; artifact `verification-6a60905dbb56e88a2662dc316303031e75fea2b6`;
- actual PR #463 synthetic merge `1a7fcc47c5c8a1dafee3dda05c90ca9998f15152` — full Verify #1585 passed; artifact `verification-1a7fcc47c5c8a1dafee3dda05c90ca9998f15152`;
- squash production main `40c97fcbf8a31c751f9bd527bb00d6fbba16aa94` — full Verify #1586 passed; artifact `verification-40c97fcbf8a31c751f9bd527bb00d6fbba16aa94`.

Seller-facing article display lifecycle:

- feature head `a8e0696c7864e031aa04ca906efd6589d1c5737f` — full Verify #1593 passed;
- actual PR #465 synthetic merge `544c1b3cef1545a1e02310ccc66e35779ca9737f` — full Verify #1594 passed;
- squash production main `d74856ca669e695bb8feaed0f03192e275c6998c` — full Verify #1595 passed.

Verification evidence is SHA-bound and is never transferred between revisions.

# Period Profit open-period sale quantity reconciliation — 2026-09-07

## Scope

Runtime request reported by the seller:

```text
прибыль за период 03.05.2026–07.09.2026
```

Observed seller-facing response before the correction:

```text
Данные о количестве проданных товаров недоступны
```

Ozon remains strictly READ-ONLY. This package does not change prices, advertising, stock, product cards, supplies, or any other Ozon business state.

## Exact failure source

The seller-facing message is emitted by `PeriodProfitSaleQuantitySummaryService._quantity_error()` with status `PERIOD_PROFIT_SALE_QUANTITY_UNAVAILABLE`.

The service uses account-level finance as the monetary authority, but finance accrual-by-day does not expose authoritative product quantity. Standard-sale COGS therefore reconciles quantity separately by exact `(posting_number, SKU)`.

Before this correction the quantity source order was:

1. monthly `/v1/finance/realization/posting`;
2. for every missing exact `(posting_number, SKU)`, a separate `/v2/posting/fbo/get` or `/v3/posting/fbs/get` request;
3. fail closed if one exact quantity remained unresolved.

That contract is correct for closed periods but fragile for a long range ending in the current, still-open month. The realization report for an open month can be absent or incomplete, causing many current-month sales to fall through to individual posting-detail calls. A single unresolved detail then aborts the whole Period Profit request with `PERIOD_PROFIT_SALE_QUANTITY_EVIDENCE_UNAVAILABLE`.

The regression test reproduces the reported custom range `2026-05-03` through `2026-09-07` with a sale in the open September period and no realization quantity for that sale.

## Production correction

Verified production main after PR #455:

`e34b03c63ed47d39addb1bb354313709310b9db2`

The correction adds a read-only paginated `/v2/posting/fbo/list` quantity-evidence layer before exact posting-detail fallback.

Quantity source order is now:

1. monthly realization-by-posting evidence;
2. paginated FBO posting-list evidence for unresolved records, joined by exact `(posting_number, SKU)`;
3. exact FBO/FBS posting detail for any remaining unresolved key;
4. fail closed if exact quantity is still unknown.

No heuristic quantity is introduced. The code does not infer `1`, does not convert unknown quantity to zero, and does not use finance row count as a quantity substitute.

The batch FBO list is paginated with offset/limit and rejects ambiguous duplicate `(posting_number, SKU)` product evidence. Existing exact-detail fallback remains intact.

## Financial invariants preserved

This package does not change:

- account-level Ozon finance monetary authority;
- signed revenue semantics;
- positive-sale recognition semantics;
- configured tax policy;
- historical SKU cost authority;
- Return COGS recognition / authorization / commit / no-double-counting gates;
- seller-facing `read_only=True` and `executed=False` contract.

Canonical seller-facing Period Profit remains:

```text
period_profit = account_net_accrual
              + exact_committed_return_cogs_if_valid
              - product_cost
              - configured_tax
```

`unknown != zero` remains mandatory.

## Regression coverage

The sale-quantity authority tests now prove:

- closed-period realization quantity remains primary;
- an open-month unresolved realization row can be satisfied by paginated FBO list evidence;
- the exact reported custom range `2026-05-03`–`2026-09-07` is covered by the regression scenario;
- paginated list evidence avoids per-posting calls when exact list evidence exists;
- missing list evidence still falls back to exact posting detail;
- fully unresolved quantity still fails closed;
- return quantity is not reused as standard-sale quantity;
- duplicate finance sale evidence still fails closed.

## Verification evidence

Runtime package:

- exact feature head `47d9c79508cb8e9fd35e440dbbd2590e973ca086`: Verify #1531 — SUCCESS;
- PR #455 actual synthetic merge: Verify #1533 — SUCCESS;
- squash-merged production main `e34b03c63ed47d39addb1bb354313709310b9db2`: Verify #1534 — SUCCESS.

Documentation is reconciled only after the exact resulting production main passed full Verify.

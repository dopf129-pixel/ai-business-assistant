# Period Profit critical finance validation audit — production reconciliation

Control incident: live Telegram Period Profit returned `Финансовые данные недоступны за 2026-08-09` after SKU discovery had already been decoupled from the strict finance reader.

## Root cause

The actual account-finance path still used the strict `PeriodProfitOzonClient`. It treated ancillary decomposition fields as formula-critical, so an omitted/malformed `seller_price`, `sale_commission`, delivery-service accrued amount, or item-fee amount/container could abort the entire day even when authoritative account `total_amount` and seller revenue `sale_amount` were still available.

The canonical seller-facing Period Profit formula remains:

```text
period_profit = account_net_accrual
              + exact_committed_return_cogs_if_valid
              - product_cost
              - configured_tax
```

Ozon account-level accrual is the monetary authority. Unknown formula-critical data still fails closed and `unknown != zero` remains mandatory.

## Validation boundary after the fix

Formula-critical and fail-closed:
- account `total_amount` on every accrual;
- signed `sale_amount` for POSTING products, with recovery allowed only from exact `sale_price + bonus + coinvestment` when all three components are valid;
- POSTING/product/commission structure required to determine seller revenue and positive-sale count;
- API/transport, pagination, accrual-type, and malformed core-response failures.

Ancillary and explicitly incomplete rather than fatal:
- diagnostic `seller_price`;
- `sale_commission`;
- delivery-service accrued amounts;
- item-fee accrued amounts and ancillary fee containers.

Unknown ancillary values are not promoted as authoritative zero. The normalization layer inserts parser-safe zero only after recording an internal incompleteness marker. `PeriodProfitFinanceService` propagates that marker and the Period Profit summary exposes `fee_components_included=False` internally. Canonical profit continues to use authoritative account `net_accrual`, verified seller revenue, product cost, configured tax, and only committed return COGS.

Raw SKU discovery remains on a separate READ-ONLY `OzonClient`. Ozon mutations were not added. No Telegram diagnostic fields were added. Return COGS recognition/authorization/commit/no-double-counting gates are unchanged. Seller-facing Period Profit remains read-only and non-executing.

## Regression coverage

The package adds direct coverage for:
- missing diagnostic `seller_price` with valid canonical finance;
- missing `sale_commission`, delivery fee, and item-fee money;
- malformed ancillary fee containers;
- fail-closed missing `total_amount`;
- fail-closed unrecoverable `sale_amount`;
- exact three-component `sale_amount` recovery;
- explicit `sale_amount` precedence over incomplete diagnostics;
- malformed formula-critical commission structure;
- completeness propagation through finance and summary adapters.

## SHA-bound production evidence

Failed intermediate SHAs remain permanently failed and are not release evidence:
- `32af1c7c5e922f4cac63b123f1e739cbf8039be6` — Verify #1454 FAILED;
- `bc9005d2456094c82505d2ab1b1a68924525b48a` — Verify #1457 FAILED.

Successful production chain:
- exact feature head `44d2915f9efc2c9e962a7c58b3c998cdb21eb533` — Verify #1471 SUCCESS;
- PR #443 actual synthetic merge `15a24c9f59b37920925ae94e12d46da8501f5aac` — Verify #1472 SUCCESS, `2378 passed`;
- squash-merged production main `d9a22df1ef95ddcc6aaa0330382b192ebd21305c` — Verify #1473 SUCCESS.

This document is reconciled from exact verified production main `d9a22df1ef95ddcc6aaa0330382b192ebd21305c`. The separate documentation verification/merge chain must complete before the package is declared fully ready.

# Period Profit sale-type unit reconciliation — 2026-09-06

## Control evidence

For 2026-06-01 through 2026-06-30, the official Ozon accrual report contains 4,931 `Продажи / Выручка` units. Period Profit reported 4,930 units while its money reconciled: revenue 486,122.75 RUB and account net accrual 126,958.65 RUB.

The one-unit difference showed that sale-unit identity cannot be inferred only from `sale_amount > 0`: an explicit Ozon revenue accrual may represent a sold unit even when its sale money is zero. At configured cost 21 RUB/unit, the old result understated June COGS by 21 RUB.

## Production rule

`PeriodProfitFinanceService` now keeps two facts separate:

- money remains the signed official `sale_amount` and is never replaced by seller price;
- sold-unit identity uses the explicit Ozon accrual type `Выручка` / `Revenue` when available.

A zero-money explicit revenue row therefore contributes one sold unit and one unit of COGS. Positive revenue is not double-counted. `Возврат выручки`, discount/partner rows, ancillary POSTING rows, and unknown zero-money rows are not promoted to standard sales. The legacy positive-money fallback remains for records where an explicit revenue type cannot be resolved.

Ozon remains strictly read-only. Return COGS authorization/commit gates, account-level net accrual authority, configured tax, and Telegram output shape are unchanged.

## Regression coverage

The package adds tests for zero-money explicit revenue, positive revenue non-duplication, return exclusion, zero-money non-revenue exclusion, and the legacy positive-money fallback.

## Verified production evidence

- feature head: `7da3a6b5ec71e997f4ff79975a27782976bdf983`; Verify #1490 SUCCESS;
- PR #447 synthetic-merge Verify #1491 SUCCESS;
- production main: `c9fd1e2f20aab54bba018534d5a2cbf1f67e8a85`; Verify #1492 SUCCESS.

The expected June control result after deployment is 4,931 sold units and 103,551 RUB standard positive-sale COGS. Monetary revenue, account net accrual and tax are unchanged; before any separately authorized return-COGS restoration, profit decreases by 21 RUB versus the prior June bot result.

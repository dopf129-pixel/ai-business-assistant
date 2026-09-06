# Period Profit reaccrued sale quantity reconciliation

Production baseline: `08d0eaf99333a013df6ee8d91f6ce08da7859dba`.

## Proven Ozon evidence

Official August accrual evidence for posting `0226093297-0256-3`, SKU `3921245627` shows one physical FBO posting with this finance sequence:

- 2026-08-06: positive sale accrual, seller price +90.00, revenue component +69.20;
- 2026-08-07: reversal/cancellation of the sale accrual, seller price -90.00, revenue component -69.20;
- 2026-08-09: positive sale re-accrual, seller price +90.00, revenue component +69.20.

This proves that Ozon finance can emit more than one positive sale event for the same `posting_number + SKU` when the same physical posting is reversed and later re-accrued.

## Root cause

`PeriodProfitSaleQuantitySummaryService` previously treated a repeated positive finance sale event for the same physical `posting_number + SKU` as `PERIOD_PROFIT_SALE_QUANTITY_DUPLICATE_SALE_EVIDENCE` and failed the whole Period Profit request with `Данные о количестве проданных товаров недоступны`.

That duplicate rule confused finance event multiplicity with physical sale quantity authority.

## Corrected contract

For standard COGS quantity reconciliation:

- finance money remains fully signed and authoritative across all accrual/reversal/re-accrual events;
- physical quantity is resolved once per exact `posting_number + SKU`;
- quantity authority remains realization-by-posting, then read-only FBO posting list, then exact posting detail;
- repeated positive finance events for the same physical key are coalesced for quantity only;
- unknown quantity remains fail-closed;
- no `unknown = 0` or implicit `1 unit` fallback is introduced;
- Return COGS recognition/authorization/commit gates are unchanged;
- Ozon remains READ-ONLY.

## Regression evidence

A regression test models the exact August re-accrual pattern with two positive finance events for the same posting key and one authoritative physical quantity. Expected result: one physical sold unit, one COGS application for that posting, and two positive finance events retained only as diagnostics.

Verified lifecycle evidence before this docs reconciliation:

- feature head `2054e03b692816bff932d34257e4030cdf225f99` — full Verify #1541 SUCCESS;
- PR #457 synthetic merge — full Verify #1544 SUCCESS;
- resulting production main `08d0eaf99333a013df6ee8d91f6ce08da7859dba` — full Verify #1545 SUCCESS.

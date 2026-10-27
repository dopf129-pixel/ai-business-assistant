# Q18 — observation evidence normalization

Date: 2026-10-27
Status: VERIFIED

## Implemented

- Added pure `UnitPriceObservationNormalizer`. It consumes a Q17 evidence package without network/storage access and returns a bounded normalized projection; it does not calculate or label an observed profit.
- Monetary inputs use finite `Decimal` values and currency/percentage outputs use `ROUND_HALF_UP`. Signed finance totals, including corrections already present in source totals, remain signed.
- Gross finance revenue, discount points, net finance accrual, component breakdown and Performance CPC remain separate fields. `net_seller_revenue` (gross less discount points) is calculated only when the source explicitly marks discount points complete. Q17's existing `FinanceService` aggregate does not prove that every discount-point row is present, so current observed tax-base value stays `None`.
- Seller-revenue DRR is only produced when CPC and revenue windows, date basis and timezone match. Attributed-revenue DRR is a separate ratio using the Performance report's own attributed revenue. `OZON_ACCRUAL_DATE` and `PERFORMANCE_REPORT_DATE` do not match, so the current collector will not manufacture a common-cohort seller DRR.
- Added weighted sum/denominator aggregation (`Σamount / Σunits`), preserving the numerator when denominator is zero and returning no per-unit value. Missing denominators remain incomplete; posting/operation row count is never treated as units.
- Added a bounded in-memory deduplicator for stable row identities. Identical duplicate rows collapse; conflicting duplicates fail closed; account-scoped data and mismatched SKU are rejected. It returns only safe amount/date/basis/quantity fields, not source row IDs. A correction is accepted only when explicitly marked as a referenced `SIGNED_DELTA` with zero units; signed adjustments are preserved and cannot silently change the unit denominator.
- Mixed-price evidence remains `MIXED_PRICES`/`PRICE_HISTORY_UNCONFIRMED`; the declared effective-date day is warned as a potential mixed-price day. No account totals are allocated to SKU. Finance net and its component breakdown are not subtracted twice; Performance CPC is separate evidence and is never deducted again from finance net.
- Current Q17 aggregates do not expose stable transaction IDs, correction lineage, explicit complete discount-point coverage, successful units, or verified per-sale prices. Those completeness values remain unknown, preventing a comparable observed profit. Overlapping windows stay separate.

## Verification

Windows, Python 3.12.10. Tests ran with a new temporary storage root/baseline and pytest basetemp, dotenv/plugin autoload disabled, and provider/credential environment variables removed. The existing project venv was missing the already-declared `tzdata` package; a prior first test attempt therefore failed at timezone resolution. Installed only the declared `tzdata>=2025.1,<2027` requirement into a temporary target directory, without changing the project venv, then reran the checks.

Linked Q16–Q18 profile — **184 passed in 3.92s** across:

- `tests/test_unit_price_observation_normalizer.py`
- `tests/test_unit_price_observation_collection_service.py`
- `tests/test_unit_price_observation_repository.py`
- `tests/test_period_profit_sku_telegram_flow.py`
- `tests/test_current_unit_economics_production_wiring.py`
- `tests/test_period_profit_finance_sku_scope_v1401_v1410.py`
- `tests/test_period_profit_finance_safe_diagnostics.py`
- `tests/test_period_profit_finance_retry_v1441_v1450.py`
- `tests/test_ozon_performance_historical_reports.py`
- `tests/test_period_profit_sku_advertising.py`
- `tests/test_finance_service_accrual_fee_breakdown.py`

No real Ozon/Telegram API, credential, owner database, tracked `data/` file or bot process was used. Full pytest and exact-head CI are planned in Q33–Q35.

## Remaining limitation for Q19

Q18 normalizes the available evidence but does not estimate unit profit. The current finance source lacks the confirmed successful-unit denominator and per-sale price history needed to build that result. Q19 must keep a separately labeled model or return `INCOMPARABLE`/`INSUFFICIENT_DATA`; it must not turn these window totals into profit per unit.

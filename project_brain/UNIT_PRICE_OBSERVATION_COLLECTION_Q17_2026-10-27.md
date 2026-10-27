# Q17 — bounded read-only observation collection

Date: 2026-10-27
Status: VERIFIED

## Implemented

- Added `UnitPriceObservationCollectionService` as a read-only collector for a previously owner-confirmed observation. It enforces the exact saved FBO identity and seller-price record, and accepts only completed local-calendar windows of 3–56 days that do not predate the declared effective date.
- Reuses the existing finance and Ozon Performance adapters. Finance read sessions are prepared for the exact requested window. Their retries, pagination and Performance report polling reserve requests on a child `PeriodProfitOperationTrace` with a 60-second and 64-attempt budget. The trace is reset even when collection fails.
- Collects only the exact SKU's daily finance evidence and optional CPC evidence. CPC remains separate from finance totals; ordered/successful units, returns, price history, tax, cost and historical commission are not inferred by this stage.
- Preserves unsupported accrual type names/IDs and unknown response field names/types as bounded schema metadata only. Raw amounts, product titles, posting/accrual identifiers, credentials and API payloads are not copied into the evidence package.
- Marks unavailable or incomplete sources explicitly. It does not require Premium Analytics, mutate Ozon, or write a result revision; normalization/comparability are Q18–Q19 responsibilities.
- Factory composition injects the existing planning repository, finance service and Performance-by-SKU service into the collector. Runtime's default remains optional for compatibility with existing direct constructions.

## Verification

Windows, Python 3.12.10; isolated temporary test storage/basetemp, dotenv and pytest plugin autoload disabled, credential/provider environment variables removed. Tests used a fake finance transport and synthetic repository; no live API, credentials, owner database, tracked data or bot process was used.

Focused linked profile — **172 passed in 3.65s**:

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

`git diff --check` passed. `git diff -- data` was empty. The full pytest suite and CI are deferred to Q33–Q35.

## Known boundaries

- Finance aggregates are still adapter-produced evidence and are not yet a canonical observed profit per successful unit.
- The collector does not establish whether units with the owner-declared effective date all sold at the new price.
- Returned CPC is report-window evidence, not automatically a finance-reconciled or attributed expense.
- Stage Q18 must normalize/deduplicate source rows, determine weighted denominators and correction semantics, and keep revenue bases separate before any result can be compared.

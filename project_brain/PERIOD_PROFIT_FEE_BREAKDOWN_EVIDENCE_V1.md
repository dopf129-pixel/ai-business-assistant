# Period Profit Fee Breakdown Evidence v1

`PeriodProfitSummaryService` now aggregates the existing Ozon `fee_breakdown` by exact operation name for the whole requested period and for each product row.

The aggregation reuses the same finance responses already used to calculate `net_accrual`; it does not perform duplicate Ozon API calls.

This makes later return-financial evidence reproducible against the exact period-profit source data. The fee-breakdown values remain explanatory components of `net_accrual` and are not subtracted again from profit.

`returns_included=False` remains unchanged because the presence of return-related fee operations does not by itself prove complete return economics, product-cost recovery, or all reverse-logistics effects.

Review classification: Architecture Review Required because an existing summary contract is extended. Read-only analytics only.
# Period Profit Fee Breakdown v1

`PeriodProfitSummaryService` now propagates the fee components already reported by `FinanceService` into period and per-product summaries:

- commission;
- logistics;
- acquiring;
- other fees.

These fields are explanatory components of the existing Ozon `net_accrual`; they are not subtracted again when profit is calculated. Profit remains `net_accrual - product_cost - configured_tax`.

The change does not infer returns, advertising, or storage costs. Their coverage flags remain false until independently supported by source data.

No Ozon mutation, Product Decision mutation, Action Executor use, or automatic execution path is introduced.

Review classification: Architecture Review Required because an existing service contract was extended.

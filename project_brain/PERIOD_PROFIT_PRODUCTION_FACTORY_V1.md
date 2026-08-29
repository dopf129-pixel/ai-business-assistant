# Period Profit Production Factory v1

Wires the period-profit query to existing production dependencies:

- `ProductService.load_products` for the current product set;
- `FinanceService` for daily Ozon accruals;
- `ProductCostService` for stored product costs;
- configured `TAX_RATE` from `config.py`;
- `PeriodProfitSummaryService` and `PeriodProfitQueryService` for calculation and user-facing orchestration.

The factory is read-only with respect to Ozon and Product Decisions. It introduces no mutation or execution path.

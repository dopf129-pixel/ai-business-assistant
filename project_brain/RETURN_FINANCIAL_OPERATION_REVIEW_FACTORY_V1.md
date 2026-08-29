# Return Financial Operation Review Factory v1

Adds production wiring for the read-only return financial operation review report.

The factory builds the chain:

`FinanceService -> ReturnFinancialOperationCatalogService -> ReturnFinancialOperationReviewReportService`

It uses the existing Ozon accrual-type source and does not activate return mapping, profit adjustment, Product Decision execution, or Ozon mutation.

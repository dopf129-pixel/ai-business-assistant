# Current Checkpoint v1401-v1410

Period Profit product-cost scope is now derived from the unique SKUs present in Ozon finance accruals for the exact selected period.

The current product catalog remains identity/cost mapping evidence, not the authority for which SKUs belong to historical period revenue. Duplicate catalog rows for the same SKU are deduplicated before calculation. If a finance SKU has no catalog mapping, the calculation fails closed instead of inventing zero cost.

Account-level Ozon revenue and net accrual remain the monetary authority. The existing product-vs-account revenue reconciliation remains as a final integrity guard.

Production main `cb6f3fd3341debf52617688350a3c6d7cab336fd` passed Verify #1272. Artifact `9967892096`, digest `sha256:fb2a8fa99482e86d2c70e7e9a40547f71065899c1162e7916999511c585a4e7a`.

Ozon remains read-only.

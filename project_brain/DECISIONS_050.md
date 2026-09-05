# Decision 050 — Period Profit SKU Scope Comes From Finance Evidence

For a selected Period Profit interval, the authoritative SKU scope for product-cost attribution is the unique set of SKUs observed in Ozon finance `POSTING` accruals for that exact interval.

The product catalog is used to resolve product identity and configured cost only. It must not define historical revenue scope because current catalog state may contain stale entries, duplicate SKU rows, or differ from the set that actually participated in finance operations during the selected period.

Rules:
- deduplicate catalog entries by SKU before product-cost calculation;
- include only SKUs observed in finance `POSTING` operations for the selected period;
- if a finance SKU lacks catalog/cost mapping, fail closed; unknown cost is not zero;
- keep account-level Ozon revenue and `net_accrual` as monetary authority;
- retain revenue reconciliation as a final integrity check;
- never mutate Ozon business state.

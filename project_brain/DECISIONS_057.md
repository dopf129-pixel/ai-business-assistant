# Decision 057 — Raw Ozon Revenue Diagnostics Without Formula Mutation

When seller-facing Period Profit revenue does not reconcile with an official Ozon realization report, diagnostics must expose the raw finance `POSTING` commission fields before changing accounting semantics again.

The diagnostic set is `sale_amount`, `seller_price`, `sale_price`, `bonus`, and `coinvestment`. It is observational only: these values do not alter revenue, tax, Ozon net accrual, COGS, return COGS, profit, or margin. The existing Decision 056 `seller_price` revenue authority remains in force until evidence supports a different accounting mapping.

Diagnostics reuse the already-read daily finance cache and must not add Ozon mutations or additional business-state writes. Missing or malformed diagnostic evidence is unknown, not zero; observed partial sums may be shown only when explicitly labeled partial.

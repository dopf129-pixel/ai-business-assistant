# Decision 056 — Seller-Price Revenue Authority for Period Profit

Period Profit seller-facing revenue uses Ozon finance `POSTING` `commission.seller_price` as the revenue authority. `commission.sale_amount` is not used as seller-facing gross revenue because its pricing semantics can include discount-related value that does not match the seller realization basis.

Bonus and coinvestment values are not added separately. Account-level `total_amount` remains authoritative for net Ozon accruals, so the canonical profit formula does not change.

Missing, malformed, or non-finite `seller_price` fails closed. There is no fallback to `sale_amount` and unknown revenue must never become zero. The implementation is read-only and does not mutate Ozon.

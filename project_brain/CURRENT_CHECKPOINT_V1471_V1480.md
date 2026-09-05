# Current Checkpoint — v1471-v1480 Period Profit Revenue Diagnostics

Production runtime SHA: `e611dd9b5df1e5f3455ea308219d6391f77c107e`.

Period Profit now exposes a read-only diagnostic view of the raw Ozon finance `POSTING` commission fields `sale_amount`, `seller_price`, `sale_price`, `bonus`, and `coinvestment`. The diagnostic values are captured before the existing seller-price normalization and are aggregated from the same daily finance cache, without extra Ozon reads.

This package does not change the canonical Period Profit formula, account-level `total_amount` authority, configured tax behavior, COGS, return-COGS gates, or final profit application. `seller_price` remains the seller-facing revenue input from Decision 056.

Missing diagnostic values remain unknown: a complete field total is `None` when any record is missing or malformed, while explicitly observed partial sums are labeled partial rather than treated as zero. Ozon remains read-only.

Verification: exact production main `e611dd9b5df1e5f3455ea308219d6391f77c107e`, Verify run `33969459386`, full verification succeeded.

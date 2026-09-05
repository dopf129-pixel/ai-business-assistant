# Current Checkpoint v1461-v1470

## Period Profit Seller Revenue

Production feature main: `535412fdde19eadea10bcb47911404839a445ffc`.

- Period Profit seller-facing revenue now uses Ozon finance `POSTING` `commission.seller_price` rather than `commission.sale_amount`.
- Discount/bonus and coinvestment values are not added separately to revenue.
- Account-level `total_amount` remains the authority for Ozon net accruals and the canonical Period Profit formula is unchanged.
- Missing or invalid `seller_price` fails closed; unknown revenue is never converted to zero and there is no fallback to `sale_amount`.
- The change is scoped to the read-only Period Profit Ozon client; other finance consumers are not rewritten.
- Ozon remains read-only and all return COGS/no-double-count/accounting gates remain unchanged.

Verification: exact feature head `58a2a9e8f232d2814608c4c442fe6586f00ab8d9` passed Verify #1356; PR #429 synthetic merge `9f9e2160002fff00532e69f85210809fc0972335` passed Verify #1357; exact production main passed Verify #1358.

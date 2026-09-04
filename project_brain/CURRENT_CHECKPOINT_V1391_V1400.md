# Current Checkpoint v1391-v1400

Production Telegram validation exposed a false Period Profit revenue-coverage failure caused by an incomplete local Ozon product catalog.

The product catalog previously loaded only the first `/v3/product/list` page. Period Profit now refreshes all pages using the Ozon cursor before loading product identities from local storage.

The accounting reconciliation itself was not weakened: product-attributed revenue must still reconcile to the account-level Ozon revenue boundary. Account-level Ozon finance remains the monetary authority.

Catalog refresh is Ozon read-only and may write only to the local product identity cache. Any incomplete, malformed, repeated-cursor or failed refresh blocks the calculation rather than treating missing products as zero or using a stale subset.

Verified production main for this package: `d2695fe7863b8c27c66e3ba14055bc5e3d8bb35b` — Verify #1254 succeeded.

# Current Checkpoint v1391-v1400

Fixes Period Profit runtime failure when the local product catalog contains only the first Ozon product-list page.

The Period Profit product provider now refreshes the complete read-only Ozon catalog using `/v3/product/list` cursor pagination before loading local product identities. Incomplete, malformed, repeated-cursor, storage-failure, or page-limit refreshes fail closed instead of silently using a stale subset.

Account-level Ozon finance remains the monetary authority. The revenue reconciliation guard remains intact; this package fixes the catalog coverage that caused false mismatches for sellers with more than one product-list page.

Ozon business mutations remain prohibited. The refresh performs read-only Ozon API calls and only updates the local product identity cache.

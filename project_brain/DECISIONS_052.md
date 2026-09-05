# Decision 052 — Seller-Confirmed Historical Finance SKU COGS

## Decision

A historical Ozon finance SKU that has no current catalog row and no existing local COGS evidence must not receive an inferred cost. The seller may explicitly provide COGS through Telegram using `/costsku SKU COST`.

## Boundary

The command writes only to local `product_costs` storage using a synthetic identity `finance-sku:<SKU>`. It does not call any Ozon mutation endpoint and does not alter prices, ads, stock, cards, finance or other business state.

Period Profit may consume this record only through the existing exact-SKU local recovery path. The supplied cost must be finite, non-negative and RUB. Missing, invalid, ambiguous or unavailable cost remains unknown and fails closed.

Account-level Ozon finance remains the monetary authority. Product revenue reconciliation, Return COGS exact-once rules and no-double-count protections remain unchanged.

# v1491-v1500 — Today Period Profit

Production baseline: `f72d8551e1d82b7c0b818b3cbd2461a7ac9e380d` (Verify run `33982596416`).

- Seller-facing `прибыль ...` and `маржа ...` requests use the read-only Period Profit runtime.
- `сегодня` resolves to Period Profit `TODAY`, so profit and margin use the same account-level Ozon finance semantics as longer periods.
- Explicit unit-economics questions remain on the existing estimate/current-unit-economics path and are not intercepted by Period Profit.
- No Ozon mutation was introduced. Period Profit remains `read_only=True`, `executed=False`.

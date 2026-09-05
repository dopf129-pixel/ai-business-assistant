# AI Assistant Project State

## Current product state

AI Business Assistant remains a read-only Ozon business analyst and advisor. Ozon business mutations remain prohibited.

## Current verified checkpoint

Package: `v1431-v1440: Compact Period Profit Telegram Report`

Exact production main: `5c869fff0ea69c0e6dff979c639f0e0e1cf15cd3`

Verify #1318: success.

Artifact: `9968899898`.

Digest: `sha256:5fb6ce4f27c7bab94819380dc6c3f0e6dc789df4f1b2a67b488a878151bcd264`.

## Telegram Period Profit presentation

The seller-facing Period Profit report is now compact. The main Telegram message contains the selected period, revenue, Ozon accruals, sold units (`Продано SKU`), product cost, tax, profit, margin, previous-period delta, and only short warnings for incomplete evidence.

The previous verbose response is preserved as `details_text` for diagnostics but is no longer the default Telegram text.

Sold quantity comes from the existing exact `units_sold` aggregation. If the quantity is unavailable, presentation stays unknown (`—`) rather than inventing zero.

## Runtime validation

Seller-entered historical COGS for finance SKU `3398133813` allowed Period Profit to complete in Telegram for `2026-08-09 — 2026-09-05`. The returned report showed revenue `454034.93`, account net accrual `175004.50`, product cost `121212.00`, tax `27242.10`, profit `26550.40`, and margin `5.85%`.

This validates the local seller-confirmed historical SKU cost path externally. Remaining warnings are incomplete external-expense coverage and unresolved Return COGS recovery evidence; unknown values are not treated as zero.

## Period Profit accounting boundary

Account-level Ozon revenue and `net_accrual` remain the monetary authority. Product/account revenue reconciliation remains mandatory.

The canonical seller-facing calculation remains:

`period_profit = account_net_accrual + exact_committed_return_cogs_if_valid - product_cost - configured_tax`

Unknown monetary evidence remains `None`, never inferred zero. Ozon remains read-only.

## Verification lifecycle

Successful lifecycle for this package:

- feature head `da88353db080fea2ae21b8ac87d6430c7273772c` — Verify #1316 succeeded; artifact `9968812453`, digest `sha256:d9b341ae7ab901b4b3563d708c33660d4fb0f7915a7f3b45dd46b4ffd05e0f6b`;
- PR #423 synthetic merge `cccc6eaed915aa8d627c40d96a8d08714ac4e990` — Verify #1317 succeeded; artifact `9968811117`, digest `sha256:002960648649a83f3bc765436b61222c85046d98c9ff4588d8ecdc01ce7bcde9`;
- squash production main `5c869fff0ea69c0e6dff979c639f0e0e1cf15cd3` — Verify #1318 succeeded; artifact `9968899898`, digest `sha256:5fb6ce4f27c7bab94819380dc6c3f0e6dc789df4f1b2a67b488a878151bcd264`.

## Preserved boundaries

- account-level Ozon finance remains monetary authority;
- seller COGS is never inferred from Ozon finance;
- `/costsku` mutates only local cost storage, never Ozon;
- ambiguous or unknown money fails closed;
- no compensation double counting;
- exact-once Return COGS commitment remains append-only;
- compact presentation does not alter financial calculations;
- detailed diagnostic text remains available separately.

## Next product work

Use production runtime feedback to validate that `Продано SKU` matches seller expectations, then continue with unresolved Return COGS recovery evidence and external-expense coverage without weakening `unknown != zero`.

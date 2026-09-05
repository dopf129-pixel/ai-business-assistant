# Current Checkpoint v1431-v1440

Package: `Compact Period Profit Telegram Report`

Production feature-main: `5c869fff0ea69c0e6dff979c639f0e0e1cf15cd3`

Verify #1318: success.

Artifact: `9968899898`.

Digest: `sha256:5fb6ce4f27c7bab94819380dc6c3f0e6dc789df4f1b2a67b488a878151bcd264`.

## Shipped behavior

- Telegram Period Profit main text is compact and management-facing.
- Main text includes period, revenue, Ozon accruals, sold units, product cost, tax, profit, margin, comparison delta, and concise warnings.
- Previous verbose report is preserved as `details_text`.
- Sold units come from exact `units_sold`; unavailable quantity remains unknown (`—`).
- Financial formulas, Ozon read-only behavior, reconciliation, Return COGS gates, and `unknown != zero` are unchanged.

## Runtime validation

Seller-confirmed local COGS for finance SKU `3398133813` allowed the period `2026-08-09 — 2026-09-05` to complete in Telegram with profit `26550.40` and margin `5.85%`.

Remaining incomplete evidence is external-expense coverage and unresolved Return COGS recovery status.

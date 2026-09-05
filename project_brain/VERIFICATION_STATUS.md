# Verification Status

Date: 2026-09-05

## Latest verified product baseline

`5c869fff0ea69c0e6dff979c639f0e0e1cf15cd3`

Package: `v1431-v1440: Compact Period Profit Telegram Report`

### Exact feature head

- SHA `da88353db080fea2ae21b8ac87d6430c7273772c`;
- Verify #1316 succeeded;
- artifact `9968812453`;
- digest `sha256:d9b341ae7ab901b4b3563d708c33660d4fb0f7915a7f3b45dd46b4ffd05e0f6b`.

### PR integration checkout

- PR #423;
- synthetic merge SHA `cccc6eaed915aa8d627c40d96a8d08714ac4e990`;
- Verify #1317 succeeded;
- artifact `9968811117`;
- digest `sha256:002960648649a83f3bc765436b61222c85046d98c9ff4588d8ecdc01ce7bcde9`.

### Exact production main

- squash SHA `5c869fff0ea69c0e6dff979c639f0e0e1cf15cd3`;
- Verify #1318 succeeded;
- artifact `9968899898`;
- digest `sha256:5fb6ce4f27c7bab94819380dc6c3f0e6dc789df4f1b2a67b488a878151bcd264`.

## Product behavior verified

Telegram Period Profit now uses a compact management-facing presentation while preserving the full prior diagnostic text as `details_text`. The compact text adds sold quantity from exact `units_sold` evidence and does not modify any profit calculation.

Production runtime has also externally validated the local seller-confirmed historical SKU COGS path: finance SKU `3398133813` no longer blocks the selected period after the seller supplied its real local cost.

Unknown external expenses and unresolved Return COGS evidence remain unknown and are surfaced as short warnings rather than coerced to zero.

## Verification policy

Exact branch verification proves only that branch head. PR verification proves only the synthetic integration checkout. Every squash-main SHA requires its own exact verification. Failed SHAs remain failed permanently. Missing evidence is unknown, not zero. Ozon remains read-only.

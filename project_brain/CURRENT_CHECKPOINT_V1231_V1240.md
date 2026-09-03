# CURRENT_CHECKPOINT_V1231_V1240

Date: 2026-09-03

## Finance Accrual Pagination & Read Session Integrity

Production package:

`v1231-v1240: Finance Accrual Pagination & Read Session Integrity`

Goal:

Fix live Period Profit finance-unavailable failures by honoring the current Ozon finance accrual cursor contract, reading all pages, and reducing duplicate same-day API reads across SKUs.

## Live issue

Observed seller-facing message:

`Финансовые данные недоступны за 2026-06-06`

## Root causes addressed

### Ozon request contract

`POST /v1/finance/accrual/by-day` requires a `last_id` request field.

The first request must send an empty string.

The previous client sent only `date`.

### Pagination completeness

The accrual endpoint returns a cursor in `last_id`.

The previous client read one page only, so finance evidence for a target SKU could be missed when it appeared on a later page.

### Duplicate day downloads

Period Profit calculates product-by-product.

FinanceService previously fetched the complete daily accrual payload again for every SKU, multiplying request volume on long periods.

## Verified behavior

- first request body contains:
  - `date`;
  - `last_id: ""`;
- later pages use the returned cursor;
- pagination ends only when returned `last_id` is empty;
- malformed pages fail closed;
- repeated cursor fails closed;
- page-cap exhaustion fails closed;
- target SKU evidence from a second page is included;
- one daily accrual payload is reused for all SKUs inside a read session;
- every Period Profit summary starts a fresh read session;
- read-session errors are seller-safe and do not expose private exception text.

## Product boundary

Decision 036 remains active and unchanged.

This package changes read-only finance retrieval integrity only.

No price, advertising, stock, product-card or other Ozon mutation is introduced.

No profit, tax or return-cost formula is changed.

## SHA-bound verification

- entering exact main `400ca040d743dc7db93480605ebd62a7fe9b02f3`: Verify #984, 2131 passed / 0 failed, artifact 9887796288, digest `sha256:8081f8fc794c49b95c4012940e030db7cac46d5a7560d622c14f02086f821313`;
- failed `8d159ed09410ed978bef6cfdb5719a67bc5491b1`: Verify #990, 2140 passed / 1 failed, artifact 9888518874, digest `sha256:428c75b168488fa3f7c415751d2622917aee6d32c4474e2c8da7ada5757fde81`;
- final feature `ad215b8d86c547e740dcb3583e7b7f580e9fb823`: Verify #991, 2141 passed / 0 failed, artifact 9888545229, digest `sha256:64a52c5115d3ebd12f0988c0c36ae2b04e11463b56ec4c9d792b93e5bc2d832c`;
- PR #383 synthetic `4b1f8e48de3f92c6aecc590232697890c8814d08`: Verify #992, 2141 passed / 0 failed, artifact 9888577950, digest `sha256:1eb510792dc9693d39d425ed1b178f113dffa4ee9a054ab518a2a18c73981d92`;
- squash main `e66125d5e2c737497762178bef86dd36a62721f3`: Verify #993, 2141 passed / 0 failed, artifact 9888609599, digest `sha256:c42afb3d6c2beb970d7e46a610abf0c59be8712482fdc6b5eee05c525da32cee`.

Failed SHA evidence is not transferable.

## Next live validation

After local update and Telegram restart, rerun the same Period Profit request.

Expected behavior:

- the first day should no longer fail merely because the request omitted `last_id`;
- later accrual pages should be included;
- long periods with multiple SKUs should issue substantially fewer duplicate day requests;
- if Ozon still returns a genuine API error, Period Profit remains fail-closed and does not invent finance values.

GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.

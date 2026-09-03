# AI Assistant Project State

## Current product state

AI Business Assistant

## Product role

Read-only Ozon business analyst and advisor.

The assistant may read seller/business evidence, analyze it, compare periods, explain risks, rank priorities, recommend next steps, and prepare non-executable drafts/checklists.

The assistant must not mutate Ozon business state.

## Current verified checkpoint

Package:

`v1231-v1240: Finance Accrual Pagination & Read Session Integrity`

Goal:

Fix live Period Profit finance-unavailable failures by honoring the current Ozon `/v1/finance/accrual/by-day` cursor contract, reading all pages, and avoiding duplicate same-day downloads for every SKU.

Immediately preceding verified package:

`v1221-v1230: Period Profit Revenue Share Presentation`

## Stable verification

Latest exact production main:

`e66125d5e2c737497762178bef86dd36a62721f3`

GitHub Actions push Verify #993:

2141 passed / 0 failed.

## Root causes fixed

1. The Ozon accrual-by-day request now requires `last_id`; the first page must send an empty string.

2. The endpoint is cursor-paginated. Reading only one page could omit finance evidence for products present on later pages.

3. Period Profit previously re-downloaded the same full day once for each SKU, multiplying API calls and rate-limit pressure on long periods.

## Verified behavior

- first finance accrual request sends `last_id=""`;
- pages are followed until Ozon returns an empty cursor;
- malformed pages, repeated cursors, and page-limit exhaustion fail closed;
- second-page SKU evidence is included;
- one daily accrual payload is reused across all SKUs inside a Period Profit calculation;
- every Period Profit summary starts a fresh read session, so cached evidence does not leak between calculations.

## Production evidence

Entering exact docs-reconciled main:

- `400ca040d743dc7db93480605ebd62a7fe9b02f3` / Verify #984 / 2131 passed / 0 failed.

Failed intermediate:

- `8d159ed09410ed978bef6cfdb5719a67bc5491b1` / Verify #990 / 2140 passed / 1 failed.
- failure was test-only: a new test assumed raw Ozon success responses always contain an `error` key.

Final feature:

- `ad215b8d86c547e740dcb3583e7b7f580e9fb823` / Verify #991 / 2141 passed / 0 failed.

PR integration:

- PR #383 synthetic `4b1f8e48de3f92c6aecc590232697890c8814d08` / Verify #992 / 2141 passed / 0 failed.

Squash main:

- `e66125d5e2c737497762178bef86dd36a62721f3` / Verify #993 / 2141 passed / 0 failed.

## Preserved boundaries

- Decision 036 read-only analyst boundary;
- no profit/tax formula changes;
- no return-cost inference;
- no Product Decision/Product Task Draft execution;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.

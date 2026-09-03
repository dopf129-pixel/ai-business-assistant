# AI Assistant Project State

## Current product state

AI Business Assistant

## Product role

Read-only Ozon business analyst and advisor.

The assistant may read seller/business evidence, analyze it, compare periods, explain risks, rank priorities, recommend next steps, and prepare non-executable drafts/checklists.

The assistant must not mutate Ozon business state.

## Current verified checkpoint

Package:

`v1171-v1180: Telegram Custom Period Date Input`

Goal:

Let sellers request Period Profit for a concrete calendar range using familiar `ДД.ММ.ГГГГ` input while preserving the existing ISO path and strict read-only analytics boundary.

Immediately preceding verified package:

`v1161-v1170: Telegram Period Profit Analyst Wiring`

## Stable verification

Latest exact production main:

`05f94da42e21c5ad5f7d78cb7f55bb2d40730f77`

GitHub Actions push Verify #886:

2081 passed / 0 failed.

Preserved product boundary:

- assistant is an analyst/advisor, not an Ozon executor;
- localized dates are normalized to ISO before the existing Period Profit query layer;
- no finance formula change;
- no Product Decision execution;
- no Product Task Draft execution;
- no Action Executor connection;
- no Ozon mutation;
- `externally_verified=False`.

## Production evidence

Entering exact verified docs-main:

- `fa30bafeecfa9291175e7f1c4ac0ad2c078b4607` / Verify #881 / 2071 passed / 0 failed.

Final feature:

- `62b040e392514bc410b34d82eccb8e0385b9c548` / Verify #884 / 2081 passed / 0 failed.

PR integration:

- PR #371 synthetic `b865b551289ba4592d8d32594323ea8a6dc64c61` / Verify #885 / 2081 passed / 0 failed.

Squash main:

- `05f94da42e21c5ad5f7d78cb7f55bb2d40730f77` / Verify #886 / 2081 passed / 0 failed.

No failed production SHA occurred in this package.

## Telegram analyst capability added

Supported examples:

- `прибыль 01.05.2026 - 03.09.2026`;
- `прибыль 1.5.2026 - 3.9.2026`;
- en dash / em dash between dates;
- existing `прибыль 2026-05-01 - 2026-09-03` remains supported.

Invalid or incomplete custom calendar dates fail closed without querying finance.

## Development direction

Next analytical priorities:

- seller-facing "what needs attention today" summary;
- sales and profit period comparison;
- stock/out-of-stock risk;
- advertising-efficiency analysis from read-only evidence;
- returns/non-buyout impact;
- explainable SKU prioritization.

Do not add Ozon mutation/execution capability.

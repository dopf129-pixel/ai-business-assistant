# AI Assistant Project State

## Current product state

AI Business Assistant

## Product role

Read-only Ozon business analyst and advisor.

The assistant may read seller/business evidence, analyze it, compare periods, explain risks, rank priorities, recommend next steps, and prepare non-executable drafts/checklists.

The assistant must not mutate Ozon business state.

## Current verified checkpoint

Package:

`v1181-v1190: Tax Policy Production Availability`

Goal:

Restore the validated production tax policy for clean Telegram deployments so current unit economics can calculate tax and base profit, while preserving fail-closed unknown-tax semantics when no explicit policy exists.

Immediately preceding verified package:

`v1171-v1180: Telegram Custom Period Date Input`

## Stable verification

Latest exact production main:

`9c9d379e36edf2123a466ad2b3cd1d000d81bae3`

GitHub Actions push Verify #902:

2091 passed / 0 failed.

Preserved product boundary:

- assistant remains read-only analyst/advisor;
- validated production policy is USN Income 6%;
- persisted tax configuration is explicit and non-secret;
- explicit environment tax policy is accepted only when `TAX_MODE` is actually present;
- missing tax policy remains unknown and is never converted to zero;
- malformed persisted tax policy remains fail-closed;
- no finance formula change;
- no Product Decision/Product Task Draft execution;
- no Ozon mutation;
- `externally_verified=False`.

## Production evidence

Entering exact verified docs-main:

- `8ca28c36249a052fdf83cfd5ab86a13d986cbb1c` / Verify #896 / 2081 passed / 0 failed.

Final feature:

- `1d0df2799fb87b57d916843a96a080389e2ac07b` / Verify #900 / 2091 passed / 0 failed.

PR integration:

- PR #373 synthetic `a6493407f0bb915f366573404fcffd220e6757a1` / Verify #901 / 2091 passed / 0 failed.

Squash main:

- `9c9d379e36edf2123a466ad2b3cd1d000d81bae3` / Verify #902 / 2091 passed / 0 failed.

No failed production SHA occurred in this package.

## Seller-facing result

For the verified hook-2-like current-economics sample at 100 ₽:

- commission: 17.00 ₽;
- logistics: 17.54 ₽;
- last mile: 1.54 ₽;
- acquiring: 1.09 ₽;
- product cost: 21.00 ₽;
- tax: 6.00 ₽;
- base net profit before return-risk adjustment: 35.83 ₽.

Returns/non-buyout evidence remains a separate completeness boundary and is not assumed to be zero.

## Development direction

Next analytical priorities:

- improve unit-economics presentation when base profit is known but returns evidence is incomplete;
- seller-facing "what needs attention today" summary;
- sales and profit period comparison;
- stock/out-of-stock risk;
- advertising-efficiency analysis from read-only evidence;
- returns/non-buyout impact;
- explainable SKU prioritization.

Do not add Ozon mutation/execution capability.

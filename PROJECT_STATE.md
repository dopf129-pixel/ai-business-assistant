# AI Assistant Project State

## Current product state

AI Business Assistant

## Product role

Read-only Ozon business analyst and advisor.

The assistant may read seller/business evidence, analyze it, compare periods, explain risks, rank priorities, recommend next steps, and prepare non-executable drafts/checklists.

The assistant must not mutate Ozon business state.

## Current verified checkpoint

Package:

`v1211-v1220: Period Profit Tax Rate Unit Integrity`

Goal:

Fix the live Period Profit result where a configured 6% tax rate was passed as multiplier `6.0` instead of fraction `0.06`, while adding fail-closed protection against future percent/fraction unit mismatches.

Immediately preceding verified package:

`v1201-v1210: Period Profit Data Completeness Integrity`

## Stable verification

Latest exact production main:

`2f438bd6bb739938cee4fe56b83af8f4a563f942`

GitHub Actions push Verify #957:

2121 passed / 0 failed.

## Live issue fixed

Seller output showed:

- revenue: 1 348 371.10 ₽;
- tax: 8 090 226.60 ₽;
- profit: -7 698 622.78 ₽;
- margin: -570.96%.

Root cause:

- tax configuration stores rates in percentage units, where `6.0 = 6%`;
- Period Profit summary expects a fractional multiplier, where `0.06 = 6%`;
- production factory passed the percentage value without conversion.

## Verified behavior

For the seller-provided financial sample at USN Income 6%:

- revenue: 1 348 371.10 ₽;
- Ozon net accrual: 752 971.82 ₽;
- product cost: 361 368.00 ₽;
- tax: 80 902.27 ₽;
- operational profit before returns/advertising/storage: 310 701.55 ₽;
- margin: 23.04%.

Additional protections:

- production Period Profit reads the validated TaxConfigurationService policy;
- `USN_INCOME 6.0%` converts to `0.06`;
- `NONE` converts to `0.0`;
- unsupported tax modes fail closed instead of using the wrong formula;
- PeriodProfitSummaryService rejects tax multipliers outside `0..1`.

## Production evidence

Entering exact verified docs-main:

- `590b068ef46f58e56509ac038759f465975c9a8a` / Verify #949 / 2111 passed / 0 failed.

Failed intermediates:

- `a7d5cead4c7c49907d6d045b54a3cec30d48efad` / Verify #953 / 2110 passed / 1 failed.
- `ee463cd1000113998ae5b895da02334bb5a5f495` / Verify #954 / 2120 passed / 1 failed.
- both failures were legacy factory-test contract drift after removing direct `TAX_RATE` wiring.

Final feature:

- `4c50429bc4c2f6515d80b497b85fe8c9663e24eb` / Verify #955 / 2121 passed / 0 failed.

PR integration:

- PR #379 synthetic `68c0f7360dd93738377f7111f5f4732d0b4d48af` / Verify #956 / 2121 passed / 0 failed.

Squash main:

- `2f438bd6bb739938cee4fe56b83af8f4a563f942` / Verify #957 / 2121 passed / 0 failed.

## Preserved boundaries

- Decision 036 read-only analyst boundary;
- no finance source change;
- no return-cost inference;
- no Product Decision/Product Task Draft execution;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Next analytical priority

Seller-requested Period Profit presentation improvement:

- show each monetary line with its percentage of revenue in parentheses;
- revenue itself = 100%;
- if revenue is zero, do not invent percentages;
- keep all calculations read-only and preserve existing amounts.

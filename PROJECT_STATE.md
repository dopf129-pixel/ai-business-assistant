# AI Assistant Project State

## Current product state

AI Business Assistant

## Product role

Read-only Ozon business analyst and advisor.

The assistant may read seller/business evidence, analyze it, compare periods, explain risks, rank priorities, recommend next steps, and prepare non-executable drafts/checklists.

The assistant must not mutate Ozon business state.

## Current verified checkpoint

Package:

`v1221-v1230: Period Profit Revenue Share Presentation`

Goal:

Show the percentage of revenue in parentheses next to each main Period Profit monetary line without changing any financial calculation.

Immediately preceding verified package:

`v1211-v1220: Period Profit Tax Rate Unit Integrity`

## Stable verification

Latest exact production main:

`08d0d0fa6860101921ead603ec4a00b95c9ee8bf`

GitHub Actions push Verify #972:

2131 passed / 0 failed.

## Seller-facing presentation

For the verified seller sample:

- Revenue: 1 348 371.10 ₽ (100.00%);
- Ozon net accrual: 752 971.82 ₽ (55.84%);
- Commission: 190 333.00 ₽ (14.12%);
- Logistics: 369 353.19 ₽ (27.39%);
- Acquiring: 15 778.95 ₽ (1.17%);
- Other fees: 19 934.14 ₽ (1.48%);
- Product cost: 361 368.00 ₽ (26.80%);
- Tax: 80 902.27 ₽ (6.00%);
- Profit: 310 701.55 ₽ (23.04%).

Behavior:

- negative profit keeps a negative revenue share;
- fee lines use the same absolute monetary presentation as before and therefore show positive deduction shares;
- when revenue is zero, percent-of-revenue is omitted;
- the existing margin line and previous-period comparison percentage keep their original meaning.

## Production evidence

Entering exact docs-reconciled main:

- `5cb69fed7bc44fcd5f66a8a004e625bee9993953` / Verify #967 / 2121 passed / 0 failed.

Final feature:

- `77994ccb67c060f7c01694ac65eea5c8aec24e1d` / Verify #970 / 2131 passed / 0 failed.

PR integration:

- PR #381 synthetic `b9a72b875081d6f12fe7f5b50d4b0c6f6af13e89` / Verify #971 / 2131 passed / 0 failed.

Squash main:

- `08d0d0fa6860101921ead603ec4a00b95c9ee8bf` / Verify #972 / 2131 passed / 0 failed.

No failed production SHA occurred in this package.

## Preserved boundaries

- Decision 036 read-only analyst boundary;
- no finance formula change;
- no tax formula change;
- no return-cost inference;
- no Product Decision/Product Task Draft execution;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.

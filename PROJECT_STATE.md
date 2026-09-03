# AI Assistant Project State

## Current product state

AI Business Assistant

## Product role

Read-only Ozon business analyst and advisor.

The assistant may read seller/business evidence, analyze it, compare periods, explain risks, rank priorities, recommend next steps, and prepare non-executable drafts/checklists.

The assistant must not mutate Ozon business state.

## Current verified checkpoint

Package:

`v1241-v1250: Account-Level Ozon Profit Reconciliation`

Goal:

Move Period Profit materially closer to seller net profit by making complete account-level Ozon daily accruals the authoritative monetary source while retaining SKU-level evidence for COGS and product revenue reconciliation.

Immediately preceding verified package:

`v1231-v1240: Finance Accrual Pagination & Read Session Integrity`

## Stable verification

Latest exact production main:

`a359e3d8e68784849caa659dec0123fb15dc6932`

GitHub Actions push Verify #1012:

2151 passed / 0 failed.

## Decision 037

Period Profit monetary ownership is now:

- account-level Ozon daily accruals are authoritative for revenue, net accrual, commission, logistics, acquiring, other fees and fee breakdown;
- SKU-level finance remains product-attribution evidence for unit counts, product revenue reconciliation, COGS and drill-down;
- summed SKU revenue must reconcile to account-level revenue within 0.01 RUB;
- mismatch fails closed;
- mapped Ozon expenses already present inside account net accrual are never subtracted a second time.

## Verified seller-facing behavior

New V2 scope:

`OZON_ACCOUNT_ACCRUALS_COST_AND_CONFIGURED_TAX_V2`

Formula:

`profit = account_net_accrual - product_cost - configured_tax`

Additional evidence:

- `sku_attributed_net_accrual`;
- `ozon_account_reconciliation`;
- `product_revenue_reconciled`;
- `account_level_ozon_accruals_included=True`.

The Telegram response may show the account reconciliation amount when non-zero and explains that account-level Ozon money is already included, so mapped returns/advertising/storage evidence must not be deducted again.

## Production evidence

Entering exact docs-reconciled main:

- `0aa27a1267b9d54f1207455b05e32db843091d86` / Verify #1003 / 2141 passed / 0 failed.

Final feature:

- `a0e528f36b1b4721af0e8d0b419c414d20fabea6` / Verify #1010 / 2151 passed / 0 failed.

PR integration:

- PR #385 synthetic `4a361a58d62e56c2e2aa4c608620ae86992ac05f` / Verify #1011 / 2151 passed / 0 failed.

Squash main:

- `a359e3d8e68784849caa659dec0123fb15dc6932` / Verify #1012 / 2151 passed / 0 failed.

No failed production SHA occurred in this package.

## Preserved boundaries

- Decision 036 read-only analyst boundary;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- no tax-rate formula change;
- no return-cost inference;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Remaining path toward accounting net profit

The product is now closer to real seller profit, but accounting net-profit claim remains blocked until additional evidence is established for:

- return-related COGS reversal / goods recovery semantics;
- non-Ozon business expenses and overhead;
- any taxes/adjustments outside the configured tax policy;
- full classification coverage for returns, advertising and storage.

Next package should target return/COGS evidence before inventing any external accounting assumptions.

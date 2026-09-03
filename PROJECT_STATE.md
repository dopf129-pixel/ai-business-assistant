# AI Assistant Project State

## Current product state

AI Business Assistant

## Product role

Read-only Ozon business analyst and advisor.

The assistant may read seller/business evidence, analyze it, compare periods, explain risks, rank priorities, recommend next steps, and prepare non-executable drafts/checklists.

The assistant must not mutate Ozon business state.

## Current verified checkpoint

Package:

`v1281-v1290: Historical Product Cost Evidence`

Goal:

Provide explicit effective-dated product cost evidence for originating sales without treating the mutable current cost as historical fact.

Immediately preceding verified package:

`v1271-v1280: Return Sale-Period Lineage Evidence`

## Stable verification

Latest exact production main:

`9ca4497dda61615076b8203d0404502630ab7e81`

GitHub Actions push Verify #1105:

2195 passed / 0 failed.

## Seller-facing accounting progress

Period Profit V2 continues to use account-level Ozon daily finance as the monetary authority.

Base formula remains:

`period_profit = account_net_accrual - product_cost - configured_tax`

External expense adjustment remains:

`profit_after_external_expenses = period_profit - external_expenses`

only with explicit external-expense coverage.

Return COGS evidence now has two independently proven layers:

1. selected-period originating sale lineage by positive Ozon sale accrual matched on `posting_number + SKU`;
2. effective-dated historical product cost evidence applicable to that matched sale date.

Decision 039 establishes a separate append-only `product_cost_history` evidence contract.

Important semantics:

- existing `product_costs` remains mutable current configuration;
- current cost rows are not migrated/backfilled into history;
- current-cost updates without explicit history do not create historical evidence;
- each historical version requires an explicit `effective_from`;
- duplicate `product_id + effective_from` versions are rejected;
- lookup uses the latest explicit version effective on the originating sale date;
- ambiguous product identity remains unconfirmed;
- dates before the first explicit version remain unknown.

When every Return COGS candidate has complete sale lineage and a unique applicable historical version, `historical_cost_basis_confirmed=True`.

Historical candidate value is evidence only and still does not change Period Profit.

## Explicit boundaries

Accounting net-profit claim remains prohibited.

Still not fully proven:

- saleable/restored inventory recovery after returns;
- originating sale quantity consistency as a separate accounting fact;
- compensation timing/accounting across periods;
- taxes/accounting adjustments outside configured tax policy;
- completeness of seller external expenses without explicit coverage.

Return COGS remains conservative:

- `confirmed_cogs_recovery_amount=0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- `saleable_inventory_recovery_confirmed=False`.

## Production evidence

Entering exact docs-reconciled main:

- `212df575cc60a809032954d425902fad86623956` / Verify #1095 / 2185 passed / 0 failed / artifact 9906001699 / digest `sha256:a50fb08552d73f187bbacc608751655880f293578a7ac4408154808d82a16f79`.

No failed production SHA occurred in v1281-v1290.

Cancelled intermediate SHAs carry no transferable success evidence.

Final feature:

- `f3fcb80588f394eb05e5944ca2812ed59adf7649` / Verify #1103 / 2195 passed / 0 failed / artifact 9906200014 / digest `sha256:c776260a5026572cbe27c2bab5212d2a64d92d95f7a9170a433a2d5b12b46af7`.

PR integration:

- PR #393 synthetic `672e18f904768742917df9c808c48ec476d9fd3e` / Verify #1104 / 2195 passed / 0 failed / artifact 9906235551 / digest `sha256:d849f4a6413df1de6c6b3e28ed4f5c45465b292266db2c31dbac3602251fcfb0`.

Squash main:

- `9ca4497dda61615076b8203d0404502630ab7e81` / Verify #1105 / 2195 passed / 0 failed / artifact 9906262083 / digest `sha256:6bc9ab6699976e56572a216dab839e96c8921f484047c522eb00535163626987`.

## Preserved boundaries

- Decision 036 permanent read-only Ozon analyst boundary;
- Decision 037 account-level Ozon monetary authority;
- Decision 038 external operating expense evidence/coverage contract;
- Decision 039 versioned historical product cost evidence contract;
- no Period Profit formula change;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- no double subtraction;
- current cost behavior preserved;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Remaining path toward accounting net profit

The most material return COGS blocker is now proof that returned units actually restored saleable inventory value or another accounting-equivalent asset value.

Historical cost and selected-period lineage can now be confirmed independently, but neither proves inventory recovery.

A future package must keep missing recovery evidence unknown, distinguish compensated/non-saleable outcomes, and prevent double counting between recovered inventory value and Ozon compensation.

Only after inventory recovery is proven should automatic return COGS reversal be reconsidered.

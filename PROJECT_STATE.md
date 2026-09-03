# AI Assistant Project State

## Current product state

AI Business Assistant

## Product role

Read-only Ozon business analyst and advisor.

The assistant may read seller/business evidence, analyze it, compare periods, explain risks, rank priorities, recommend next steps, and prepare non-executable drafts/checklists.

The assistant must not mutate Ozon business state.

## Current verified checkpoint

Package:

`v1291-v1300: Return Inventory Recovery Evidence`

Goal:

Add explicit return-level evidence for whether a returned unit restored saleable inventory, without inferring recovery from stock snapshots, stock deltas, or Returns API placement status.

Immediately preceding verified package:

`v1281-v1290: Historical Product Cost Evidence`

## Stable verification

Latest exact production main:

`3f82b65054a2a7a48b9918803c197377bdb3557f`

GitHub Actions push Verify #1131:

2208 passed / 0 failed.

## Seller-facing accounting progress

Period Profit V2 keeps Decision 037 account-level Ozon monetary authority.

Base formula remains:

`period_profit = account_net_accrual - product_cost - configured_tax`

External expense adjustment remains evidence-bound:

`profit_after_external_expenses = period_profit - external_expenses`

Return COGS evidence can now independently establish:

1. originating sale lineage in the selected period by positive Ozon sale accrual matched on `posting_number + SKU`;
2. effective-dated historical product cost for that matched sale date;
3. explicit return-level inventory recovery state from `return_inventory_recovery_history`.

Decision 040 forbids using stock snapshots, stock deltas, or Returns API return-location status as automatic proof of saleable inventory restoration.

Explicit recovery states:

- `SALEABLE_RESTORED`;
- `NON_SALEABLE`.

Missing recovery evidence remains unknown.

Aggregate `saleable_inventory_recovery_confirmed=True` requires a complete return sample, exact identity, exact quantity match and `SALEABLE_RESTORED` for every Return COGS candidate.

## Explicit boundaries

Even when sale lineage, historical cost and saleable recovery are all confirmed:

- recovery accounting-period attribution remains unconfirmed;
- originating sale quantity consistency remains unconfirmed as a separate accounting fact;
- compensation accounting treatment remains unconfirmed;
- compensated returns remain outside automatic saleable recovery;
- `confirmed_cogs_recovery_amount=0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- accounting net-profit claim remains prohibited.

## Production evidence

Entering exact docs-reconciled main:

- `7f859d1073338c5c0144edea8fe15574460e5210` / Verify #1115 / 2195 passed / 0 failed / artifact 9906440691 / digest `sha256:42618c7cd0f12fdd9b1c49f2231c990c71c6931727af3a09e1035719f248929a`.

Failed intermediate SHAs remain failed evidence:

- `41b409edcd2a96016bf49e8e8303a7aec00c1886` / Verify #1125 / compile failure / no verification artifact;
- `4643126328c9e461712aae30f5f7a694a7549e89` / Verify #1126 / compile failure at Period Profit response / no verification artifact;
- `d90549d21c8fb46b0a9012c205520c68e012dbfa` / Verify #1127 / compile failure due unmatched response parenthesis / no verification artifact;
- `13e4cfbacf617bb60c5b897137b619f079c3d500` / Verify #1128 / 2203 passed / 5 failed / artifact 9906768012 / digest `sha256:59dd7f0d342951b258bdef1d45b934cd107a858fc986d9326d1f06df016c2944`.

Cancelled intermediate SHAs carry no transferable success evidence.

Final feature:

- `1a83e5466bfebd79370e9576ce00b43b79bb668d` / Verify #1129 / 2208 passed / 0 failed / artifact 9906795648 / digest `sha256:a20b8f66b8d28365b7c9d887250782e7ab01d7885ddcca75c5bfab90541bd875`.

PR integration:

- PR #395 synthetic `7d7b3a5e180a2505850345cc753a7d40ba391cbf` / Verify #1130 / 2208 passed / 0 failed / artifact 9906847145 / digest `sha256:36f7babc92f4f0d39e708927a61e95122eada8b76892dc4eb7da8912f3e01fa4`.

Squash main:

- `3f82b65054a2a7a48b9918803c197377bdb3557f` / Verify #1131 / 2208 passed / 0 failed / artifact 9906878610 / digest `sha256:45eb967f32521ae3c7a2007663f6acfffcf6fa2f1fbdddb58bc332f56a02311d`.

## Preserved boundaries

- Decision 036 read-only Ozon analyst boundary;
- Decision 037 account-level Ozon monetary authority;
- Decision 038 external operating expense coverage contract;
- Decision 039 versioned historical product cost evidence;
- Decision 040 explicit return inventory recovery evidence;
- no Period Profit formula change;
- no stock-delta inference;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- no double subtraction;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Remaining path toward return COGS recovery

The next material blocker is accounting-period attribution of an already confirmed saleable recovery, together with originating-sale quantity consistency and compensation double-count prevention.

Until those facts are independently proven, Return COGS remains evidence-only and cannot change profit.

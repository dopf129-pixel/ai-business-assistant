# CURRENT_CHECKPOINT_V1281_V1290

Date: 2026-09-03

## Historical Product Cost Evidence

Production package:

`v1281-v1290: Historical Product Cost Evidence`

Goal:

Add explicit effective-dated historical product cost evidence so return COGS can use seller-confirmed cost applicable to the originating sale date without treating mutable current cost as historical fact.

## Architecture decision

Decision 039 implemented.

Historical cost is a separate append-only evidence contract.

Existing `product_costs` remains the mutable current-cost configuration.

New `product_cost_history` stores explicit versions with:

- product_id;
- SKU and/or offer_id;
- finite non-negative cost;
- currency;
- explicit `effective_from`;
- evidence source;
- recorded timestamp.

No automatic migration/backfill from current cost is allowed.

## Version semantics

For a target sale date, historical lookup selects the latest explicit cost version whose `effective_from` is not later than that date.

Fail-closed rules:

- no version before/at the sale date => missing;
- duplicate `product_id + effective_from` version => conflict;
- ambiguous identity across products => unconfirmed;
- invalid/non-finite/negative cost => rejected;
- invalid effective date => rejected;
- mutable current cost is never used as historical fallback.

Deleting or changing current cost does not erase append-only historical evidence.

## Return COGS integration

Historical cost is resolved only after selected-period sale lineage identifies `originating_sale_accrual_date`.

Each candidate may expose:

- product_id;
- historical cost evidence status;
- historical cost per unit;
- historical effective-from date;
- historical source;
- candidate value at historical cost.

Aggregate evidence exposes:

- historical cost candidate count;
- matched/missing/ambiguous/unavailable counts;
- candidate value at historical cost;
- `historical_cost_basis_confirmed`.

Aggregate historical cost basis is confirmed only when:

- sale-period lineage is confirmed;
- candidate records exist;
- every candidate resolves to exactly one valid historical cost version.

## Financial boundary

Historical cost confirmation does not prove that the returned unit restored saleable inventory value.

Therefore:

- `saleable_inventory_recovery_confirmed=False`;
- `period_cogs_recovery_confirmed=False`;
- `accounting_cogs_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`.

Period Profit formula is unchanged.

Accounting net-profit claim remains prohibited.

## Seller-facing behavior

Telegram may show:

- current-cost candidate value as diagnostic evidence;
- historical-cost candidate value when effective-dated evidence is complete;
- selected-period sale lineage state;
- remaining blocker: saleable/restored inventory recovery.

Historical candidate value is never added to profit by this package.

## Local evidence input

`record_product_cost_history.py` allows explicit seller-confirmed historical cost versions.

This is local persistence only.

It performs no Ozon mutation.

## SHA-bound verification

Entering exact docs-reconciled main:

- `212df575cc60a809032954d425902fad86623956`;
- Verify #1095;
- 2185 passed / 0 failed;
- artifact 9906001699;
- digest `sha256:a50fb08552d73f187bbacc608751655880f293578a7ac4408154808d82a16f79`.

No failed production SHA occurred.

Cancelled intermediate SHAs carry no transferable success evidence.

Final feature:

- `f3fcb80588f394eb05e5944ca2812ed59adf7649`;
- Verify #1103;
- 2195 passed / 0 failed;
- artifact 9906200014;
- digest `sha256:c776260a5026572cbe27c2bab5212d2a64d92d95f7a9170a433a2d5b12b46af7`.

PR integration:

- PR #393;
- synthetic SHA `672e18f904768742917df9c808c48ec476d9fd3e`;
- Verify #1104;
- 2195 passed / 0 failed;
- artifact 9906235551;
- digest `sha256:d849f4a6413df1de6c6b3e28ed4f5c45465b292266db2c31dbac3602251fcfb0`.

Squash main:

- `9ca4497dda61615076b8203d0404502630ab7e81`;
- Verify #1105;
- 2195 passed / 0 failed;
- artifact 9906262083;
- digest `sha256:6bc9ab6699976e56572a216dab839e96c8921f484047c522eb00535163626987`.

GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.

## Next production gap

The next material return COGS blocker is saleable/restored inventory recovery evidence.

A future package must distinguish:

- returned item restored to saleable inventory;
- non-saleable/disposed/lost outcome;
- unresolved state;
- compensated outcome.

Recovery and compensation must not be counted twice.

Until inventory recovery evidence is complete, automatic COGS reversal remains prohibited.

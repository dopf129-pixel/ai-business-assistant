# AI Assistant Project State

## Current product state

AI Business Assistant

## Product role

Read-only Ozon business analyst and advisor.

The assistant may read seller/business evidence, analyze it, compare periods, explain risks, rank priorities, recommend next steps, and prepare non-executable drafts/checklists.

The assistant must not mutate Ozon business state.

## Current verified checkpoint

Package:

`v1301-v1310: Originating Sale Quantity Evidence`

Goal:

Add explicit read-only evidence for originating FBO sale quantity behind Return COGS candidates without deriving quantity from money, stock deltas, or return-state assumptions.

Immediately preceding verified package:

`v1291-v1300: Return Inventory Recovery Evidence`

## Stable verification

Latest exact production main:

`e9b56773bd1dea7c4ac6b97f0c948d49f319bb51`

GitHub Actions push Verify #1150:

2218 passed / 0 failed.

## Seller-facing accounting progress

Period Profit V2 keeps Decision 037 account-level Ozon monetary authority.

Base formula remains:

`period_profit = account_net_accrual - product_cost - configured_tax`

External expense adjustment remains evidence-bound:

`profit_after_external_expenses = period_profit - external_expenses`

Return COGS evidence can now independently establish:

1. originating sale lineage in the selected period by positive Ozon sale accrual matched on `posting_number + SKU`;
2. effective-dated historical product cost for that matched sale date;
3. explicit return-level inventory recovery state from `return_inventory_recovery_history`;
4. originating FBO sale-quantity evidence from exact posting detail `products[].quantity` matched on `posting_number + SKU`.

For quantity evidence, all Return COGS candidates sharing the same `posting_number + SKU` consume one originating sale quantity budget. Aggregate candidate return quantity must not exceed the explicit FBO posting product quantity.

Missing SKU evidence remains unknown. Duplicate matching SKU rows are ambiguous rather than silently summed. Malformed/non-positive quantities remain unconfirmed. FBS quantity evidence is unsupported in this package and fails closed.

## Explicit evidence/accounting distinction

`originating_sale_quantity_evidence_confirmed=True` means the explicit FBO posting evidence is quantity-consistent for all candidates.

It does **not** mean the Return COGS accounting gate has been promoted.

In v1301-v1310:

- `originating_sale_quantity_confirmed=False`;
- `originating_sale_quantity_gate_promoted=False`;
- `recovery_period_attribution_confirmed=False`;
- `compensation_accounting_treatment_confirmed=False`;
- `period_cogs_recovery_confirmed=False`;
- `accounting_cogs_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0.0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`.

This prevents a source-evidence improvement from silently becoming accounting authorization.

## Production evidence

Entering exact docs-reconciled main:

- `9bceb0a9cedd5db2a42eef653f5822af21dd4cee`.

No failed production SHA occurred in v1301-v1310.

Final feature:

- `44b9cf3f0e794d7b17527fad8de5dc7ec3ae1e3b` / Verify #1148 / 2218 passed / 0 failed / artifact 9929146444 / digest `sha256:f104a0d1a0676b2252185dd52bb4ce47c591461ce1f5fde7e0be0571b2968ce2`.

PR integration:

- PR #397 synthetic `3299575f706866dc214d88f65ba18d6663f2743d` / Verify #1149 / 2218 passed / 0 failed / artifact 9929197649 / digest `sha256:4271c9cba87a6310c1e0cd1175aeaec6769f1f2837beb9b7e9698a92bb555dd7`.

Squash main:

- `e9b56773bd1dea7c4ac6b97f0c948d49f319bb51` / Verify #1150 / 2218 passed / 0 failed / artifact 9929225518 / digest `sha256:77b4c9c9e1a25cfb4a9bcc31ffec4076c542aa6f0204c30cdbd3a9221e5a6747`.

## Preserved boundaries

- Decision 036 read-only Ozon analyst boundary;
- Decision 037 account-level Ozon monetary authority;
- Decision 038 external operating expense coverage contract;
- Decision 039 versioned historical product cost evidence;
- Decision 040 explicit return inventory recovery evidence;
- no new architecture decision in v1301-v1310 because accounting semantics/persistence were not changed;
- no Period Profit formula change;
- no stock-delta inference;
- no monetary-to-quantity inference;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- no double subtraction;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Remaining path toward return COGS recovery

The next material blockers are explicit recovery accounting-period attribution and compensation accounting treatment/double-count prevention.

The newly proven sale-quantity source evidence must remain separate until those independent accounting facts are bound. Only a later explicit accounting contract may promote the quantity gate and determine whether any Return COGS recovery belongs in a selected Period Profit period.

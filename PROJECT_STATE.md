# AI Assistant Project State

## Current product state

AI Business Assistant

## Product role

Read-only Ozon business analyst and advisor.

The assistant may read seller/business evidence, analyze it, compare periods, explain risks, rank priorities, recommend next steps, and prepare non-executable drafts/checklists.

The assistant must not mutate Ozon business state.

## Current verified checkpoint

Package:

`v1251-v1260: Return COGS Recovery Evidence`

Goal:

Expose conservative evidence for potential return-related COGS recovery without increasing Period Profit from unsupported assumptions.

Immediately preceding verified package:

`v1241-v1250: Account-Level Ozon Profit Reconciliation`

## Stable verification

Latest exact production main:

`d845c7183ef5a914853a15b788e18b0cebfd1c93`

GitHub Actions push Verify #1040:

2161 passed / 0 failed.

## Seller-facing accounting progress

Period Profit V2 continues to use account-level Ozon accruals as monetary authority.

Return evidence now additionally preserves:

- product SKU / offer / quantity;
- return type;
- visual return status;
- compensation status;
- return logistics moments.

The new Return COGS Recovery Evidence classifies:

- customer-return units that reached return-place as candidate recovery;
- compensated units separately;
- unresolved return/recovery status separately;
- missing current product cost as unresolved rather than zero.

Candidate recovery value is shown only at current configured product cost.

It does **not** change profit.

## Explicit boundaries

The following remain unproven:

- historical cost basis of each returned unit;
- saleability / restored inventory value;
- originating sale belonging to the selected profit period;
- accounting treatment of compensation in the selected period.

Therefore:

- `confirmed_cogs_recovery_amount=0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- accounting net-profit claim remains prohibited.

## Production evidence

Entering exact docs-reconciled main:

- `55942648266e9ca4fbb3d3380180c3a67bfc4c56` / Verify #1022 / 2151 passed / 0 failed.

Failed intermediate:

- `2339d8aa8da1ec43c3298be2da8506a1e6dd8b9b` / Verify #1033 / 2159 passed / 2 failed.
- failures were test-contract issues only.

Final feature:

- `30f3edafd9d2af603f2277701cb13492a334dd30` / Verify #1038 / 2161 passed / 0 failed.

PR integration:

- PR #387 synthetic `c5947439450297dabb353b3dfd125e3fc6417576` / Verify #1039 / 2161 passed / 0 failed.

Squash main:

- `d845c7183ef5a914853a15b788e18b0cebfd1c93` / Verify #1040 / 2161 passed / 0 failed.

## Preserved boundaries

- Decision 036 read-only analyst boundary;
- Decision 037 account-level Ozon monetary authority;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- no profit formula change in this package;
- no automatic return COGS reversal;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Remaining path toward accounting net profit

The next material gap is seller/business expense evidence outside the Ozon account accrual stream:

- payroll / contractor costs;
- external packaging / fulfilment expenses not charged through Ozon;
- software / subscriptions;
- rent / accounting / services;
- other seller-configured operating expenses.

Those expenses must be explicit evidence, never inferred as zero.

# AI Assistant Project State

## Current product state

AI Business Assistant

## Product role

Read-only Ozon business analyst and advisor.

The assistant may read seller/business evidence, analyze it, compare periods, explain risks, rank priorities, recommend next steps, and prepare non-executable drafts/checklists.

The assistant must not mutate Ozon business state.

## Current verified checkpoint

Package:

`v1271-v1280: Return Sale-Period Lineage Evidence`

Goal:

Strengthen return COGS recovery evidence by proving whether a candidate return links to a positive sale accrual inside the selected Period Profit interval.

Immediately preceding verified package:

`v1261-v1270: External Operating Expense Coverage`

## Stable verification

Latest exact production main:

`5c0ed4bd40207e3f4bcce3770e89e71e163288b1`

GitHub Actions push Verify #1085:

2185 passed / 0 failed.

## Seller-facing accounting progress

Period Profit V2 still uses account-level Ozon daily finance as the monetary authority for Ozon money.

Base formula remains:

`period_profit = account_net_accrual - product_cost - configured_tax`

The external-expense layer remains evidence-bound:

`profit_after_external_expenses = period_profit - external_expenses`

only when seller expense coverage is explicit.

Return COGS evidence now adds selected-period sale lineage:

- positive sale postings are extracted from the same cached Ozon finance read session used by Period Profit;
- a Return API record is matched to sale evidence by `posting_number + SKU`;
- exactly one positive sale-accrual date inside the selected period is a matched lineage record;
- another SKU does not match;
- multiple positive sale dates are ambiguous;
- unavailable or malformed finance evidence leaves lineage partial/unavailable;
- incomplete return pagination prevents aggregate sale-period confirmation.

When every return-place COGS candidate in a complete return sample has a unique finance match and every finance day is complete, `originating_sale_period_confirmed=True`.

This is evidence only. It does not change profit.

## Explicit boundaries

Accounting net-profit claim remains prohibited.

Still not fully proven:

- historical COGS basis for returned units;
- saleable/restored inventory recovery after returns;
- originating sale quantity consistency as a separate accounting fact;
- compensation timing/accounting across periods;
- taxes/accounting adjustments outside configured tax policy;
- completeness of external expenses without explicit coverage.

Return COGS remains conservative:

- `confirmed_cogs_recovery_amount=0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- `historical_cost_basis_confirmed=False`;
- `saleable_inventory_recovery_confirmed=False`.

## Production evidence

Entering exact docs-reconciled main:

- `356fa301a9025e15a5a9fbb94da706d10670416a` / Verify #1074 / 2171 passed / 0 failed / artifact 9897945762 / digest `sha256:9b883028d77316bcabd7634b934f9ab38664a84468eab5622195ff73929c7653`.

Failed intermediate SHA remains failed evidence:

- `db2c6c0fa900720c303a8f8face32ef3eec3be11` / Verify #1081 / 2170 passed / 1 failed / artifact 9898277377 / digest `sha256:2e8365779ec323568d2be3649d17d7a79e8d5a5da745f128cc11555750cd7b2e`.

Failure cause:

factory regression test double still accepted only the former one-argument Return COGS evidence constructor.

Cancelled intermediate SHAs carry no transferable success evidence.

Final feature:

- `e96fb63007647857045f226c9c41fd8157ae962e` / Verify #1083 / 2185 passed / 0 failed / artifact 9898333361 / digest `sha256:7ac52123e97a821e6fb65fcc7dc15dfb61d68a8be6fd40c9598b7505a174c3f5`.

PR integration:

- PR #391 synthetic `26d6ca0e9b2ef2b4a358cc6a517bd13bf152bffc` / Verify #1084 / 2185 passed / 0 failed / artifact 9898386674 / digest `sha256:a4ac6ad8520a2a0726aff061f5f579a74742f868e17e2ced9d89ac84c3798d47`.

Squash main:

- `5c0ed4bd40207e3f4bcce3770e89e71e163288b1` / Verify #1085 / 2185 passed / 0 failed / artifact 9898420551 / digest `sha256:4a187e0b83b0b5950e64aaf749d31b78d7d5435132a77fde2e044667fe06b864`.

## Preserved boundaries

- Decision 036 permanent read-only Ozon analyst boundary;
- Decision 037 account-level Ozon monetary authority;
- Decision 038 external operating expense evidence/coverage contract;
- no profit-formula change;
- no persistence-contract change;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- no double subtraction of Ozon expenses;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Remaining path toward accounting net profit

The strongest remaining return COGS blockers are now:

1. historical product cost evidence applicable to the originating sale;
2. evidence that the returned unit restored saleable inventory value or another accounting-equivalent asset value;
3. compensation treatment without double counting.

Until those are proven, candidate return value never changes profit.

After return COGS, remaining accounting gaps include taxes/adjustments outside configured policy, recurring external-expense evidence where dated rows are insufficient, and any external-expense periods without explicit coverage.

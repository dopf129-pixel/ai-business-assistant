# CURRENT_CHECKPOINT_V1271_V1280

Date: 2026-09-03

## Return Sale-Period Lineage Evidence

Production package:

`v1271-v1280: Return Sale-Period Lineage Evidence`

Goal:

Reduce one of the explicit blockers for accounting-safe return COGS recovery by proving whether a candidate return links to a positive sale accrual inside the selected Period Profit interval.

## Monetary ownership

Decision 037 remains unchanged.

Ozon account-level daily finance remains the monetary authority.

Base Period Profit remains:

`period_profit = account_net_accrual - product_cost - configured_tax`

Decision 038 external-expense adjustment remains separate and unchanged.

This package does not modify either formula.

## Sale-lineage evidence

The package adds read-only positive-sale evidence from the existing Ozon daily finance read session.

Matching basis:

`OZON_POSTING_NUMBER_AND_SKU_POSITIVE_SALE_ACCRUAL`

A return COGS candidate may have selected-period lineage only when:

- Return API provides a posting number;
- Return API provides SKU;
- Ozon finance contains a positive POSTING sale accrual with the same posting number and SKU;
- the positive sale evidence resolves to exactly one accrual date inside the selected Period Profit interval.

Evidence semantics:

- same posting but different SKU does not match;
- no positive sale in the selected period stays unmatched;
- multiple positive sale dates stay ambiguous;
- malformed positive-sale records make the finance day partial;
- unavailable finance days make the lineage period partial;
- incomplete Returns pagination prevents aggregate sale-period confirmation.

The sale-lineage reader shares the exact `FinanceService` instance already used by Period Profit, preserving read-session caching and avoiding duplicate finance fetches for already loaded days.

## Return COGS integration

Candidate return records now expose:

- `originating_sale_lineage_status`;
- `originating_sale_accrual_date`.

Aggregate evidence exposes:

- `sale_lineage_evidence_available`;
- `sale_lineage_finance_period_complete`;
- candidate/matched/unmatched/ambiguous/unresolved record counts;
- `originating_sale_period_confirmed`.

Aggregate `originating_sale_period_confirmed=True` requires:

- complete Returns sample;
- complete finance period;
- at least one COGS candidate;
- every candidate linked to exactly one positive sale date inside the selected period.

## Financial boundary

Sale-period lineage alone is not enough for COGS reversal.

Still unconfirmed:

- historical cost basis applicable to the originating sale;
- saleable/restored inventory recovery;
- compensation accounting treatment across periods.

Therefore:

- `historical_cost_basis_confirmed=False`;
- `saleable_inventory_recovery_confirmed=False`;
- `period_cogs_recovery_confirmed=False`;
- `accounting_cogs_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`.

Accounting net-profit claim remains prohibited.

## Seller-facing behavior

Telegram Return COGS evidence can now say when selected-period sale lineage is confirmed for all candidate return records.

When lineage is confirmed, the explanation removes sale-period lineage from the remaining blockers.

It still states that candidate current-cost value is not added to profit because historical cost and saleable/restored inventory are unproven.

Partial/unavailable lineage is shown as incomplete evidence rather than converted to zero or false certainty.

## No architecture decision required

Decision 036 unchanged.

Decision 037 unchanged.

Decision 038 unchanged.

This package adds evidence and wiring only.

It does not change:

- financial formula ownership;
- persistence contract;
- execution authorization;
- product read-only boundary.

## SHA-bound verification

Entering exact docs-reconciled main:

- `356fa301a9025e15a5a9fbb94da706d10670416a`;
- Verify #1074;
- 2171 passed / 0 failed;
- artifact 9897945762;
- digest `sha256:9b883028d77316bcabd7634b934f9ab38664a84468eab5622195ff73929c7653`.

Failed intermediate evidence:

- `db2c6c0fa900720c303a8f8face32ef3eec3be11`;
- Verify #1081;
- 2170 passed / 1 failed;
- artifact 9898277377;
- digest `sha256:2e8365779ec323568d2be3649d17d7a79e8d5a5da745f128cc11555750cd7b2e`;
- cause: factory regression test double had not yet accepted the sale-lineage dependency.

Cancelled intermediate SHAs carry no transferable success evidence.

Final feature:

- `e96fb63007647857045f226c9c41fd8157ae962e`;
- Verify #1083;
- 2185 passed / 0 failed;
- artifact 9898333361;
- digest `sha256:7ac52123e97a821e6fb65fcc7dc15dfb61d68a8be6fd40c9598b7505a174c3f5`.

PR integration:

- PR #391;
- synthetic SHA `26d6ca0e9b2ef2b4a358cc6a517bd13bf152bffc`;
- Verify #1084;
- 2185 passed / 0 failed;
- artifact 9898386674;
- digest `sha256:a4ac6ad8520a2a0726aff061f5f579a74742f868e17e2ced9d89ac84c3798d47`.

Squash main:

- `5c0ed4bd40207e3f4bcce3770e89e71e163288b1`;
- Verify #1085;
- 2185 passed / 0 failed;
- artifact 9898420551;
- digest `sha256:4a187e0b83b0b5950e64aaf749d31b78d7d5435132a77fde2e044667fe06b864`.

Failed SHA evidence is not transferable.

GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.

## Next production gap

The next material accounting layer is historical product cost evidence.

Safe direction:

- version product cost evidence with explicit effective dates;
- never infer older historical cost from the current configured value;
- preserve unknown periods as unknown;
- separately investigate evidence that a returned unit restored saleable inventory or accounting-equivalent value.

Only after historical cost and recovery-state evidence are both proven should automatic return COGS reversal be reconsidered.

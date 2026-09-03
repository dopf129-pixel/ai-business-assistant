# Current Checkpoint v1291-v1300

Date: 2026-09-04

Package: Return Inventory Recovery Evidence

## Production baseline

Exact verified production main:

`3f82b65054a2a7a48b9918803c197377bdb3557f`

Post-merge Verify #1131:

- 2208 passed / 0 failed
- artifact id: 9906878610
- digest: `sha256:45eb967f32521ae3c7a2007663f6acfffcf6fa2f1fbdddb58bc332f56a02311d`

## Decision 040 — Explicit Return Inventory Recovery Evidence

Return inventory recovery is now represented by separate explicit append-only evidence.

Canonical rules:

- storage: `return_inventory_recovery_history`;
- every row requires exact Return API `return_id`, `posting_number`, SKU, positive quantity, explicit recovery state, confirmation date and source;
- supported recovery states are exactly `SALEABLE_RESTORED` and `NON_SALEABLE`;
- missing recovery evidence stays unknown and is never converted to saleable, non-saleable or zero;
- duplicate `return_id + confirmed_on` evidence is rejected;
- all versions for one `return_id` must preserve `posting_number + SKU`; identity drift is a conflict and remains unconfirmed;
- current Ozon stock observations and stock deltas are never automatic proof that returned inventory became saleable;
- latest explicit confirmation may describe the current known recovery state, but its date alone does not establish the accounting period for COGS recovery;
- evidence quantity must exactly match the candidate return quantity before saleable recovery can be confirmed;
- compensated returns remain outside automatic saleable-recovery candidacy.

Decision 036 permanent read-only Ozon analyst boundary remains unchanged.
Decision 037 account-level Ozon finance monetary authority remains unchanged.
Decision 038 external operating expense coverage remains unchanged.
Decision 039 historical product cost evidence remains unchanged.

## Return COGS evidence state

The production Return COGS evidence chain can now independently confirm:

1. originating sale period lineage;
2. effective historical product cost on the matched sale date;
3. explicit saleable/non-saleable inventory recovery state.

Aggregate `inventory_recovery_state_complete=True` requires a complete Returns sample and explicit recovery state for every COGS-recovery candidate.

Aggregate `saleable_inventory_recovery_confirmed=True` requires all candidate rows to be explicitly `SALEABLE_RESTORED` with exact identity and quantity match.

A confirmed saleable recovery still does **not** authorize a Period Profit adjustment.

The production accounting safety flags remain:

- `originating_sale_quantity_confirmed=False`
- `recovery_period_attribution_confirmed=False`
- `compensation_accounting_treatment_confirmed=False`
- `period_cogs_recovery_confirmed=False`
- `accounting_cogs_recovery_confirmed=False`
- `confirmed_cogs_recovery_amount=0.0`
- `profit_adjustment_allowed=False`
- `automatic_recovery_allowed=False`

Period Profit formula remains unchanged.
No stock-delta inference is used.
No double subtraction or automatic COGS recovery is enabled.
No Ozon mutation is enabled.
No Product Decision/Product Task Draft execution is enabled.
`data/users.json` is unchanged.
`externally_verified=False`.

## Verification evidence

### Entering exact main

- SHA `7f859d1073338c5c0144edea8fe15574460e5210`
- Verify #1115
- 2195 passed / 0 failed
- artifact 9906440691
- digest `sha256:42618c7cd0f12fdd9b1c49f2231c990c71c6931727af3a09e1035719f248929a`

### Failed intermediate SHAs

1. `41b409edcd2a96016bf49e8e8303a7aec00c1886`
   - Verify #1125
   - compile failure (`SyntaxError`)
   - no verification artifact
2. `4643126328c9e461712aae30f5f7a694a7549e89`
   - Verify #1126
   - compile failure at `app/period_profit_response.py:706`
   - no verification artifact
3. `d90549d21c8fb46b0a9012c205520c68e012dbfa`
   - Verify #1127
   - compile failure, unmatched `)` at `app/period_profit_response.py:744`
   - no verification artifact
4. `13e4cfbacf617bb60c5b897137b619f079c3d500`
   - Verify #1128
   - 2203 passed / 5 failed
   - artifact 9906768012
   - digest `sha256:59dd7f0d342951b258bdef1d45b934cd107a858fc986d9326d1f06df016c2944`
   - failure exposed a test-double identity mismatch; production keeps numeric Ozon Return API IDs

These failed SHAs remain failed evidence permanently.

### Final feature head

- SHA `1a83e5466bfebd79370e9576ce00b43b79bb668d`
- Verify #1129
- 2208 passed / 0 failed
- artifact 9906795648
- digest `sha256:a20b8f66b8d28365b7c9d887250782e7ab01d7885ddcca75c5bfab90541bd875`

### PR integration

- PR #395
- synthetic merge SHA `7d7b3a5e180a2505850345cc753a7d40ba391cbf`
- Verify #1130
- 2208 passed / 0 failed
- artifact 9906847145
- digest `sha256:36f7babc92f4f0d39e708927a61e95122eada8b76892dc4eb7da8912f3e01fa4`

### Squash production main

- SHA `3f82b65054a2a7a48b9918803c197377bdb3557f`
- Verify #1131
- 2208 passed / 0 failed
- artifact 9906878610
- digest `sha256:45eb967f32521ae3c7a2007663f6acfffcf6fa2f1fbdddb58bc332f56a02311d`

## Next material accounting gap

The next package must remain fail-closed and should address the remaining Return COGS accounting blockers without changing the permanent read-only Ozon boundary:

- exact recovery accounting-period attribution;
- originating sale quantity consistency against return quantity;
- compensation accounting treatment / double-count prevention.

Until those are explicitly proven, confirmed saleable inventory recovery remains evidence only and `confirmed_cogs_recovery_amount` stays zero.

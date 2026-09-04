# AI Assistant Project State

## Current product state

AI Business Assistant is a read-only Ozon business analyst and advisor. Ozon business mutations remain prohibited by Decision 036.

## Current verified checkpoint

Package: `v1311-v1320: Return COGS Accounting Attribution Evidence`

Exact production main: `defcab860609086fe2cd5df98000ca75fd173cee`

GitHub Actions push Verify #1160: 2228 passed / 0 failed.

## Period Profit accounting boundary

Decision 037 account-level Ozon finance remains the monetary authority.

Base formula remains unchanged:

`period_profit = account_net_accrual - product_cost - configured_tax`

External expense adjustment remains separately evidence-bound under Decision 038.

Return COGS evidence can now independently stage:

1. originating sale-period lineage;
2. effective-dated historical cost;
3. explicit saleable/non-saleable inventory recovery;
4. explicit FBO originating-sale quantity evidence;
5. explicit recovery accounting date;
6. explicit compensation accounting treatment and no-double-count evidence.

## v1311-v1320 accounting attribution contract

A new append-only `return_cogs_accounting_attribution_history` evidence table stores exact return identity (`return_id + posting_number + SKU`), dedicated `recovery_accounting_date`, explicit compensation state, explicit double-count clearance, confirmation date and source.

Allowed compensation states are:

- `NO_COMPENSATION_CONFIRMED`;
- `COMPENSATION_PRESENT`.

`confirmed_on` is provenance only and is never treated as the accounting recognition date.

Missing evidence remains unknown. Identity drift is conflicting evidence. Duplicate `return_id + confirmed_on` versions are rejected. Malformed accounting dates and non-boolean double-count markers fail closed.

The service may expose source-evidence markers such as:

- `recovery_period_attribution_evidence_confirmed`;
- `compensation_accounting_treatment_evidence_confirmed`;
- `compensation_double_count_clear`;
- `accounting_attribution_evidence_confirmed`.

These markers do not promote the established accounting gates in this package.

## Gates intentionally still closed

- `originating_sale_quantity_confirmed=False`;
- `originating_sale_quantity_gate_promoted=False`;
- `recovery_period_attribution_confirmed=False`;
- `compensation_accounting_treatment_confirmed=False`;
- `period_cogs_recovery_confirmed=False`;
- `accounting_cogs_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0.0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`.

## Production verification

No failed production SHA occurred in v1311-v1320.

- feature `8909eb222671039142f85b2182a914b7065732c1` — Verify #1158 — 2228 passed / 0 failed — artifact 9932424171 — digest `sha256:9cbc491d0456e5dc9e400eea51c056032a414dfe07aa2de557614da2dd4c6a8a`;
- PR #399 synthetic `ca3e98f2173d2d483eab48990317cc4de89e5523` — Verify #1159 — 2228 passed / 0 failed — artifact 9932457274 — digest `sha256:dd9e1e0d0f32d5eea0d02082687c78c28b1e3920c1cdb6f17fe832da07a7233c`;
- squash main `defcab860609086fe2cd5df98000ca75fd173cee` — Verify #1160 — 2228 passed / 0 failed — artifact 9932497883 — digest `sha256:17bbaa40dce658718fd7b59fcdde239a393759e8fcc5a150e7f0dfce3ce02d23`.

All three reports are SHA-bound, read-only evidence, with `ozon_mutation=false` and `business_execution=false`.

## Preserved boundaries

- Decisions 036-040 remain unchanged;
- Decision 041 records explicit Return COGS accounting-attribution persistence semantics;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- no Period Profit formula change;
- no automatic COGS recovery;
- no compensation inference from operational status absence;
- no accounting-date inference from inventory confirmation time;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Next accounting package

The next package may evaluate promotion of the independently proven quantity, recovery-period and compensation gates into one accounting readiness contract. Any promotion must remain fail-closed, must prevent compensation double counting, and must not produce a non-zero Period Profit adjustment until the complete recovery amount and recognition contract are explicit.

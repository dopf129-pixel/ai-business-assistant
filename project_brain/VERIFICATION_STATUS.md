# Verification Status

Date: 2026-09-04

## Latest verified product baseline

`defcab860609086fe2cd5df98000ca75fd173cee`

Latest merged production batch:

`v1311-v1320: Return COGS Accounting Attribution Evidence`

### Entering exact docs-reconciled main

- exact main: `bf4603fca9bd8618d88fc5f2ca3d5d305bea11ca`;
- no verification evidence is transferred from this predecessor to later revisions.

### Failed intermediate evidence

No failed production SHA occurred in v1311-v1320. Failed SHAs from earlier packages remain failed evidence permanently.

### Exact feature-head verification

- SHA: `8909eb222671039142f85b2182a914b7065732c1`;
- Verify #1158;
- 2228 passed / 0 failed;
- artifact 9932424171;
- digest `sha256:9cbc491d0456e5dc9e400eea51c056032a414dfe07aa2de557614da2dd4c6a8a`;
- SHA-bound report: `read_only_evidence=true`, `ozon_mutation=false`, `business_execution=false`.

### PR merge-ref integration verification

- PR #399;
- synthetic SHA: `ca3e98f2173d2d483eab48990317cc4de89e5523`;
- Verify #1159;
- 2228 passed / 0 failed;
- artifact 9932457274;
- digest `sha256:dd9e1e0d0f32d5eea0d02082687c78c28b1e3920c1cdb6f17fe832da07a7233c`;
- revision ref: `refs/pull/399/merge`.

### Post-merge exact-main verification

- exact main: `defcab860609086fe2cd5df98000ca75fd173cee`;
- Verify #1160;
- 2228 passed / 0 failed;
- artifact 9932497883;
- digest `sha256:17bbaa40dce658718fd7b59fcdde239a393759e8fcc5a150e7f0dfce3ce02d23`;
- revision ref: `refs/heads/main`.

## Current Return COGS accounting-attribution evidence boundary

v1311-v1320 adds explicit local append-only evidence for:

- `recovery_accounting_date`;
- compensation state (`NO_COMPENSATION_CONFIRMED` or `COMPENSATION_PRESENT`);
- explicit boolean double-count clearance;
- exact return/posting/SKU identity;
- separate confirmation provenance date.

The accounting recognition date is never inferred from `confirmed_on`, inventory recovery confirmation time, current stock, stock delta, return visual status or missing compensation fields.

Source-evidence markers may be true while the accounting gates remain false.

Still blocked:

- `originating_sale_quantity_confirmed=False`;
- `recovery_period_attribution_confirmed=False`;
- `compensation_accounting_treatment_confirmed=False`;
- `period_cogs_recovery_confirmed=False`;
- `accounting_cogs_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0.0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`.

Period Profit formula is unchanged. No Ozon mutation is authorized or performed.

## Verification policy

Exact branch push verification proves only that exact branch head. Pull-request verification proves only the synthetic merge ref recorded in the artifact. Every squash-main SHA requires its own exact push verification. Failed SHAs remain failed evidence permanently. Cancelled/pending SHAs carry no transferable success claim. Missing evidence remains unknown and is never interpreted as zero or clean. Workflow evidence is project CI evidence only; `externally_verified=False`.

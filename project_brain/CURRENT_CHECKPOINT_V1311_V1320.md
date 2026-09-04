# Current Checkpoint v1311-v1320

Date: 2026-09-04

Package: `Return COGS Accounting Attribution Evidence`

## Status

Production lifecycle complete and exact-main verified.

Exact production main: `defcab860609086fe2cd5df98000ca75fd173cee`

Verify #1160: 2228 passed / 0 failed.

## Entering baseline

Exact docs-reconciled predecessor: `bf4603fca9bd8618d88fc5f2ca3d5d305bea11ca`.

No verification evidence is transferred between revisions.

## Objective

Bind two previously independent unknowns for Return COGS candidates without enabling recovery:

1. dedicated accounting recognition date for inventory-value recovery;
2. explicit compensation accounting treatment and double-count clearance.

## Persistence contract

`return_cogs_accounting_attribution_history` is append-only evidence.

Every row requires:

- exact `return_id`;
- exact `posting_number`;
- exact `SKU`;
- dedicated `recovery_accounting_date`;
- compensation state;
- explicit boolean `compensation_double_count_clear`;
- `confirmed_on` provenance date;
- source.

Allowed compensation states:

- `NO_COMPENSATION_CONFIRMED`;
- `COMPENSATION_PRESENT`.

Duplicate `return_id + confirmed_on` versions are rejected. Identity drift across versions makes the evidence conflicting and unconfirmed.

`confirmed_on` never substitutes for `recovery_accounting_date`.

## Read-only evidence service

`PeriodProfitReturnCogsAccountingEvidenceService` wraps the existing quantity-evidence service and looks up explicit local accounting evidence per candidate.

It exposes whether every candidate has an explicit accounting date, whether that date belongs to the requested period, whether compensation treatment is explicit, and whether double counting is explicitly clear.

Missing, malformed, conflicting, or unavailable evidence remains unconfirmed.

## Deliberately unpromoted gates

Even when all new source evidence is confirmed:

- `originating_sale_quantity_confirmed=False`;
- `originating_sale_quantity_gate_promoted=False`;
- `recovery_period_attribution_confirmed=False`;
- `compensation_accounting_treatment_confirmed=False`;
- `period_cogs_recovery_confirmed=False`;
- `accounting_cogs_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0.0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`.

No Period Profit formula change occurs in this package.

## Production changes

Added:

- `app/services/return_cogs_accounting_attribution_repository.py`;
- `app/services/period_profit_return_cogs_accounting_evidence_service.py`;
- `tests/test_return_cogs_accounting_attribution_evidence_v1311_v1320.py`.

Updated:

- `app/period_profit_factory.py`;
- `tests/test_period_profit_factory.py`.

## Test map

- v1311: explicit accounting date + explicit no-compensation persisted and read;
- v1312: duplicate confirmation version rejected;
- v1313: identity drift and malformed accounting date fail closed;
- v1314: missing accounting evidence remains unknown;
- v1315: explicit accounting date inside requested period is staged as evidence;
- v1316: outside-period date is not promoted;
- v1317: confirmation timestamp never substitutes for accounting date;
- v1318: explicit no-compensation treatment establishes double-count clearance evidence;
- v1319: known compensation can remain not double-count-clear;
- v1320: repository failure is contained and cannot change profit.

Full suite: 2228 passed / 0 failed.

## Verification evidence

No failed production SHA occurred in v1311-v1320.

### Feature head

- SHA `8909eb222671039142f85b2182a914b7065732c1`;
- Verify #1158;
- 2228 passed / 0 failed;
- artifact 9932424171;
- digest `sha256:9cbc491d0456e5dc9e400eea51c056032a414dfe07aa2de557614da2dd4c6a8a`.

### PR synthetic integration

- PR #399;
- synthetic SHA `ca3e98f2173d2d483eab48990317cc4de89e5523`;
- Verify #1159;
- 2228 passed / 0 failed;
- artifact 9932457274;
- digest `sha256:dd9e1e0d0f32d5eea0d02082687c78c28b1e3920c1cdb6f17fe832da07a7233c`.

### Exact main

- SHA `defcab860609086fe2cd5df98000ca75fd173cee`;
- Verify #1160;
- 2228 passed / 0 failed;
- artifact 9932497883;
- digest `sha256:17bbaa40dce658718fd7b59fcdde239a393759e8fcc5a150e7f0dfce3ce02d23`.

Every artifact reports `read_only_evidence=true`, `ozon_mutation=false`, `business_execution=false`.

## Architecture

Decision 041 records the new append-only accounting-attribution evidence semantics. Decisions 036-040 remain unchanged.

## Next package

Evaluate a single fail-closed accounting readiness gate that consumes independently proven sale quantity, recognition-period attribution, compensation treatment/double-count clearance, historical cost and saleable inventory recovery. Keep the recovery amount and Period Profit adjustment at zero until that contract is separately explicit and verified.

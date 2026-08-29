# Period Profit Mapping Replacement Activation v1 — v144–v148

Date: 2026-08-29

Architecture Review Required: **Yes** — this batch completes the safety-critical activation lifecycle for a reviewed replacement mapping.

## Workflow

`v143 handoff → v144 canonical admin preview → v145 APPLY/REJECT → v146 guarded admin apply → v147 registry verification → v148 audit receipt`

No step bypasses the existing mapping admin contract.

## v144 — canonical activation preview

The v143 replacement handoff is converted back into the existing `PERIOD_PROFIT_MAPPING_ADMIN_PREVIEW_READY` contract by calling `admin_service.preview()` again. Scope, target revision, target mapping, and current active revision must still match the handoff.

This is read-only.

## v145 — explicit APPLY / REJECT

The workflow delegates to the existing `build_mapping_admin_decision()` contract. It adds only `expected_current_active_revision_id` so the later write can detect a stale decision.

`REJECT` never enables registry apply.

## v146 — guarded activation

Only an explicit `APPLY` decision can reach `admin_service.apply()`.

Immediately before apply, the workflow re-runs the existing admin preview and checks that the current active revision is still the one the human reviewed. If another activation happened meanwhile, the decision fails closed as stale.

The workflow validates that the applied revision and mapping are exactly the inactive replacement revision selected by the user.

## v147 — post-activation verification

After apply, the registry is read again. Verification requires:

- active revision equals the selected replacement revision;
- active mapping ID equals the selected replacement mapping ID;
- an ACTIVATE event exists for that revision.

No write is performed during verification.

## v148 — activation audit receipt

A read-only audit artifact records:

- scope;
- revision ID;
- mapping ID;
- explicit APPLY decision;
- registry verification;
- activation event count.

The audit explicitly keeps `automatic_activation=False`, `profit_adjustment_allowed=False`, `ozon_mutation=False`, and `executed=False`.

## Safety invariants

- no automatic activation;
- no activation on REJECT;
- no stale APPLY after active lineage changes;
- no automatic remap;
- no Ozon mutation;
- no profit adjustment or double counting;
- existing registry integrity checks remain authoritative;
- existing admin preview/decision/apply contracts remain the only activation mechanism.

## Tests

`tests/test_period_profit_mapping_replacement_activation_batch_v144_v148.py`

Coverage includes canonical preview restoration, REJECT behavior, explicit APPLY, stale-decision blocking, post-activation registry verification, audit generation, tampered handoff rejection, and target mismatch rejection.

# Product Decision Persistence Application Readiness v1

## Goal

Validate that an explicitly authorized v39 Product Decision persistence candidate is ready for a separate persistence application step without writing Product Decision history or mutating any stored state.

## Contract

`build_product_decision_persistence_application_readiness(authorization)` validates the complete authorization → eligibility → review → delta → preview lineage, requires `AUTHORIZE`, requires `decision_persistence_allowed=True`, rechecks all mutation/execution safety flags, restricts changed fields to `decision_type`, `priority`, `confidence`, and `reasons`, checks SKU identity, and verifies every authorized `after` value against the authorized preview decision.

## Success

Returns `PRODUCT_DECISION_PERSISTENCE_APPLICATION_READY` with:

- `decision_persistence_allowed=True`;
- `decision_persistence_application_ready=True`;
- `decision_persistence_application_started=False`;
- the exact authorized preview and reviewed change evidence.

Readiness is not application.

## Safety boundary

- no `history.record()` call;
- no storage write;
- `persistent=False`;
- `product_decision_mutated=False`;
- `product_decision_persisted=False`;
- no Ozon mutation;
- no legacy Action Executor;
- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

Targeted exact minimal-checkout pytest: `12 passed in 0.05s`.

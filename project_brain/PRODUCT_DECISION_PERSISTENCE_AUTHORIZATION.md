# Product Decision Persistence Authorization v1

## Goal

Allow an explicit AUTHORIZE / REJECT decision on top of v38 Product Decision persistence eligibility without performing persistence.

## Contract

`build_product_decision_persistence_authorization(eligibility, decision)` validates exact v38 eligibility lineage, requires technical eligibility and a still-closed persistence boundary, rechecks all safety flags, restricts authorized changed fields to `decision_type`, `priority`, `confidence`, and `reasons`, and checks reviewed preview SKU identity.

`AUTHORIZE` returns `PRODUCT_DECISION_PERSISTENCE_AUTHORIZED` with `decision_persistence_allowed=True`.

`REJECT` returns `PRODUCT_DECISION_PERSISTENCE_REJECTED` with `decision_persistence_allowed=False`.

Authorization is permission for a separate future persistence step, not persistence itself.

## Safety boundary

- `persistent=False`;
- `product_decision_mutated=False`;
- `product_decision_persisted=False`;
- no Product Decision history/storage write;
- no Ozon mutation;
- no legacy Action Executor;
- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

Targeted exact minimal-checkout pytest: `12 passed in 0.05s`.

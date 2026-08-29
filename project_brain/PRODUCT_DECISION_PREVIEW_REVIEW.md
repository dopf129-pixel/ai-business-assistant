# Product Decision Preview Review v1

## Goal

Allow an explicit ACCEPT / REJECT review of a changed v36 Product Decision preview delta without persisting or replacing the Product Decision.

## Contract

`build_product_decision_preview_review(delta, decision)` validates exact v36 delta lineage, requires a real changed decision, rechecks all safety flags, restricts reviewed fields to `decision_type`, `priority`, `confidence`, and `reasons`, validates change count/set, and checks current/preview SKU identity.

`ACCEPT` returns `PRODUCT_DECISION_PREVIEW_REVIEW_ACCEPTED`; `REJECT` returns `PRODUCT_DECISION_PREVIEW_REVIEW_REJECTED`.

An unchanged delta is blocked because no new decision change requires review.

## Safety boundary

Review acceptance is not persistence authorization:

- `persistent=False`;
- `decision_persistence_allowed=False`;
- `product_decision_mutated=False`;
- `product_decision_persisted=False`;
- no Product Decision history write;
- no Ozon mutation;
- no legacy Action Executor;
- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

Targeted exact minimal-checkout pytest: `10 passed in 0.05s`.

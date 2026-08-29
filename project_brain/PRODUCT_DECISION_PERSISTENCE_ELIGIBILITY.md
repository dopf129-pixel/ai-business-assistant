# Product Decision Persistence Eligibility v1

## Goal

Determine whether an explicitly accepted v37 Product Decision preview review is technically eligible to proceed to a separate persistence review step, without persisting or replacing the Product Decision.

## Contract

`build_product_decision_persistence_eligibility(review)` validates exact v37 review lineage, requires `ACCEPT`, rechecks all persistence/execution safety boundaries, restricts reviewed changes to `decision_type`, `priority`, `confidence`, and `reasons`, checks SKU identity, and verifies every reviewed change `after` value against the reviewed preview decision.

## Success

Returns `PRODUCT_DECISION_PERSISTENCE_ELIGIBLE` with:

- `decision_persistence_eligible=True`;
- `decision_persistence_review_required=True`;
- `decision_persistence_allowed=False`;
- copied eligible preview decision and reviewed delta evidence.

Eligibility is not persistence authorization.

## Safety boundary

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

Targeted exact minimal-checkout pytest: `11 passed in 0.04s`.

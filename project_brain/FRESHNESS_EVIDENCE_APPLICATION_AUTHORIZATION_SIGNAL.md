# Freshness Evidence Application Authorization Signal v1

## Goal

Add an explicit human/system decision signal after the application authorization contract without starting evidence application.

## Contract

Input:
- v24 application authorization contract
- decision: `AUTHORIZE` or `REJECT`

Output on authorize:
- `status=APPLICATION_AUTHORIZATION_GRANTED`
- `authorization_granted=True`
- deterministic authorization signal id
- exact whitelisted evidence copied from the authorization contract

Output on reject:
- `status=APPLICATION_AUTHORIZATION_REJECTED`
- `authorization_rejected=True`

## Safety boundary

Authorization is still not application permission.

Always remains false:
- `application_allowed`
- `application_started`
- `persistent`
- `product_decision_recomputed`
- `product_decision_mutated`
- `task_draft_mutated`
- `execution_allowed`
- `execution_ready`
- `executed`

The signal makes no Ozon call, performs no persistence and does not connect to the legacy Action Executor.

## Validation

The contract re-binds request, approval, prior signal, eligibility, preview and authorization identifiers; re-whitelists evidence; verifies evidence count; requires v24 freshness/review validation; and rejects any pre-existing application/execution boundary violation.

Targeted tests after semantic hardening: `10 passed in 0.04s`.

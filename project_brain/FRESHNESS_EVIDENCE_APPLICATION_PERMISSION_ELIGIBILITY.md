# Freshness Evidence Application Permission Eligibility v1

## Goal

Consume a granted v25 application authorization signal and determine whether it is eligible for a separate application-permission review.

## Contract

A valid granted authorization signal produces:
- `status=APPLICATION_PERMISSION_REVIEW_REQUIRED`
- `permission_eligible=True`
- `permission_review_required=True`
- `permission_granted=False`
- deterministic `permission_eligibility_id`
- exact re-whitelisted evidence as `permission_evidence`

Eligibility is not permission.

## Safety boundary

Always remains false:
- `permission_granted`
- `application_allowed`
- `application_started`
- `persistent`
- `product_decision_recomputed`
- `product_decision_mutated`
- `task_draft_mutated`
- `execution_allowed`
- `execution_ready`
- `executed`

The contract performs no persistence, Ozon mutation, draft mutation, Product Decision recomputation or legacy Action Executor call.

## Validation

The contract verifies the complete request → approval → approval signal → eligibility → preview → authorization → authorization signal lineage. It requires `APPLICATION_AUTHORIZATION_GRANTED`, exact `AUTHORIZE`, a ready signal, safe boundaries, exact evidence count and an independent evidence allowlist.

Validation during implementation: 10/10 targeted assistant-side behavioral checks passed.

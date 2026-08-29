# Freshness Evidence Application Permission Signal v1

## Goal

Consume the v26 permission-review eligibility contract and record an explicit `GRANT` or `REJECT` decision without applying freshness evidence.

## Contract

A valid `GRANT` decision produces:
- `status=APPLICATION_PERMISSION_GRANTED`
- `permission_signal_ready=True`
- `permission_granted=True`
- deterministic `permission_signal_id`
- exact re-whitelisted `permission_evidence`

A valid `REJECT` decision produces:
- `status=APPLICATION_PERMISSION_REJECTED`
- `permission_rejected=True`

Permission decision is still not evidence application.

## Safety boundary

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

The contract performs no persistence, Ozon mutation, draft mutation, Product Decision recomputation, or legacy Action Executor call.

## Validation

The contract verifies the complete request → approval → approval signal → eligibility → preview → authorization → authorization signal → permission eligibility lineage. It independently re-whitelists evidence, verifies evidence count, rejects pre-decided permission, and rejects any application, persistence, freshness, Product Decision, or execution boundary violation.

Targeted exact minimal-checkout pytest: `11 passed in 0.04s`.

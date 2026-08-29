# Freshness Evidence Application Readiness v1

## Goal

Consume the v27 granted permission signal and determine whether the evidence workflow is ready for a separate future application step.

## Contract

A valid granted permission signal produces:
- `status=APPLICATION_READY_FOR_SEPARATE_STEP`
- `application_ready=True`
- `application_review_complete=True`
- deterministic `application_readiness_id`
- exact re-whitelisted evidence as `readiness_evidence`

Readiness is not application permission and is not application execution.

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

The contract verifies the full request → approval → approval signal → eligibility → preview → authorization → authorization signal → permission eligibility → permission signal lineage. It requires an exact `GRANT`, a ready permission signal, safe boundaries, exact evidence count, and an independent evidence allowlist.

Targeted exact minimal-checkout pytest: `11 passed in 0.04s`.

## Boundary after v28

This is the final pure readiness layer before real evidence application. Any subsequent step that persists evidence, mutates the task draft, recomputes Product Decisions, calls a mutating Ozon API, or enables execution requires a separate business/safety decision.
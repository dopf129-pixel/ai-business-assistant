# Freshness Evidence Application Preview v1

Date: 2026-08-29

## Goal

Preview the effect of v22 approved evidence on a Product Task Draft without persisting or mutating the real draft.

## Contract

`build_freshness_evidence_application_preview(draft, eligibility, freshness_service, readiness_service)`:

- deep-copies draft and eligibility inputs;
- validates draft/SKU/request/approval/signal/eligibility identity bindings;
- accepts only `ELIGIBLE_FOR_APPLICATION_REVIEW` input;
- independently re-checks all non-application and non-execution safety flags;
- re-whitelists approved freshness evidence;
- requires exact approved evidence count;
- applies evidence only to an in-memory draft copy;
- evaluates freshness before and after;
- evaluates readiness before and after.

## Identity bindings

Required:

- `request_id == refresh:<draft_id>`;
- `approval_id == evidence-approval:<draft_id>`;
- `signal_id == evidence-signal:<approval_id>`;
- `eligibility_id == evidence-eligibility:<signal_id>`;
- draft and eligibility SKU must match.

## Evidence boundary

Only these fields can be preview-applied:

- `sales_source_recorded_at`;
- `sales_observed_at`;
- `stock_source_recorded_at`;
- `stock_observed_at`;
- `unit_economics_source_recorded_at`;
- `unit_economics_observed_at`.

Observation-only evidence never becomes source freshness proof by itself.

## Preview semantics

A successful result returns `APPLICATION_PREVIEW_READY` and reports:

- `before_freshness`;
- `after_freshness`;
- `before_readiness`;
- `after_readiness`;
- `applied_evidence`.

This is hypothetical state only.

Even when the preview becomes fresh/review-ready:

- `application_allowed=False`;
- `application_started=False`;
- `source_freshness_proven=False`;
- `persistent=False`;
- `product_decision_recomputed=False`;
- `product_decision_mutated=False`;
- `task_draft_mutated=False`;
- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

No Ozon call, persistence operation, Product Decision recomputation, task-draft mutation, or legacy Action Executor call is performed.

## Validation

Focused tests: `tests/test_product_task_freshness_evidence_application_preview.py`.

Targeted assistant-side pytest after safety hardening: `10 passed in 0.04s`.

The full repository suite was intentionally not rerun for this isolated additive block.

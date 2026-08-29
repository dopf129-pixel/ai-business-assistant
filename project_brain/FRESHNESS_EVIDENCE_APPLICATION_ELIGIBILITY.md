# Freshness Evidence Application Eligibility v1

Date: 2026-08-29

## Goal

Determine whether a v21 explicit `APPROVED` evidence signal is eligible to enter a future evidence-application review step without applying evidence, persisting state, mutating Product Decisions, or enabling business execution.

## Contract

`build_freshness_evidence_application_eligibility(approval_contract, approval_signal)` consumes the v20 approval contract and v21 approval signal.

It returns `ELIGIBLE_FOR_APPLICATION_REVIEW` only after re-validating both inputs rather than trusting upstream flags blindly.

## Identity requirements

The contract and signal must contain matching non-empty:

- `approval_id`;
- `request_id`;
- `draft_id`;
- `sku`.

Additional bindings are required:

- `approval_id == evidence-approval:<draft_id>`;
- `signal_id == evidence-signal:<approval_id>`.

Any missing or mismatched identity produces `APPLICATION_INELIGIBLE`.

## Approval requirements

The v20 approval contract must still be:

- `status=APPROVAL_REQUIRED`;
- `approval_ready=True`;
- `approval_required=True`;
- `approval_granted=False`;
- `freshness_guard_validated=True`;
- `preview_freshness_status=FRESH`;
- `application_allowed=False`.

The v21 signal must be:

- `status=APPROVED`;
- `decision=APPROVE`;
- `signal_ready=True`;
- `approval_granted=True`;
- `approval_rejected=False`;
- `application_allowed=False`;
- `application_started=False`.

A rejected or conflicting signal is never eligible.

## Evidence safety

Both contract and signal evidence are independently re-whitelisted to:

- `sales_source_recorded_at`;
- `sales_observed_at`;
- `stock_source_recorded_at`;
- `stock_observed_at`;
- `unit_economics_source_recorded_at`;
- `unit_economics_observed_at`.

The two evidence dictionaries must be non-empty, contain no extra fields, and match exactly.

## Boundary semantics

`application_eligible=True` means only that the evidence may enter a separate future application-review boundary.

It explicitly does not mean application permission.

Even for an eligible result:

- `application_review_required=True`;
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

Focused tests: `tests/test_product_task_freshness_evidence_application_eligibility.py`.

Targeted assistant-side pytest after safety hardening: `10 passed in 0.05s`.

The full repository suite was intentionally not rerun for this isolated additive contract under the reduced full-suite cadence.

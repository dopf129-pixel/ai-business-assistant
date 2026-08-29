# Freshness Evidence Approval Signal v1

Date: 2026-08-29

## Goal

Capture an explicit `APPROVE` or `REJECT` decision for a v20 freshness evidence approval contract without applying evidence, mutating Product Decisions, or enabling business execution.

## Contract

`build_freshness_evidence_approval_signal(approval_contract, decision)` accepts only `APPROVE` or `REJECT` after normalization.

The approval contract must contain complete context:

- `approval_id`;
- `request_id`;
- `draft_id`;
- `sku`.

It must also remain in the expected v20 state:

- `status=APPROVAL_REQUIRED`;
- `approval_ready=True`;
- `approval_required=True`;
- `freshness_guard_validated=True`;
- `preview_freshness_status=FRESH`;
- `application_allowed=False`;
- non-empty `validated_evidence`.

## Decision semantics

`APPROVE` returns an `APPROVED` signal with `approval_granted=True`.

`REJECT` returns a `REJECTED` signal with `approval_rejected=True`.

An approval signal is evidence of the explicit decision only. It is not an evidence-application permission or a Product Decision execution permission.

## Safety invariants

Even for `APPROVED`:

- `application_allowed=False`;
- `application_started=False`;
- `persistent=False`;
- `source_freshness_proven=False`;
- `product_decision_recomputed=False`;
- `product_decision_mutated=False`;
- `task_draft_mutated=False`;
- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

No Ozon calls are performed by this contract.

## Validation

Focused tests: `tests/test_product_task_freshness_evidence_approval_signal.py`.

Targeted assistant-side pytest: `7 passed in 0.04s`.

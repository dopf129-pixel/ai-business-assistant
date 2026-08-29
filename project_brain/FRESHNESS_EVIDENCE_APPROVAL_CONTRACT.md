# Freshness Evidence Application Approval Contract v1

Date: 2026-08-29

## Goal

Create an approval-ready object only after a freshness evidence candidate has passed the read-only validation preview. The contract does not grant approval and does not apply evidence.

## Inputs

`build_freshness_evidence_approval_contract(draft, evidence_candidate, validation_preview)` consumes:

- the current task draft identity;
- the v18 evidence-update candidate;
- the v19 validation preview.

## Approval readiness requirements

The contract returns `APPROVAL_REQUIRED` only when all of the following are true:

- `draft_id` is present and exactly matches draft, candidate, and preview;
- `sku` is present and exactly matches draft, candidate, and preview;
- candidate and preview both contain the same non-empty `request_id`;
- preview status is `PREVIEW_READY`;
- `preview_only=True`;
- `preview_freshness_validated=True`;
- `preview_freshness_status` is exactly `FRESH`;
- candidate evidence is non-empty;
- whitelisted candidate evidence exactly matches the evidence that the preview validated.

Any mismatch, missing identity, stale/unknown preview status, or forged validation combination returns `APPROVAL_BLOCKED`.

## Approved evidence surface

Only these fields can appear in `validated_evidence`:

- `sales_source_recorded_at`;
- `sales_observed_at`;
- `stock_source_recorded_at`;
- `stock_observed_at`;
- `unit_economics_source_recorded_at`;
- `unit_economics_observed_at`.

Unexpected lifecycle, cache, request, execution, or other fields are ignored.

## Approval semantics

`APPROVAL_REQUIRED` means the evidence is eligible to be presented for an explicit approval step. It does not mean approval has been granted.

The contract always returns:

- `approval_required=True` only for approval-ready evidence;
- `approval_granted=False`;
- `application_allowed=False`;
- `source_freshness_proven=False` because evidence is still not persisted;
- `persistent=False`.

## Safety invariants

- no persistence;
- no Ozon calls;
- no Product Decision recompute or mutation;
- no task-draft mutation;
- no legacy Action Executor connection;
- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

A future explicit approval workflow may consume this contract, but it must remain separate from Product Decision execution.

## Validation

Focused tests: `tests/test_product_task_freshness_evidence_approval_contract.py`.

Targeted assistant-side pytest after identity and forged-preview safety review: `9 passed in 0.05s`.

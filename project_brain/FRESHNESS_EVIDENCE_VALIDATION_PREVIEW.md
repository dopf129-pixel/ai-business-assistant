# Freshness Evidence Validation Preview v1

Date: 2026-08-29

## Goal

Validate a freshness evidence candidate against the existing `ProductTaskDraftFreshnessService` without mutating the Product Decision, task draft, or execution state.

## Contract

`build_freshness_evidence_validation_preview(draft, evidence_candidate, freshness_service)`:

- deep-copies the input draft and candidate;
- evaluates freshness before the candidate;
- applies only whitelisted freshness evidence fields to the copy;
- evaluates freshness after the hypothetical update with the existing freshness guard;
- reports overall and component-level status changes;
- does not persist or apply the candidate.

## Allowed preview evidence

Only these fields can be applied to the preview copy:

- `sales_source_recorded_at`;
- `sales_observed_at`;
- `stock_source_recorded_at`;
- `stock_observed_at`;
- `unit_economics_source_recorded_at`;
- `unit_economics_observed_at`.

Unexpected candidate fields are ignored.

## Freshness semantics

The existing freshness guard remains authoritative.

A candidate source timestamp may preview as:

- `FRESH` when valid and within the configured age limit;
- `STALE` when older than the configured limit;
- `UNKNOWN` when missing, invalid, or in the future.

Observation-only evidence does not change source freshness status.

The preview exposes:

- `preview_freshness_status`;
- `preview_freshness_validated` when the copied draft evaluates to `FRESH`;
- `before` and `after` guard results;
- component-level changes.

`source_freshness_proven` intentionally remains `False` because the candidate has not been applied to persisted state. The preview proves only what the guard would report for the hypothetical copy.

## Safety invariants

- `preview_only=True`;
- `persistent=False`;
- `product_decision_recomputed=False`;
- `product_decision_mutated=False`;
- `task_draft_mutated=False`;
- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

No Ozon calls are performed by this contract.

## Validation

Focused tests: `tests/test_product_task_freshness_evidence_validation_preview.py`.

Targeted assistant-side pytest: `6 passed in 0.05s`.

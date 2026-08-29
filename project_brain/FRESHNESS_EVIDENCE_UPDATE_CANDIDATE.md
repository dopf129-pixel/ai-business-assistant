# Freshness Evidence Update Candidate v1

Date: 2026-08-29

## Goal

Normalize read-only refresh results into a candidate evidence update without mutating Product Decisions, task drafts, or execution state.

## Input

The contract consumes the result of `execute_read_only_refresh()` from Autonomous Assistant v17.

## Canonical evidence mapping

Only explicit freshness evidence fields are eligible:

- sales: `sales_source_recorded_at`, `sales_observed_at`;
- stock: `stock_source_recorded_at`, `stock_observed_at`;
- unit economics: `unit_economics_source_recorded_at`, `unit_economics_observed_at`.

For unit economics, existing `as_of` is accepted only as the observation alias for `unit_economics_observed_at`.

## Timestamp safety

The candidate builder does not promote these fields to source freshness evidence:

- `cached_at`;
- `created_at`;
- `updated_at`;
- request/orchestration time;
- draft or confirmation time;
- analytics period boundaries;
- unit-economics `as_of`.

A source-evidence candidate exists only when the matching canonical `*_source_recorded_at` field is explicitly present in refreshed data.

Presence alone does not prove freshness. The timestamp may still be invalid, future-dated, or stale. Only the existing `ProductTaskDraftFreshnessService` may validate the timestamp after a separately reviewed evidence-application step.

## Output

`build_freshness_evidence_candidate()` returns:

- component-level evidence candidates;
- flattened `evidence_update` candidate fields;
- counts for source and observation evidence;
- `source_evidence_candidate_present` when canonical source evidence exists;
- `requires_freshness_guard_validation=True` when source evidence must later be validated;
- `source_freshness_proven=False` in all cases at this stage.

The candidate is not applied to a Product Decision or task draft and does not bypass the freshness guard.

## Safety invariants

- `persistent=False`;
- `product_decision_recomputed=False`;
- `product_decision_mutated=False`;
- `task_draft_mutated=False`;
- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

No Ozon call is performed by this contract.

## Validation

Focused tests: `tests/test_product_task_freshness_evidence_candidate.py`.

Targeted assistant-side pytest after safety review: `5 passed in 0.05s`.

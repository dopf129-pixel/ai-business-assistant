# Freshness Coverage Summary v1

Date: 2026-08-29

## Goal

Make the freshness guard explainable without weakening it.

The system already distinguishes source-recorded timestamps from application observation timestamps. This change exposes that distinction as a compact coverage summary for Product Task Draft readiness and Telegram presentation.

## Evidence states

For each freshness-relevant component required by the current proposal:

- `SOURCE_PROVEN` — a non-empty `*_source_recorded_at` value exists. This is the only evidence class that can prove source freshness.
- `OBSERVED_ONLY` — no source-recorded timestamp exists, but a non-empty `*_observed_at` value exists. This is diagnostic metadata only.
- `NO_EVIDENCE` — neither source-recorded nor observed timestamp is available.

Components:

- sales: `sales_source_recorded_at` / `sales_observed_at`
- stock: `stock_source_recorded_at` / `stock_observed_at`
- unit economics: `unit_economics_source_recorded_at` / `unit_economics_observed_at`

## Readiness contract

`ProductTaskDraftReadinessService.evaluate()` now returns `freshness_coverage` when a freshness service is connected.

The coverage object contains:

- per-component freshness status and evidence state;
- source and observation timestamps as received;
- counts for `SOURCE_PROVEN`, `OBSERVED_ONLY`, and `NO_EVIDENCE`.

`ProductTaskDraftReadinessService.summarize()` aggregates those component counts across drafts as `freshness_coverage_counts`.

Coverage is explanatory only. Existing review readiness continues to depend on the actual freshness guard result, not on observation metadata.

## Telegram presentation

The task-draft queue can show aggregate evidence coverage counts.

The task-draft detail view can show the evidence state for each freshness-relevant component, for example:

- Sales: observation only
- Stock: no timestamp evidence
- Unit economics: source proven

Telegram remains a presentation boundary. It does not calculate freshness or change readiness.

## Safety invariants

This change does not:

- convert `*_observed_at` into `*_source_recorded_at`;
- treat analytics period end, request time, cache time, decision time, draft time, or confirmation time as source freshness evidence;
- change Product Business Decision rules;
- enable Product Decision execution;
- connect the legacy Action Executor;
- call mutating Ozon APIs;
- modify `data/users.json` or other runtime data files.

`execution_ready` remains `False` and `executed` remains `False`.

## Validation

Focused regression tests were added in `tests/test_product_task_freshness_coverage.py`.

Validation status: pending local/CI execution.

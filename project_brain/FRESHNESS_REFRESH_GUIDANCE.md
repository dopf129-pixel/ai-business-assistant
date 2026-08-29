# Freshness Refresh Guidance v1

Date: 2026-08-29

## Goal

Turn freshness blockers into explicit next-step guidance without automatically refreshing data or enabling execution.

The existing freshness guard remains authoritative. Guidance is derived from the guard result plus the evidence coverage contract.

## Guidance actions

For each freshness-relevant component required by the current proposal:

- `SOURCE_TIMESTAMP_REQUIRED` — freshness is unknown and no usable source-recorded timestamp exists. Observation metadata may exist, but it cannot prove source freshness.
- `VERIFY_SOURCE_TIMESTAMP` — a source timestamp is present but the guard still reports `UNKNOWN`, for example because the timestamp is in the future or otherwise cannot be trusted.
- `REFRESH_SOURCE_DATA` — a real source timestamp exists and the corresponding source data is stale.

Fresh components produce no guidance target.

## Readiness contract

`ProductTaskDraftReadinessService.evaluate()` returns `freshness_refresh_guidance` when a freshness service is connected.

The object contains:

- `required` — whether any freshness action is needed;
- `targets` — component-specific guidance with action, freshness status, evidence state, and original guard reasons;
- aggregate counts by guidance action;
- `execution_ready=False` and `executed=False`.

`ProductTaskDraftReadinessService.summarize()` aggregates guidance actions across drafts as `freshness_refresh_counts`.

## Telegram presentation

Task-draft queue summary can show how many components need:

- a trustworthy source timestamp;
- source timestamp verification;
- source data refresh.

Task-draft detail shows the required action for each affected component.

These are explanatory instructions only. No refresh button or execution callback is introduced.

## Source audit context

The current Ozon client returns stock and price response JSON without stripping source fields, but the used stock and price contracts currently expose no reliable source-recorded timestamp in the application pipeline.

Therefore observation timestamps continue to be diagnostic only and unsupported source freshness remains `UNKNOWN`.

## Safety invariants

This change does not:

- generate or infer `*_source_recorded_at`;
- treat observation, request, cache, analytics-period, decision, draft, or confirmation time as source freshness evidence;
- call Ozon to refresh data automatically;
- mutate Product Decisions or task drafts as part of guidance;
- change Product Business Decision thresholds;
- enable Product Decision execution;
- connect the legacy Action Executor;
- call mutating Ozon APIs;
- modify runtime data files.

## Validation

Focused regression tests: `tests/test_product_task_freshness_refresh_guidance.py`.

Targeted local validation: `5 passed in 0.05s`.

The assistant executed the focused suite in a minimal local checkout containing the exact changed readiness service, Telegram adapter, freshness-service dependency, and focused test file. Full repository regression was intentionally not rerun for this isolated additive block.

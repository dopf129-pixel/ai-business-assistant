# Source Provenance Passthrough v218-v224

## Goal

Preserve real freshness source timestamps when an immediate upstream contract explicitly supplies the exact domain field, without promoting observation, request, cache, period, decision, or generic timestamps.

## Stages

### v218 — Sales exact provenance

`ProductDecisionMetricsSource` preserves `sales_source_recorded_at` only when the current sales/finance result explicitly contains that exact field.

### v219 — Sales alias rejection

Generic fields such as `recorded_at`, period boundaries, or observation timestamps are not promoted to `sales_source_recorded_at`.

### v220 — Stock exact provenance

The stock preparation boundary preserves `stock_source_recorded_at` when `MetricsService` (or a compatible injected implementation) explicitly exposes that exact field at the result or metrics level.

Current production `MetricsService` does not generate this field, so current stock source freshness remains unsupported/UNKNOWN.

### v221 — Unit economics exact provenance

`ProductUnitEconomicsProvider.build_current` now preserves:

- `unit_economics_source_recorded_at`;
- `unit_economics_observed_at`;

only when those exact fields are supplied in prepared facts.

The provider does not promote generic `source_recorded_at` or `as_of` into source freshness. Existing query logic may continue to treat `as_of` as observation time only.

### v222 — Missing evidence remains absent

If upstream contracts do not provide source evidence, no source field is created.

This remains the expected state for current Ozon stock and sales paths unless their upstream contracts are extended with trustworthy source-recorded timestamps.

### v223 — Malformed evidence fails closed

Passthrough is lossless, not a freshness validator. A malformed explicit timestamp is carried as evidence and the downstream freshness evaluator classifies it as UNKNOWN.

No malformed value can enable execution.

### v224 — Freshness semantics remain separate from execution

A recent valid source timestamp may make the required freshness component FRESH.

It still does not set:

- `execution_ready`;
- `execution_allowed`;
- `executed`.

## Exact-field policy

Allowed pass-through fields in this change:

- `sales_source_recorded_at`;
- `stock_source_recorded_at`;
- `unit_economics_source_recorded_at`;
- `unit_economics_observed_at`.

No fuzzy matching, alias inference, timestamp synthesis, or clock substitution is permitted.

## Current production truth

This change closes a propagation gap. It does not claim that the current Ozon APIs used by the project already provide reliable source-recorded timestamps.

Current known behavior remains:

- sales: analytical period + application observation exist; source-recorded timestamp is not currently produced;
- stock: application observation exists; source-recorded timestamp is not currently produced;
- unit economics: application `as_of` is observation time only unless a separate exact source timestamp is supplied.

Therefore unsupported components remain UNKNOWN.

## Safety invariants

- no automatic refresh;
- no task-draft mutation;
- no Product Decision rule changes;
- no Product Decision recomputation;
- no Action Executor connection;
- no Ozon mutation;
- no business execution permission;
- `execution_ready=False`;
- `execution_allowed=False`;
- `executed=False`.

## Validation

Focused regression coverage is in:

`tests/test_product_source_provenance_passthrough_v218_v224.py`

Full repository suite is not claimed as run in the connector-only environment.

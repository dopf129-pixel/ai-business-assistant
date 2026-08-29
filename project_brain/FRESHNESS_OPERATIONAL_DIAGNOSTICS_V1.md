# Freshness Operational Diagnostics v1 — v204–v210

Date: 2026-08-30

Architecture Review Required: **Yes** — this extends the runtime-facing read-only freshness boundary.

## Goal

Make the freshness operational route diagnosable without inventing a canonical audit store or enabling mutation. The previous runtime collapsed reader capability errors, reader exceptions and malformed artifacts into a single unavailable result. This batch separates those states while preserving fail-closed semantics.

## v204 — reader capability inspection

`inspect_freshness_reader_capabilities(reader)` checks only the four explicit read methods required by the snapshot provider:

- `get_preparation_audit`
- `get_executor_admission_audit`
- `get_write_protocol_audit`
- `get_adapter_boundary_audit`

No discovery fallback or fuzzy method matching is allowed.

## v205 — per-artifact acquisition diagnostics

`collect_freshness_snapshot_diagnostics(reader)` reports each artifact independently as:

- `AVAILABLE`
- `MISSING`
- `CAPABILITY_MISSING`
- `READ_ERROR`
- `MALFORMED`
- `SAFETY_VIOLATION`

Missing lifecycle evidence is distinct from a broken reader. Reader exceptions are not exposed as arbitrary exception text.

## v206 — safe snapshot projection

Diagnostics include a deep-copied snapshot for read-only inspection. Unsafe or malformed inputs never become positive readiness evidence.

## v207 — runtime activation readiness

`build_freshness_runtime_activation_readiness(...)` answers only whether the reader/provider boundary is technically usable. `activation_ready=True` does **not** mean lifecycle readiness, mutation readiness or business execution readiness. A complete reader that currently returns no lifecycle artifacts can therefore be technically activatable while lifecycle readiness stays false.

## v208 — provider diagnostics

`FreshnessOperationalSnapshotProvider.get_diagnostics()` exposes the diagnostics contract without changing the existing `get_snapshot()` behavior.

## v209 — explicit runtime diagnostics route

`AssistantFreshnessOperationalRuntimeService` recognizes explicit diagnostics requests such as `freshness diagnostics` / `диагностика свежести`. Status requests still use the existing readiness projection. Unrelated text is not captured.

## v210 — diagnostics audit

`build_freshness_diagnostics_audit(...)` recomputes activation readiness and rejects contradictory or unsafe downstream claims.

## Safety invariants

- read-only only;
- no audit persistence is introduced;
- no task-draft mutation;
- no Product Decision mutation/recomputation;
- no Ozon API mutation;
- no Action Executor connection;
- `lifecycle_ready=False` in activation diagnostics;
- `mutation_ready=False`;
- `business_execution_ready=False`;
- `application_allowed=False`;
- `persistent=False`;
- `execution_allowed=False`;
- `executed=False`.

## Validation

Focused regression coverage:

- `tests/test_freshness_operational_diagnostics_v204_v210.py`

Latest confirmed full-suite baseline remains the user-reported **982 passed** on the earlier pre-v174 baseline. No later full-suite pass is claimed until independently executed.

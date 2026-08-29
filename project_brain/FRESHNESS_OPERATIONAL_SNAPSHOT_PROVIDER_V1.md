# Freshness Operational Snapshot Provider v1 — v199–v203

Date: 2026-08-30

Architecture Review Required: **Yes** — this adds a production-facing DI boundary that can later connect real audit storage to the read-only freshness runtime.

## Goal

Continue after v194–v198 by making the operational runtime actually injectable without inventing persistence or fabricating lifecycle evidence.

Workflow:

`explicit audit reader → v199 snapshot provider → v200 runtime factory → v201 operational projection → v202 fail-closed diagnostics → v203 immutable snapshot behavior`

## v199 — snapshot provider

`FreshnessOperationalSnapshotProvider` aggregates exactly four canonical audit readers:

- preparation audit;
- executor-admission audit;
- write-protocol audit;
- adapter-boundary audit.

The provider is read-only. Missing reader capabilities, exceptions, or malformed non-dict artifacts fail closed through the runtime boundary.

## v200 — runtime factory

`create_freshness_operational_runtime(reader=None)` returns `None` when there is no explicit reader. This preserves existing assistant behavior and prevents accidental activation with invented or empty production data.

With a reader, the factory wires `FreshnessOperationalSnapshotProvider` into `AssistantFreshnessOperationalRuntimeService` through constructor DI.

## v201 — end-to-end read-only projection

A complete canonical reader set can produce the existing `FRESHNESS_OPERATIONAL_READINESS_SUMMARY`. Operational readiness remains distinct from mutation readiness and business execution readiness.

## v202 — fail-closed reader diagnostics

A partial/incompatible reader fails through the existing runtime response as `FRESHNESS_OPERATIONAL_SNAPSHOT_UNAVAILABLE`; no fallback fabricates missing lifecycle evidence.

## v203 — immutable aggregation

The provider deep-copies every returned artifact so downstream projection cannot mutate the reader-owned canonical object.

## Safety invariants

- no persistence introduced;
- no task-draft mutation;
- no Product Decision recomputation or mutation;
- no Ozon mutation;
- no Action Executor connection;
- no business execution permission;
- no fabricated audit evidence;
- factory remains inactive without an explicit reader;
- reader artifacts are copied before exposure;
- operational readiness never means mutation readiness.

## Production status

This batch makes the runtime DI-ready, but does **not** provide a concrete production audit store because the repository still has no confirmed canonical persistence source for these four freshness lifecycle audits. `create_assistant()` should not activate this route until such a reader exists.

## Validation

Focused regression coverage:

- `tests/test_freshness_operational_snapshot_provider_v199_v203.py`

Latest full-suite baseline supplied by the user before v174+: **982 passed**.

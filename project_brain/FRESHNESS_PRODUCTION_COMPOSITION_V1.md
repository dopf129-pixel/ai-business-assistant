# Freshness Production Composition v1 — v211–v217

Date: 2026-08-30

Architecture Review Required: **Yes** — this changes the main assistant composition boundary, although freshness remains read-only and opt-in.

## Goal

Make the existing freshness operational runtime composable by the production assistant without inventing a canonical audit store. A real caller may inject an explicit audit reader; the default application remains unchanged.

## v211 — factory activation audit

`evaluate_freshness_operational_runtime_activation(reader)` runs the canonical v204–v210 diagnostics path before composition. It reports technical reader activation readiness only.

It never claims lifecycle, mutation or business execution readiness.

## v212 — gated runtime construction

`create_freshness_operational_runtime(reader)` returns a runtime only when:

- a reader was explicitly supplied;
- all four required reader capabilities exist;
- diagnostics contain no capability/read/malformed/safety blocker;
- canonical activation audit says `activation_ready=True`.

A missing or incomplete reader returns `None` rather than a partially wired runtime.

## v213 — explicit assistant composition parameter

`create_assistant(freshness_audit_reader=None)` adds one optional composition parameter. Default `None` is intentional and preserves existing behavior.

No environment-variable lookup, global singleton, JSON fallback or inferred reader is introduced.

## v214 — entry wiring

When and only when the factory returns a runtime, it is passed through the existing `freshness_operational_runtime_service` constructor dependency of `AssistantEntryService`.

## v215 — explicit valid reader route

A complete explicit reader makes freshness status/diagnostics routes available through the main assistant composition. The route remains read-only.

## v216 — incomplete-reader fail-closed behavior

Incomplete readers do not get wired into `AssistantEntryService`. This prevents freshness requests from shadowing existing assistant behavior with a known-broken source.

## v217 — regression preservation

Focused tests verify that existing period-profit composition remains present and that default `create_assistant()` still has no freshness runtime.

## Safety invariants

- default application behavior unchanged;
- no canonical audit store is invented;
- no persistence added;
- no task-draft mutation;
- no Product Decision mutation/recomputation;
- no Ozon mutation;
- no Action Executor connection;
- reader activation does not imply lifecycle readiness;
- lifecycle readiness does not imply mutation readiness;
- `application_allowed=False`;
- `persistent=False`;
- `execution_allowed=False`;
- `executed=False`.

## Validation

Focused regression coverage:

- `tests/test_freshness_production_composition_v211_v217.py`
- existing `tests/test_assistant_app_period_profit_wiring.py` contract remains represented in the new regression coverage.

Latest independently confirmed full-suite baseline remains the earlier user-reported **982 passed**. This document does not claim a later full-suite run.

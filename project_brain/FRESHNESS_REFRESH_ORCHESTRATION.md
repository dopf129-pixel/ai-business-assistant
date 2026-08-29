# Freshness Refresh Orchestration v1

Date: 2026-08-29

## Goal

Connect the v15 refresh request draft and v16 refresh capability contract to existing read-only providers without connecting Product Decision execution.

## Contract

`app/product_task_refresh_orchestrator.py` exposes `execute_read_only_refresh(capability_contract, providers)`.

The orchestrator accepts an already-built capability contract and an injected provider map. It does not discover arbitrary application objects and it does not call provider methods unless the whole capability contract is explicitly marked `all_read_only=True`.

Allowed provider names:

- `ProductDecisionMetricsSource`
- `ProductUnitEconomicsQueryService`

The invoked method and provider must match an explicitly supported, read-only target from the capability contract.

## Result semantics

Possible orchestration statuses:

- `NOT_REQUIRED` — no refresh targets exist;
- `BLOCKED` — capability is not fully read-only or the request lacks a SKU;
- `COMPLETED` — all declared read-only reads returned successfully;
- `PARTIAL` — at least one read succeeded and at least one target failed;
- `FAILED` — no target read completed successfully.

Provider errors are captured as observational refresh errors. They never enable execution.

## Freshness boundary

A successful read does not itself prove source freshness.

Every result keeps:

- `source_freshness_proven=False`;
- `product_decision_recomputed=False`;
- `task_draft_mutated=False`;
- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

Unit economics may still return cache metadata. Cache hit/miss/stale state is diagnostic and is not a substitute for `unit_economics_source_recorded_at`.

## Safety invariants

This change does not:

- call mutating Ozon APIs;
- connect the legacy Action Executor;
- recompute or persist a Product Decision;
- mutate Product Task Draft state;
- infer or fabricate source timestamps;
- treat observation/cache/request time as source freshness evidence;
- change Product Business Decision thresholds;
- modify runtime data files.

## Validation

Focused regression tests: `tests/test_product_task_refresh_orchestrator.py`.

Assistant-side targeted validation: `4 passed in 0.05s`.

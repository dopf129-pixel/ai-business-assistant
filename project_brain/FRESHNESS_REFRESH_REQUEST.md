# Freshness Refresh Request Draft v1

Date: 2026-08-29

## Goal

Represent required freshness work as an explicit, safe request draft without starting a refresh, persisting a new workflow object, or enabling execution.

## Contract

`ProductTaskDraftReadinessService.build_refresh_request(draft)` derives a request from the existing freshness guard and v14 refresh guidance.

When freshness work is required, the result contains:

- deterministic `request_id` based on the Product Task Draft identifier;
- `status=REQUEST_DRAFT`;
- the affected freshness components and existing guidance actions;
- the source decision timestamp for traceability;
- `persistent=False`;
- `refresh_started=False`;
- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

When all freshness-relevant source evidence is fresh, the result uses `status=NOT_REQUIRED`, has no request id, and contains no targets.

## Scope

The request includes only components required by the current proposal type. For example, a margin review targets unit economics and does not add unrelated sales or stock refresh work.

The operation is deterministic and read-only. Repeated calls with the same draft return the same request draft and do not mutate the input.

## Architectural boundary

No new service was introduced. The request builder lives in `ProductTaskDraftReadinessService`, where freshness status, evidence coverage, and refresh guidance already converge.

This avoids a new persistence or execution dependency and keeps the workflow descriptive only.

## Safety invariants

This change does not:

- persist refresh requests;
- call Ozon APIs;
- refresh source data automatically;
- generate or infer source timestamps;
- change Product Business Decision rules;
- mutate Product Task Draft lifecycle state;
- connect the legacy Action Executor;
- enable execution permission;
- modify runtime data files.

## Validation

Focused tests: `tests/test_product_task_freshness_refresh_request.py`.

Assistant-side isolated behavioral validation: 4 checks passed.

A full repository suite is not required for this isolated additive block; the next full integration checkpoint should still run against the real repository checkout.

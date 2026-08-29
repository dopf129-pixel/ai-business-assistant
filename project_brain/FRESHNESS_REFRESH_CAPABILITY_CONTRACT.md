# Freshness Refresh Capability Contract v1

Date: 2026-08-29

## Goal

Describe which existing application paths can safely re-read freshness-relevant Product Task data without connecting Product Decision execution.

The contract consumes the non-persistent refresh-request draft introduced in v15 and returns metadata only. It does not call providers itself.

## Supported components

### Sales

- provider: `ProductDecisionMetricsSource`
- method: `sales(sku)`
- read-only: yes
- cache expected for the public refresh call: no
- reliable source-recorded timestamp currently expected: no

### Stock

- provider: `ProductDecisionMetricsSource`
- method: `stock(sku)`
- read-only: yes
- cache expected for the public refresh call: no
- reliable source-recorded timestamp currently expected: no

### Unit economics

- provider: `ProductUnitEconomicsQueryService`
- method: `query(sku)`
- read-only: yes
- cache may be used: yes
- cache hit/stale fallback does not prove source freshness
- reliable source-recorded timestamp currently expected: no

Unknown components are explicitly unsupported with `REFRESH_PROVIDER_NOT_DEFINED`; they are never assumed safe.

## Contract output

`build_refresh_capability_contract(refresh_request)` returns:

- per-target provider and method metadata;
- `supported` and `read_only` flags;
- `may_use_cache`;
- `source_timestamp_expected`;
- `source_freshness_proven=False`;
- `refresh_execution_connected=False`;
- aggregate capability status.

Statuses:

- `CAPABILITY_READY` — all requested targets have known read-only paths;
- `CAPABILITY_PARTIAL` — only some targets are known;
- `CAPABILITY_UNAVAILABLE` — no requested target has a known path.

## Safety boundary

This contract does not:

- invoke Ozon or any provider;
- persist refresh requests;
- start refresh work;
- generate source timestamps;
- treat observation/cache/request time as source evidence;
- mutate Product Decisions or task drafts;
- connect the legacy Action Executor;
- enable execution.

All execution flags remain false.

## Validation

Focused tests: `tests/test_product_task_refresh_capability_contract.py`.

Targeted assistant-side validation: `4 passed in 0.04s`.

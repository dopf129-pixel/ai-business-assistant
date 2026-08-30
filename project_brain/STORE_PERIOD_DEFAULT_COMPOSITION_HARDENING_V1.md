# Store Period Default Composition Hardening V1

Date: 2026-08-30  
Stages: v509-v513  
Architecture Review Required: Yes

## Gap

`StorePeriodSummaryService()` created a default `StorePeriodRunnerService()` without a period profit dependency.

The runner then created `StorePeriodReportService(profit_service=None)`, and a real build could reach `None.calculate_period_profit(...)`.

The runner constructor also contained a duplicated initialization block.

## Change

- remove duplicate runner initialization;
- preserve existing optional constructor injection;
- make `StorePeriodReportService.build()` return an explicit error when `profit_service` is absent;
- make summary construction reject malformed non-dict runner results.

## Safety

This package does not fabricate financial data or silently substitute a provider.

Missing dependency means blocked/unavailable, not optimistic success.

No profit formula, Ozon call, Product Decision, task execution, mapping, persistence or seller mutation is changed.

## Architecture review

Required because this corrects behavior at an existing service contract boundary.

Review result:

- no new service/layer;
- no competing composition path;
- constructor signatures remain compatible;
- injected test/production dependencies remain supported;
- missing dependency is fail-closed;
- no hidden side effects;
- no invented runtime state.

## Verification

Focused regressions cover the broken default path, malformed runner output and existing injected paths.

Full GitHub Actions verification is required before merge.

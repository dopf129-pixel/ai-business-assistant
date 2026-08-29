# Stock Freshness Observation Evidence v1

## Purpose

Record when the application observed stock values without claiming that this is the timestamp when Ozon recorded or generated those stock values.

## Contract

`ProductDecisionMetricsSource` may expose:

- `stock_observed_at` — application-side UTC observation time for the prepared stock metrics;
- `stock_source_recorded_at` — reserved for a real upstream source timestamp only.

The current Ozon stock path does not expose a reliable source-recorded timestamp in the contract used by `MetricsService`. Therefore v1 does not create `stock_source_recorded_at`.

## Freshness semantics

`ProductTaskDraftFreshnessService` continues to evaluate stock freshness only from `stock_source_recorded_at`.

`stock_observed_at`, request time, cache time, decision time, and draft time are not substitutes for source evidence. A recent observation without a source timestamp must remain `UNKNOWN`.

## Propagation

Existing freshness-evidence propagation carries explicit `stock_observed_at` through prepared decision input, Product Decision payloads, and task drafts.

## Safety

- no Product Decision thresholds changed;
- no execution permission changes;
- no Action Executor connection;
- no mutating Ozon API path;
- no data files changed.

## Validation

Focused tests cover observation metadata, no source timestamp fabrication, evidence propagation, and the `UNKNOWN` freshness invariant.

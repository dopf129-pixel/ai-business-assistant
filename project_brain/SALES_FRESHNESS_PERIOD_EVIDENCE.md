# Sales Freshness Period Evidence v1

## Goal

Add truthful sales freshness diagnostics without treating an analytics period boundary or application observation time as an upstream source-recorded timestamp.

## Current sales pipeline

`ProductDecisionMetricsSource` derives sales velocity and trend from analytics and finance data over a configured current period and previous period.

The finance aggregation exposes `date_from` and `date_to`, but does not expose a reliable Ozon source-recorded timestamp for the aggregated sales facts.

Therefore:

- `sales_period_from` records the start of the analytical period;
- `sales_period_to` records the end of the analytical period;
- `sales_observed_at` records when the application prepared the sales metrics;
- `sales_source_recorded_at` is not generated.

## Propagation

The existing freshness evidence pipeline already propagates explicit `sales_observed_at` through `ProductDecisionInputProvider` and the Product Decision query boundary.

The period fields remain diagnostic metadata on the prepared sales source in v1.

## Freshness safety

`ProductTaskDraftFreshnessService` continues to require `sales_source_recorded_at` when sales freshness is required.

A recent `sales_observed_at`, even together with a recent analytics `sales_period_to`, does not make sales `FRESH`.

Until upstream sales data provides a trustworthy source-recorded timestamp, sales freshness remains `UNKNOWN` where source evidence is required.

## Safety boundaries

- no Product Decision threshold changes;
- no execution permission changes;
- no Action Executor connection;
- no Ozon mutation path;
- no period date is promoted to source-recorded time;
- no observation/request/cache timestamp substitutes for source evidence.

## Validation

`tests/test_sales_freshness_period_evidence.py` covers:

1. sales period diagnostics;
2. deterministic observation time;
3. absence of fabricated `sales_source_recorded_at`;
4. propagation of observation evidence;
5. proof that observation time alone leaves sales freshness `UNKNOWN`.

Status: targeted validation pending.

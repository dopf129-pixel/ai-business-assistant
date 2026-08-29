# Freshness Evidence Contract v1

## Goal

Make Product Task Draft freshness evidence explicit without fabricating source timestamps.

## Contract

Product task drafts may carry two different timestamp classes:

- `*_source_recorded_at` — time supplied by the actual data source and eligible for freshness evaluation;
- `*_observed_at` — time when the application observed or retrieved the data, informational only.

Supported components:

- sales;
- stock;
- unit economics.

## Persistence

`ProductActionTaskDraftService` copies these evidence fields from the product decision into the persisted draft when they are present.

It does not create, infer, or substitute timestamp values.

Legacy decisions without evidence remain compatible and produce drafts without these optional fields.

## Freshness rule

`ProductTaskDraftFreshnessService` continues to evaluate only `*_source_recorded_at`.

`*_observed_at`, `created_at`, `updated_at`, cache time, request time, or confirmation time cannot prove source freshness.

Therefore a recently observed data point with no reliable source timestamp remains `UNKNOWN`.

## Why this matters

The current production stock path receives real Ozon values but does not expose a reliable source-recorded timestamp. Treating request time as source time would falsely convert unknown source age into fresh data.

This contract allows real source timestamps to be propagated later without weakening the existing freshness guard.

## Safety boundary

- no Product Decision rules changed;
- no execution permission changed;
- no legacy Action Executor connection added;
- no Ozon mutation path enabled;
- no source timestamp is fabricated.

## Validation

`tests/test_product_task_freshness_evidence.py` covers:

1. source timestamp persistence;
2. observed/source timestamp separation;
3. observed time cannot prove freshness;
4. real source timestamps can prove freshness;
5. legacy decisions remain compatible.

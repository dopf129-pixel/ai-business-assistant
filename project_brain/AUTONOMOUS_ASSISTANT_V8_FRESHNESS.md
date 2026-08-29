# Autonomous Assistant v8 — Draft Data Freshness Guards

Date: 2026-08-29

Status: Completed

## Purpose

Distinguish between a draft that merely has data and a draft whose required source data is proven fresh enough for manual review.

## Architecture

`ProductTaskDraftFreshnessService` is a separate read-only service injected into `ProductTaskDraftReadinessService` by `product_business_decision_factory.py`.

Freshness statuses:

- `FRESH`
- `STALE`
- `UNKNOWN`

`UNKNOWN` is mandatory when a reliable timestamp is missing, invalid, or in the future. Request time, cache time, draft creation time and draft update time are not valid substitutes for a source timestamp.

The persisted `decision_recorded_at` measures decision-snapshot age only; it is not proof of Ozon/source freshness.

Proposal-aware requirements:

- `REVIEW_REPLENISHMENT`: decision snapshot + sales + stock freshness;
- `REVIEW_UNIT_ECONOMICS`: decision snapshot + unit-economics freshness;
- `REVIEW_MARGIN`: decision snapshot + unit-economics freshness;
- unknown proposal types are evaluated conservatively.

## Current Source Limitation

The current prepared sales, stock and unit-economics contracts do not expose reliable source timestamps in production. Therefore the relevant component freshness remains `UNKNOWN` until those source boundaries propagate real timestamps.

No timestamp is fabricated to make a draft review-ready.

## Readiness Integration

When the freshness guard is connected, `ProductTaskDraftReadinessService` requires `FRESH` source data for `review_ready=True` and adds `SOURCE_DATA_NOT_FRESH` otherwise.

When no freshness service is injected directly, the legacy readiness contract is preserved.

## Telegram Presentation

`AssistantTelegramAdapter` presents freshness without changing the large button-handler business flow:

- review queue: counts for fresh / stale / unknown;
- draft detail: freshness status;
- decision-snapshot age when known;
- Russian human-readable freshness reasons.

Non-draft callbacks remain unchanged.

## Safety Boundary

The Product Decision / Proposal / Draft / Freshness path remains non-executable:

- `execution_ready=False`;
- `executed=False`;
- proposal/draft `execution_allowed=False` remains unchanged;
- no Action Executor connection;
- no mutating Ozon API path;
- no inferred replenishment quantity;
- no inferred price mutation.

`data/users.json` is unchanged.

## Tests

Targeted implementation verification: **18 passed**.

Full repository regression suite run from the developer checkout on 2026-08-29: **329 passed**.

Coverage added in:

- `tests/test_product_task_draft_freshness_service.py`
- `tests/test_product_task_draft_freshness_production_wiring.py`
- `tests/test_product_task_draft_freshness_telegram.py`

Existing readiness tests also verify legacy behavior remains compatible.

## Roadmap

Autonomous Assistant v8 is complete. The next module must be selected only after comparing the roadmap with the implemented code. No execution-policy stage is implied automatically.

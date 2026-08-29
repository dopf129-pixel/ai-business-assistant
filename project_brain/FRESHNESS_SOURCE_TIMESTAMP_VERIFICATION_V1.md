# Freshness Source Timestamp Verification v225-v231

## Goal

Separate two different facts that were previously conflated in readiness coverage:

1. an exact source timestamp field is present;
2. the timestamp is parseable and temporally usable by the freshness guard.

The existing `SOURCE_PROVEN` coverage state is retained for backward compatibility and continues to mean that the exact `*_source_recorded_at` field is present. A new verification dimension describes whether that value is actually usable as a timestamp.

## New source timestamp states

For each freshness-relevant component:

- `VERIFIED` — source field is present and the freshness service parsed it into a valid past timestamp; component status may be `FRESH` or `STALE`;
- `UNVERIFIED` — source field is present but freshness status is `UNKNOWN`, for example malformed or future timestamp;
- `ABSENT` — no exact source timestamp field is present.

This does not assert upstream business correctness or external verification. It is only validation of the timestamp evidence already supplied to the freshness guard.

## Stages

### v225 — Valid source timestamp verification

Fresh, parseable source timestamps are marked `VERIFIED`.

### v226 — Stale source timestamp verification

A parseable stale timestamp remains `VERIFIED` as timestamp evidence; it still requires source data refresh.

### v227 — Future and malformed evidence

Future or malformed source timestamps are `UNVERIFIED` and remain freshness `UNKNOWN`.

### v228 — Observation-only and absent evidence

Observation-only data has `source_timestamp_state=ABSENT`. Observation timestamps never become source timestamps.

### v229 — Operator wording

Telegram detail no longer describes every present source field as "источник подтверждён".

It distinguishes:

- `timestamp источника проверен`;
- `timestamp источника требует проверки`;
- `timestamp источника отсутствует`.

### v230 — Aggregate verification counts

Readiness summaries expose:

`freshness_source_timestamp_counts = {VERIFIED, UNVERIFIED, ABSENT}`.

### v231 — Presentation regression

Focused tests verify that verified and unverified source fields are rendered differently while all execution flags remain false.

## Refresh guidance

Existing action semantics remain:

- stale valid source timestamp → `REFRESH_SOURCE_DATA`;
- unverified source timestamp → `VERIFY_SOURCE_TIMESTAMP`;
- absent source timestamp → `SOURCE_TIMESTAMP_REQUIRED`.

## Safety

This change does not:

- fabricate timestamps;
- promote observed timestamps;
- claim external verification;
- change Product Decision rules;
- persist or mutate drafts;
- recompute Product Decisions;
- connect Action Executor;
- call mutating Ozon endpoints;
- enable execution.

`execution_ready=False` and `executed=False` remain invariant.

## Validation

Focused regression coverage:

`tests/test_freshness_source_timestamp_verification_v225_v231.py`

Full repository suite is not claimed as run in the connector-only environment.

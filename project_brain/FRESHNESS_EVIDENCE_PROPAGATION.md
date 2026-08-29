# Freshness Evidence Propagation v1

## Goal

Propagate explicit freshness evidence from prepared Product Decision inputs into the final decision and persisted task draft without inventing source timestamps.

## Pipeline

Evidence can now flow through:

`prepared sales / stock / unit economics -> ProductDecisionInputProvider -> ProductBusinessDecisionQueryService -> Product Decision -> Product Task Draft`

Supported fields:

- `sales_source_recorded_at`;
- `stock_source_recorded_at`;
- `unit_economics_source_recorded_at`;
- `sales_observed_at`;
- `stock_observed_at`;
- `unit_economics_observed_at`.

Fields are propagated only when an upstream contract explicitly supplies them.

## Current unit economics observation

`CurrentProductEconomicsSource` currently emits `as_of` using the application clock. This describes when the application observed/retrieved the current economics facts.

Therefore the query boundary maps:

`as_of -> unit_economics_observed_at`

It never maps `as_of` to `unit_economics_source_recorded_at`.

An explicit upstream `unit_economics_source_recorded_at`, if introduced later, is preserved separately.

## Cache boundary

Unit-economics `cache.cached_at` remains cache metadata only. It is not propagated as source freshness evidence.

## Stock and sales boundary

Prepared sales and stock sources may propagate explicit evidence fields when they genuinely have them.

The current production stock path does not expose a reliable source-recorded timestamp, so stock freshness remains `UNKNOWN` until such evidence exists.

No request, observation, cache, decision, draft, or confirmation timestamp is substituted for a missing source timestamp.

## Architecture

Evidence propagation is implemented at the input/query composition boundary. `ProductBusinessDecisionService` decision rules are unchanged.

## Safety

- no Product Decision threshold or priority rule changes;
- no execution permission changes;
- no Action Executor connection;
- no Ozon mutation path;
- no timestamp fabrication;
- observed time alone cannot make draft freshness `FRESH`.

## Validation

`tests/test_product_decision_freshness_evidence_propagation.py` covers:

1. explicit evidence propagation from all three prepared sources;
2. absence of fabricated evidence when upstream fields are missing;
3. mapping current unit-economics `as_of` to observed time only;
4. propagation of explicit source evidence into the final decision;
5. end-to-end proof that observed economics time alone still leaves draft freshness `UNKNOWN`.

Status: targeted validation pending.

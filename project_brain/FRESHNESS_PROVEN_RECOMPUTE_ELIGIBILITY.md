# Freshness-Proven Product Decision Recompute Eligibility v1

## Goal

Allow the system to state that a Product Decision is eligible for a separate review/recompute step only after v32 has proven source freshness from durable verified evidence.

## Input

The contract consumes the v32 freshness promotion and requires:

- status `SOURCE_FRESHNESS_PROVEN`;
- `source_freshness_proven=True`;
- `promotion_ready=True`;
- exact allowlisted `proven_evidence` and matching count;
- no persistence/draft mutation in the promotion contract;
- Product Decision mutation/recompute, Ozon mutation, and all execution flags false.

## Success

Returns `PRODUCT_DECISION_RECOMPUTE_REVIEW_ELIGIBLE` with `recompute_review_eligible=True` and `recompute_review_required=True`.

Eligibility is not permission. `recompute_allowed=False` and `recompute_started=False` remain explicit.

## Safety

This is a pure contract. It does not recompute or mutate Product Decisions, save drafts, call Ozon, invoke the legacy Action Executor, or enable execution. `execution_allowed`, `execution_ready`, and `executed` remain false.

# Freshness State Promotion v1

## Goal

Promote independently verified durable freshness evidence into an explicit `source_freshness_proven=True` contract without mutating any durable state or enabling Product Decision execution.

## Input

The contract consumes the v31 durable verification result and requires:

- status `FRESHNESS_EVIDENCE_DURABLE_PERSISTENCE_VERIFIED`;
- `verified=True`;
- empty `mismatched_fields`;
- exact allowlisted `verified_evidence` and matching count;
- Product Decision mutation/recompute, Ozon mutation, and execution flags all false.

## Success

Returns `SOURCE_FRESHNESS_PROVEN`, `source_freshness_proven=True`, deterministic promotion identity bound to the exact verified evidence fingerprint, and a copied `proven_evidence` set.

## Safety

Promotion is a pure contract only. It does not save storage, mutate the task draft, recompute or mutate Product Decisions, call Ozon, invoke the legacy Action Executor, or enable execution. `execution_allowed`, `execution_ready`, and `executed` remain false.

Targeted exact minimal-checkout pytest: `10 passed in 0.04s`.

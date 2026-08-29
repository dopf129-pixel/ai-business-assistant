# Product Decision Recompute Review Authorization v1

## Goal

Allow an explicit `AUTHORIZE` / `REJECT` decision on the v33 recompute-review eligibility contract without performing Product Decision recomputation.

## Input

The contract requires exact v33 eligibility lineage, proven freshness, exact allowlisted evidence, `recompute_review_eligible=True`, `recompute_review_required=True`, and all pre-existing recompute/mutation/execution flags closed.

## Success

`AUTHORIZE` returns `PRODUCT_DECISION_RECOMPUTE_REVIEW_AUTHORIZED` with `recompute_authorized=True` and `recompute_allowed=True`.

`REJECT` returns `PRODUCT_DECISION_RECOMPUTE_REVIEW_REJECTED` and keeps recompute disallowed.

In both cases `recompute_started=False`, `product_decision_recomputed=False`, and `product_decision_mutated=False`.

## Safety

Authorization is permission for a separate future recompute step only. It does not call ProductBusinessDecisionService, persist or mutate drafts, call Ozon, invoke the legacy Action Executor, or enable execution. `execution_allowed`, `execution_ready`, and `executed` remain false.

Targeted exact minimal-checkout pytest: `11 passed in 0.05s`.

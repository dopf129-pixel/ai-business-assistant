# Product Decision Recompute Preview v1

## Goal

Perform an explicitly authorized Product Decision recomputation as a non-persistent preview only.

## Design

`ProductDecisionRecomputePreviewService` receives the decision engine through constructor injection. It accepts the v34 authorization contract plus prepared `product_metrics`, validates exact authorization lineage and safety boundaries, requires exact allowlisted authorization evidence, verifies SKU identity, and then calls the injected decision service.

## Success

Returns `PRODUCT_DECISION_RECOMPUTE_PREVIEW_READY` with the recomputed decision under `preview_decision`.

Because calculation actually occurs, `recompute_started=True` and `product_decision_recomputed=True` are explicit. However the result is preview-only:

- `persistent=False`;
- `product_decision_mutated=False`;
- `product_decision_persisted=False`;
- `task_draft_mutated=False`;
- no Ozon mutation;
- no legacy Action Executor;
- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

Calculation errors or invalid result identity fail closed and do not claim recomputation success.

Targeted exact minimal-checkout pytest: `12 passed in 0.05s`.

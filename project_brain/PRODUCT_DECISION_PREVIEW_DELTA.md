# Product Decision Preview Delta v1

## Goal

Compare the latest persisted Product Decision snapshot with the explicitly authorized v35 recompute preview without changing either value.

## Contract

`ProductDecisionPreviewDeltaService.compare(current_decision, recompute_preview)` validates the v35 preview lineage and safety boundary, requires matching SKU identity, and compares only stable decision fields:

- `decision_type`;
- `priority`;
- `confidence`;
- `reasons`.

## Success

Returns `PRODUCT_DECISION_PREVIEW_DELTA_READY` with deterministic `decision_preview_delta_id`, `decision_changed`, ordered `changed_fields`, exact before/after `changes`, and compact current/preview decision views.

The service is read-only:

- `persistent=False`;
- `task_draft_mutated=False`;
- `product_decision_mutated=False`;
- `product_decision_persisted=False`;
- no Product Decision history write;
- no Ozon mutation;
- no legacy Action Executor;
- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

Targeted exact minimal-checkout pytest: `11 passed in 0.05s`.

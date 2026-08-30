# Verification Status

Date: 2026-08-30

## Latest verified baseline entering v488-v492

Latest exact verified `main`:

`5c372255b87b8b5a8387ed980f51372d925b33d9`

Latest merged seller-facing batch:

`v478-v487: add Product Decision learning health surface`

Full-suite verification for this exact SHA:

- GitHub Actions workflow: `Verify`
- event: `push`
- run number: **58**
- conclusion: **success**
- result: **1309 passed**
- failed: **0**
- exact SHA-bound: **yes**
- canonical JSON test manifest generated: **yes**

## Seller-facing Learning Health coverage

The current production Telegram flow now exposes a read-only Product Decision Learning Health screen.

It is based only on persisted `ProductDecisionHistoryService.learning_summary()` aggregates.

The screen shows:

- products in decision history;
- decision snapshots;
- user feedback counts;
- later decision-change observation counts;
- descriptive evidence-volume state;
- a safe next evidence-collection/review step.

It does not expose a success rate.

## Learning Health safety semantics

Mandatory invariants remain:

- `causal_claim_allowed=False`;
- `success_rate_claim_allowed=False`;
- `profitability_claim_allowed=False`;
- `decision_rule_update_allowed=False`;
- `automatic_execution_allowed=False`;
- `executed=False`.

The seller-facing wording explicitly states that counts do not prove causality, decision correctness or profitability.

## Canonical advisory-chain limitation

The newer user-action guidance/checklist/advisory contracts require exact persisted and independently verified Product Decision lineage.

The current Telegram decision card does not possess that verification artifact.

Therefore the canonical advisory/checklist chain remains intentionally unconnected to production Telegram.

No lineage is reconstructed from legacy aggregates.

## Next product target

The next safe seller-facing gap is per-SKU learning coverage.

A Learning Coverage Queue should identify, from existing decision-history facts only:

- SKUs with no stored decision feedback;
- SKUs with feedback but no later observation;
- SKUs with later descriptive observations;
- stable, explainable priority for which SKU to review next.

It must not:

- score business performance;
- infer causality;
- infer profitability;
- change Product Decision rules;
- execute actions.

## Persistence hardening status

Kernel-backed task-persistence hardening remains closed after v463-v472.

No new persistence layer is planned without a concrete defect or product requirement.

## Verification policy

Every safety-critical or production-wired PR must pass the full GitHub Actions verification workflow before merge.

Every resulting `main` SHA must receive its own successful push verification before becoming the current exact baseline.

## Safety

Current learning/verification surfaces do not:

- alter Product Decisions;
- execute Product Task Drafts;
- mutate Ozon;
- change mapping authorization;
- change financial calculations;
- modify `data/users.json`.

## Related implementation

- `app/product_decision_learning_health.py`
- `app/services/product_decision_history_service.py`
- `app/services/assistant_button_handler_service.py`
- `app/services/assistant_keyboard_service.py`
- `app/telegram_assistant_factory.py`
- `tests/test_product_decision_learning_health_v478_v487.py`
- `project_brain/PRODUCT_DECISION_LEARNING_HEALTH_SURFACE_V1.md`
- `project_brain/CURRENT_CHECKPOINT_V488_V492.md`

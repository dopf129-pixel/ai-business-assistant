# Verification Status

Date: 2026-08-30

## Latest verified product baseline entering docs reconciliation

Latest exact verified `main` product baseline:

`ef8b52ad34740d5cbb657988866ec01ebfe7191b`

Latest merged seller-facing batch:

`v493-v502: add Product Decision learning coverage queue`

GitHub evidence is kept SHA-bound and separated by layer.

### PR-head verification

- PR: **#219**
- exact head SHA: `dea7c6e7accdbc599744043d181636957766db35`
- workflow: `Verify`
- event: pull request
- run number: **61**
- status: **completed**
- conclusion: **success**

This confirms the PR head only. It is not reused as proof for the squash-merge SHA.

### Post-merge main verification

- exact main SHA: `ef8b52ad34740d5cbb657988866ec01ebfe7191b`
- workflow: `Verify`
- event: **push**
- run number: **62**
- run id: **33310108807**
- status: **completed**
- conclusion: **success**
- full test suite: **1321 passed**
- failed: **0**
- canonical SHA-bound test-report artifact: **generated**
- workflow artifact: `verification-ef8b52ad34740d5cbb657988866ec01ebfe7191b`

The completed workflow run is CI evidence for this exact SHA. It does not imply independent external verification.

## Seller-facing Learning Coverage Queue

The production Telegram flow now exposes a read-only per-SKU Product Decision Learning Coverage Queue.

It uses only:

- current product identities from `product_service.load_products()`;
- persisted Product Decision records from `ProductDecisionHistoryService.history(sku)`.

Opening the queue does not call `ProductBusinessDecisionQueryService.query()` and therefore does not create a new Product Decision snapshot.

Current states:

- `NEEDS_USER_FEEDBACK`;
- `NO_DECISION_HISTORY`;
- `WAITING_FOR_LATER_OBSERVATION`.

The deterministic rank is learning-attention only, with exact SKU lexical tie-break. It is not business priority.

## Learning safety semantics

Mandatory invariants remain:

- `business_priority_claimed=False`;
- `causal_claim_allowed=False`;
- `success_rate_claim_allowed=False`;
- `profitability_claim_allowed=False`;
- `decision_rule_update_allowed=False`;
- `automatic_execution_allowed=False`;
- `executed=False`.

Older outcome evidence does not satisfy the need for a future observation after the latest feedback.

Absence of a later snapshot is not interpreted as evidence that a decision stayed unchanged.

## Canonical advisory-chain limitation

The newer user-action guidance/checklist/advisory contracts require exact persisted and independently verified Product Decision lineage.

The current Telegram decision card still does not possess that verification artifact.

Therefore that canonical advisory/checklist chain remains intentionally unconnected to production Telegram.

No lineage is reconstructed from legacy aggregates.

## Persistence hardening status

Kernel-backed task-persistence hardening remains closed after v463-v472.

No new persistence layer is planned without a concrete defect or product requirement.

## Next package selection

The previously planned per-SKU Learning Coverage Queue is complete.

The next package must be selected from a concrete current product, production-correctness, operator-usability, observability or release-readiness gap after re-reading the actual repository.

Do not create another learning/provenance wrapper solely because the previous package was in that area.

## Verification policy

Every safety-critical or production-wired PR must pass the full GitHub Actions verification workflow before merge.

Every resulting `main` SHA must receive its own successful push verification before becoming the current exact baseline.

A PR-head green run is not proof for the squash-merge SHA.

A canonical test manifest proves test-suite results for its bound SHA; it does not by itself prove final workflow completion.

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
- `app/product_decision_learning_coverage_queue.py`
- `app/services/product_decision_history_service.py`
- `app/services/assistant_button_handler_service.py`
- `app/services/assistant_keyboard_service.py`
- `app/telegram_assistant_factory.py`
- `tests/test_product_decision_learning_health_v478_v487.py`
- `tests/test_product_decision_learning_coverage_v493_v502.py`
- `project_brain/PRODUCT_DECISION_LEARNING_HEALTH_SURFACE_V1.md`
- `project_brain/PRODUCT_DECISION_LEARNING_COVERAGE_QUEUE_V1.md`
- `project_brain/CURRENT_CHECKPOINT_V493_V502.md`

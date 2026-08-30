# Verification Status

Date: 2026-08-30

## Latest verified product baseline

Latest exact verified `main` product baseline:

`ed7ca690c78372e10e09ff471cae8023bd8d4125`

Latest merged production-correctness batch:

`v534-v540: harden Sales evidence availability`

GitHub evidence remains SHA-bound and separated by layer.

### PR-head verification

- PR: **#231**
- final exact head SHA: `86d24f903b37de19c042414e33a932dbbbc94c1e`
- workflow: `Verify`
- event: pull request
- run number: **99**
- run id: **33317832547**
- status: **completed**
- conclusion: **success**
- full test suite: **1385 passed**
- failed: **0**

This confirms the PR head only. It is not reused as proof for the squash-merge SHA.

### Post-merge main verification

- exact main SHA: `ed7ca690c78372e10e09ff471cae8023bd8d4125`
- workflow: `Verify`
- event: **push**
- run number: **100**
- run id: **33317865276**
- status: **completed**
- conclusion: **success**
- full test suite: **1385 passed**
- failed: **0**
- canonical SHA-bound test-report artifact: **generated**
- workflow artifact: `verification-ed7ca690c78372e10e09ff471cae8023bd8d4125`

The completed workflow run is CI evidence for this exact SHA. It does not imply independent external verification.

## Sales evidence availability hardening

The configured Sales Intelligence path now distinguishes complete comparison
evidence from unavailable or malformed comparison evidence.

Contract:

- confirmed decline keeps the existing `sales_down=True` + `sales_context`
  action payload;
- complete non-decline evidence returns `sales_down=False` and
  `sales_evidence_available=True`;
- unavailable/partial configured evidence returns `sales_down=False` and
  `sales_evidence_available=False`;
- availability metadata is report evidence only and is not execution permission.

Historical AssistantEntryService mode with no data dependencies at all keeps its
existing hardcoded fallback for backward compatibility.

## Fail-closed sales evidence

Configured sales evidence fails closed on:

- malformed or empty product collections;
- malformed product targets;
- invalid current/previous period payloads;
- failed, empty or malformed period-profit evidence;
- failed or malformed analytics results;
- malformed comparison structures;
- missing, boolean or non-finite revenue `change_percent`.

Missing comparison change is not normalized to 0%.

Explicit numeric zero change remains valid stable evidence.

## Sales Intelligence metric semantics

SalesIntelligenceService rejects malformed action context before invoking the
analytics service.

Required sales facts:

- revenue / `gross_sales`;
- gross profit / `gross_profit`.

Missing or malformed required facts produce an insufficient-data result.

Optional business metrics:

- business profit;
- margin percent.

Missing optional business metrics remain `None`, not zero.

Missing or malformed comparison change produces no trend insight and is not
treated as stable.

AssistantSalesExecutorService renders unknown metrics as `—`.

## Recommendation semantics

A sales action remains tied to `sales_down=True`.

When no other recommendation exists and
`sales_evidence_available=False`, the generic fallback says:

`Недостаточно данных для полной оценки бизнеса`

instead of claiming:

`Критичных проблем не найдено`.

## Execution safety

This package does not:

- change the sales-decline threshold;
- alter Product Decision rules;
- execute Product Task Drafts;
- add an Action Executor route;
- mutate Ozon;
- modify persistence;
- modify `data/users.json`.

No sales-evidence availability field is business execution authorization.

## Persistence hardening status

Kernel-backed task-persistence hardening remains closed after v463-v472.

No new persistence layer is planned without a concrete defect or product requirement.

## Next package selection

Choose the next package from a concrete current product, production-correctness,
operator-usability, observability or release-readiness gap.

Do not extend sales/evidence/provenance layers solely to advance stage numbering.

The canonical user-action advisory/checklist chain remains disconnected from
production Telegram until exact persisted Product Decision verification lineage
is available there.

## Verification policy

Every safety-critical or production-wired PR must pass full GitHub Actions
verification before merge.

Every resulting `main` SHA must receive its own successful push verification
before becoming the current exact baseline.

A PR-head green run is not proof for the squash-merge SHA.

A failed SHA remains failed evidence even if a later SHA on the same branch passes.

A canonical test manifest proves suite results for its bound SHA; it does not by
itself prove final workflow completion.

## Related implementation

- `app/services/assistant_entry_service.py`
- `app/services/assistant_recommendation_service.py`
- `app/services/sales_context_provider.py`
- `app/services/sales_intelligence_service.py`
- `app/services/assistant_sales_executor_service.py`
- `tests/test_sales_evidence_availability_v534_v540.py`
- `project_brain/SALES_EVIDENCE_AVAILABILITY_HARDENING_V1.md`
- `project_brain/CURRENT_CHECKPOINT_V534_V540.md`

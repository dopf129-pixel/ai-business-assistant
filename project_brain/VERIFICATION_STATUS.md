# Verification Status

Date: 2026-08-30

## Latest verified product baseline

Latest exact verified `main` product baseline:

`0dacff655fe97a6ca9bab32b7977b7ac432cc0c9`

Latest merged financial-correctness batch:

`v521-v526: harden Finance Context evidence`

GitHub evidence remains SHA-bound and separated by layer.

### PR verification history

Initial PR head:

`b794ae652faf4e49a69457ad7fa6c5b2232fb623`

- PR: **#227**
- workflow: `Verify`
- event: pull request
- run number: **78**
- run id: **33315549168**
- status: **completed**
- conclusion: **failure**

The failure was caused by the first iteration extending the explicitly protected
FinanceContextProvider output shape with a new `profit_scope` field.

That contract extension was removed in the same branch.

The failed SHA remains failed evidence and is not promoted as verified.

Final PR head:

`33a2e3551bc453cadc748314b552286a4de306a8`

- workflow: `Verify`
- event: pull request
- run number: **87**
- run id: **33315651481**
- status: **completed**
- conclusion: **success**
- full test suite: **1355 passed**
- failed: **0**

This confirms the final PR head only. It is not reused as proof for the squash-merge SHA.

### Post-merge main verification

- exact main SHA: `0dacff655fe97a6ca9bab32b7977b7ac432cc0c9`
- workflow: `Verify`
- event: **push**
- run number: **88**
- run id: **33315687562**
- status: **completed**
- conclusion: **success**
- full test suite: **1355 passed**
- failed: **0**
- canonical SHA-bound test-report artifact: **generated**
- workflow artifact: `verification-0dacff655fe97a6ca9bab32b7977b7ac432cc0c9`

The completed workflow run is CI evidence for this exact SHA. It does not imply independent external verification.

## Finance Context evidence hardening

The existing FinanceContextProvider output shape remains backward compatible:

- `revenue`
- `expenses`
- `profit`
- `margin`

No mandatory provider `profit_scope` field was added.

Input handling is now fail-closed:

- non-dict period payloads are rejected;
- non-dict source rows are rejected;
- any explicit source row with `error=True` blocks aggregation;
- missing `gross_sales` or `gross_profit` blocks aggregation;
- malformed, boolean and non-finite required values are rejected;
- explicit numeric zero remains valid evidence;
- mixed valid + error rows do not produce partial totals.

FinanceIntelligenceService also rejects malformed current or provided previous
finance contexts instead of converting invalid values to optimistic zero facts.

## Seller-facing financial semantics

Finance Intelligence no longer claims that period gross-result evidence proves
whole-business accounting profitability.

Seller-facing output uses evidence-scoped language such as:

- `Расчётный финансовый результат`;
- `Расходы по доступным данным`;
- `Маржинальность по доступным данным`.

Direct FinanceIntelligenceService inputs may receive deterministic internal
scope classification, but that does not alter the FinanceContextProvider output
contract.

## Financial safety

This package does not:

- change period-profit arithmetic for complete evidence;
- alter `FinanceService.fee_breakdown`;
- subtract marketplace fees twice;
- infer or subtract tax, advertising, storage or returns expenses again;
- claim complete return economics;
- claim accounting net profit.

The derived `expenses = revenue - gross_profit` value remains an existing
available-evidence metric, not complete business expenses.

## Product and execution safety

This package does not:

- alter Product Decisions;
- execute Product Task Drafts;
- add or change Action Executor mappings;
- mutate Ozon;
- add a seller/business execution route;
- modify persistence;
- modify `data/users.json`.

## Persistence hardening status

Kernel-backed task-persistence hardening remains closed after v463-v472.

No new persistence layer is planned without a concrete defect or product requirement.

## Next package selection

Choose the next package from a concrete current product, production-correctness,
operator-usability, observability or release-readiness gap.

Do not extend finance/evidence/provenance layers solely to advance stage numbering.

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

- `app/services/finance_context_provider.py`
- `app/services/finance_intelligence_service.py`
- `app/services/assistant_finance_executor_service.py`
- `tests/test_finance_context_evidence_v521_v526.py`
- `tests/test_finance_intelligence_business_data_input.py`
- `tests/test_finance_intelligence_executor_integration.py`
- `tests/test_intelligence_context_providers_refactor.py`
- `project_brain/FINANCE_CONTEXT_EVIDENCE_HARDENING_V1.md`
- `project_brain/CURRENT_CHECKPOINT_V521_V526.md`

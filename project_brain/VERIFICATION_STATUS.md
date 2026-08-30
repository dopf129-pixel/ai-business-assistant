# Verification Status

Date: 2026-08-30

## Latest verified product baseline

Latest exact verified `main` product baseline:

`f10679a2d3eb8890480a9cdf59f15c1db5541823`

Latest merged financial-correctness batch:

`v514-v520: preserve unknown advertising financial evidence`

GitHub evidence remains SHA-bound and separated by layer.

### PR-head verification

- PR: **#225**
- final exact head SHA: `fbcc64ffa58611dde0a7b2364b0e17a7cdfb5e4a`
- workflow: `Verify`
- event: pull request
- final successful run number: **74**
- run id: **33315001914**
- status: **completed**
- conclusion: **success**
- full test suite: **1342 passed**
- failed: **0**

An earlier PR run #73 on head `866f28102cd6f8f1ea80987e4fa5adf5bb572f61` failed because a newly added regression test bypassed the real StoreAnalyticsService boundary. The test was corrected in the same branch. That failed SHA is not promoted as verified evidence.

This confirms the final PR head only. It is not reused as proof for the squash-merge SHA.

### Post-merge main verification

- exact main SHA: `f10679a2d3eb8890480a9cdf59f15c1db5541823`
- workflow: `Verify`
- event: **push**
- run number: **75**
- run id: **33315031971**
- status: **completed**
- conclusion: **success**
- full test suite: **1342 passed**
- failed: **0**
- canonical SHA-bound test-report artifact: **generated**
- workflow artifact: `verification-f10679a2d3eb8890480a9cdf59f15c1db5541823`

The completed workflow run is CI evidence for this exact SHA. It does not imply independent external verification.

## Unknown advertising financial evidence

Production business analytics no longer interprets missing advertising-expense evidence as a known zero.

Contract:

- `advertising_cost=None` means evidence unavailable;
- `advertising_cost=""` remains unavailable/unknown;
- explicit numeric `0` means a known zero;
- positive numeric values are explicit known advertising expense evidence.

When advertising evidence is unknown:

- advertising output is `configured=False`;
- advertising cost remains `None`;
- revenue and gross profit remain separately available;
- business profit and margin remain `None`;
- missing evidence includes `advertising`;
- unconfigured tax is reported separately;
- tax errors are not hidden.

Presentation renders unknown or malformed financial values as `—`, not zero or Python `None`.

## Financial safety

This package does not:

- alter Ozon fee calculations;
- classify or remap RETURN / ADVERTISING / STORAGE;
- double-subtract `FinanceService.fee_breakdown`;
- claim complete return economics;
- claim accounting net profit;
- create a hidden advertising API fetch;
- infer advertising spend from unrelated evidence.

## Product and execution safety

This package does not:

- alter Product Decisions;
- execute Product Task Drafts;
- connect a new Action Executor route;
- mutate Ozon;
- modify persistence;
- modify `data/users.json`.

## Persistence hardening status

Kernel-backed task-persistence hardening remains closed after v463-v472.

No new persistence layer is planned without a concrete defect or product requirement.

## Next package selection

Choose the next package from a concrete current product, production-correctness, operator-usability, observability or release-readiness gap.

Do not extend learning/provenance/financial evidence layers solely to advance stage numbering.

The canonical user-action advisory/checklist chain remains disconnected from production Telegram until exact persisted Product Decision verification lineage is available there.

## Verification policy

Every safety-critical or production-wired PR must pass full GitHub Actions verification before merge.

Every resulting `main` SHA must receive its own successful push verification before becoming the current exact baseline.

A PR-head green run is not proof for the squash-merge SHA.

A failed SHA remains failed evidence even if a later SHA on the same branch passes.

A canonical test manifest proves suite results for its bound SHA; it does not by itself prove final workflow completion.

## Related implementation

- `app/telegram_core_factory.py`
- `app/services/advertising_service.py`
- `app/services/business_analytics_service.py`
- `app/services/sales_intelligence_service.py`
- `app/services/assistant_sales_executor_service.py`
- `app/services/advertising_dashboard_service.py`
- `app/services/business_profit_dashboard_service.py`
- `tests/test_unknown_advertising_financial_evidence_v514_v520.py`
- `project_brain/UNKNOWN_ADVERTISING_FINANCIAL_EVIDENCE_V1.md`
- `project_brain/CURRENT_CHECKPOINT_V514_V520.md`

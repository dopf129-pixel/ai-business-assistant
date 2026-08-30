# Verification Status

Date: 2026-08-30

## Latest verified product baseline

Latest exact verified `main` product baseline:

`81ebdccf88a3959d65607de28c904bb952054139`

Latest merged lifecycle-correctness batch:

`v541-v547: preserve FAILED lifecycle for executor error results`

GitHub evidence is separated by the revision actually executed.

## Verification layers for PR #233

### Failed exact branch-head evidence

Earlier exact feature SHA:

`3c49c302b631f888f45e74c3c7c38d2b36522946`

- workflow: `Verify`
- event: **push**
- run number: **106**
- run id: **33318940284**
- actual checkout SHA: `3c49c302b631f888f45e74c3c7c38d2b36522946`
- status: **completed**
- conclusion: **failure**
- tests: **1392 passed, 1 failed**

The failure came from the existing CI contract test requiring the explicit
`- main` push trigger after branch push verification was first added as only
`"**"`.

The workflow was corrected in the same branch to preserve explicit `main` and
also verify all branch pushes.

This failed SHA remains failed evidence and is not promoted by later green runs.

### Final exact branch-head verification

Final feature head:

`aca50b561c999da1a6aac47afb1ebfe191617a9a`

- PR: **#233**
- workflow: `Verify`
- event: **push**
- run number: **112**
- run id: **33319126918**
- actual checkout SHA: `aca50b561c999da1a6aac47afb1ebfe191617a9a`
- status: **completed**
- conclusion: **success**
- full test suite: **1395 passed**
- failed: **0**
- SHA-bound artifact: `verification-aca50b561c999da1a6aac47afb1ebfe191617a9a`
- artifact id: **9734360032**

This is the exact PR branch-head verification evidence.

### Pull-request merge-ref integration verification

- PR: **#233**
- workflow: `Verify`
- event: **pull_request**
- run number: **113**
- run id: **33319129148**
- status: **completed**
- conclusion: **success**

GitHub's pull-request workflow checks out a synthetic PR merge revision by
default. Therefore this run is merge-ref integration evidence, not exact
branch-head evidence, even though GitHub run metadata also references the PR
head.

Do not transfer this run's test manifest or revision identity to
`aca50b561c999da1a6aac47afb1ebfe191617a9a`.

### Post-merge exact main verification

Squash-merge `main` SHA:

`81ebdccf88a3959d65607de28c904bb952054139`

- workflow: `Verify`
- event: **push**
- run number: **114**
- run id: **33319235235**
- actual checkout SHA: `81ebdccf88a3959d65607de28c904bb952054139`
- status: **completed**
- conclusion: **success**
- full test suite: **1395 passed**
- failed: **0**
- SHA-bound artifact: `verification-81ebdccf88a3959d65607de28c904bb952054139`
- artifact id: **9734392896**

This completed push run verifies the exact squash-merge SHA and establishes the
current product baseline. It is CI evidence, not independent external
verification.

## Executor error-result lifecycle integrity

Before v541-v547, AssistantActionExecutionService handled raised exceptions as
FAILED but an executor could return a normal dictionary with `error=True` and
still continue into `complete_action()`.

The persisted execution boundary now fails closed:

- `AssistantActionRouterService.execute()` preserves its direct result-returning
  contract;
- `AssistantActionRouterService.run()` validates persisted-execution results;
- explicit executor `error=True` is routed into the existing exception/FAILED
  lifecycle;
- non-dict results fail as `INVALID_EXECUTOR_RESULT`;
- malformed error flags fail as `INVALID_EXECUTOR_RESULT`;
- explicit error without a usable message uses `EXECUTOR_RETURNED_ERROR`;
- arbitrary result payload fields are not stringified into persisted errors.

For executor-returned failures:

- action status becomes FAILED, not DONE;
- task remains ACTIVE rather than falsely completing;
- pending action is cleared;
- failed progress is not counted as completed;
- history records `execution_failed`, not `execution_completed`;
- feedback records FAILED, not DONE;
- existing retry policy and retry preparation remain active;
- `complete_action()` is not reached.

Successful results preserve the existing DONE completion path.

## Exact branch-SHA CI contract

`Verify` now runs on:

- pull requests;
- explicit `main` pushes;
- all branch pushes;
- workflow dispatch.

For an open PR, use the branch-push run as exact feature/docs head evidence.
Use the pull-request run as synthetic merge-ref integration evidence.

After squash merge, a separate `main` push run remains mandatory for the exact
merged SHA.

Evidence must not be transferred among:

1. feature/docs branch head SHA;
2. synthetic PR merge SHA;
3. squash-merge `main` SHA.

The canonical test report remains bound to the run's actual `GITHUB_SHA` and does
not by itself prove final workflow completion.

## Execution safety

This package does not:

- add a new executor or runtime route;
- change Product Decision rules;
- execute Product Task Drafts;
- add Ozon mutation;
- change retry limits;
- change task persistence format;
- modify `data/users.json`.

The lifecycle change prevents false completion; it does not grant new business
execution permission.

## Persistence hardening status

Kernel-backed task-persistence hardening remains closed after v463-v472.

No new persistence layer is planned without a concrete defect or product requirement.

## Next package selection

Choose the next package from a concrete current product, production-correctness,
operator-usability, observability or release-readiness gap.

Do not extend lifecycle/provenance/evidence layers solely to advance stage
numbering.

The canonical user-action advisory/checklist chain remains disconnected from
production Telegram until exact persisted Product Decision verification lineage
is available there.

## Verification policy

Every production or safety-critical feature branch must receive successful
exact branch-push verification before merge.

Pull-request merge-ref green status is additional integration evidence and does
not replace branch-head verification.

Every resulting `main` SHA must receive its own successful push verification
before becoming the current exact baseline.

A failed SHA remains failed evidence even if a later SHA passes.

A canonical test manifest proves suite results for its bound SHA; it does not by
itself prove final workflow completion or independent external verification.

## Related implementation and evidence

- `app/services/assistant_action_router_service.py`
- `.github/workflows/verify.yml`
- `tests/test_executor_error_result_lifecycle_v541_v547.py`
- `tests/test_exact_branch_verification_v547.py`
- `project_brain/EXECUTOR_ERROR_RESULT_LIFECYCLE_INTEGRITY_V1.md`
- `project_brain/EXACT_BRANCH_SHA_VERIFICATION_V1.md`
- `project_brain/CURRENT_CHECKPOINT_V541_V547.md`

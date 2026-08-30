# Current Checkpoint v541-v547

Date: 2026-08-30  
Package: Executor Error-Result Lifecycle Integrity V1 + Exact Branch SHA Verification V1  
Architecture Review Required: Yes

## Baseline entering package

Exact verified `main` before implementation:

`73a587641089ad84f59c413c9b71253447bbad3a`

Push Verify #102 for that SHA completed successfully with 1385 passed.

## Completed lifecycle package

PR #233 corrected a persisted execution-lifecycle defect.

Before this package, raised executor exceptions entered the existing FAILED
lifecycle, but an executor result such as `{"error": true, ...}` could continue
to `complete_action()` and be persisted as DONE.

Implemented:

- direct `AssistantActionRouterService.execute()` contract remains unchanged;
- persisted `run()` boundary validates executor results;
- explicit executor error results enter the existing exception/FAILED lifecycle;
- non-dict results fail as `INVALID_EXECUTOR_RESULT`;
- malformed error flags fail closed;
- missing error messages use stable `EXECUTOR_RETURNED_ERROR`;
- arbitrary executor payload fields are not stringified into persisted errors;
- successful results preserve the existing DONE path.

Persisted failure semantics now preserve:

- FAILED action status;
- ACTIVE task status after a failed action;
- pending-action cleanup;
- zero completed progress for the failed action;
- `execution_failed` history;
- FAILED feedback;
- existing retry policy and retry preparation;
- no call to `complete_action()` for error results.

## Exact branch SHA verification correction

During PR verification, a separate CI provenance defect was discovered:
GitHub `pull_request` workflows check out a synthetic PR merge ref by default.
A green PR run therefore must not be described as exact branch-head verification
unless its actual executed revision equals the branch head.

The `Verify` workflow now runs on:

- pull requests;
- explicit `main` pushes;
- all branch pushes;
- workflow dispatch.

This creates separate evidence layers:

1. branch push = exact feature/docs head;
2. pull request = synthetic merge-ref integration;
3. post-squash `main` push = exact merged baseline.

## Failed exact-head evidence

Earlier feature SHA:

`3c49c302b631f888f45e74c3c7c38d2b36522946`

GitHub Actions:

- workflow: `Verify`;
- event: push;
- run number: **106**;
- run id: **33318940284**;
- conclusion: **failure**;
- tests: **1392 passed, 1 failed**.

The failure came from an existing CI contract test requiring an explicit
`- main` trigger after the first branch-push trigger edit used only `"**"`.

The workflow was corrected to retain explicit `main` and add `"**"`.

This SHA remains failed evidence.

## Final exact feature-head verification

Final feature head:

`aca50b561c999da1a6aac47afb1ebfe191617a9a`

GitHub Actions:

- workflow: `Verify`;
- event: **push**;
- run number: **112**;
- run id: **33319126918**;
- actual checkout SHA: `aca50b561c999da1a6aac47afb1ebfe191617a9a`;
- conclusion: **success**;
- tests: **1395 passed**;
- failed: **0**.

Artifact:

`verification-aca50b561c999da1a6aac47afb1ebfe191617a9a`

Artifact id: **9734360032**.

This is the exact branch-head evidence used before merge.

## PR merge-ref integration verification

For the same final branch head:

- PR: **#233**;
- workflow: `Verify`;
- event: **pull_request**;
- run number: **113**;
- run id: **33319129148**;
- conclusion: **success**.

This is synthetic PR merge-ref integration evidence and is intentionally not
promoted as exact branch-head verification.

## Squash merge

Exact resulting `main` SHA:

`81ebdccf88a3959d65607de28c904bb952054139`

## Post-merge exact main verification

GitHub Actions:

- workflow: `Verify`;
- event: **push**;
- run number: **114**;
- run id: **33319235235**;
- actual checkout SHA: `81ebdccf88a3959d65607de28c904bb952054139`;
- status: completed;
- conclusion: success;
- tests: **1395 passed**;
- failed: **0**.

Artifact:

`verification-81ebdccf88a3959d65607de28c904bb952054139`

Artifact id: **9734392896**.

This completed run verifies the exact squash-merge SHA and is not described as
independent external verification.

## Architecture review

Required because the package changes a persisted action execution boundary and
can prevent false DONE state for failed work. The package also exceeded the
approximate 300 changed-line review threshold with tests and documentation.

Review confirmed:

- no new production service/layer;
- no new runtime route;
- direct router compatibility preserved;
- existing exception-based FAILED lifecycle remains the single persistence owner;
- no duplicate task-mutation logic added;
- retry/history/feedback contracts preserved;
- successful completion contract preserved;
- no Product Decision/Product Task Draft execution change;
- no Ozon mutation;
- no persistence-format change;
- no `data/users.json` change.

## Current interpretation

Executor-returned errors can no longer be persisted as successful completed
actions through the normal action runner path.

Exact branch push verification is now mandatory evidence for future feature/docs
heads; PR merge-ref verification remains separate integration evidence.

The next package should be selected from a concrete current product,
production-correctness, operator-usability, observability or release-readiness
gap rather than mechanically extending lifecycle/provenance layers.

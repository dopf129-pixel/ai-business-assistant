# Verification Status

Date: 2026-08-30

## Latest verified baseline entering v458-v462

Latest exact verified `main`:

`bfedb5bf096535440ed39a6ddd3d15a60169c9f8`

Latest merged persistence-verification batch:

`v448-v457: add completed workflow-run evidence binding`

Full-suite verification for this exact SHA:

- GitHub Actions workflow: `Verify`
- event: `push`
- run number: **50**
- conclusion: **success**
- result: **1287 passed**
- failed: **0**
- exact SHA-bound: **yes**
- canonical JSON test manifest generated: **yes**

## Current evidence layers

The project distinguishes:

1. implementation-contract evidence;
2. runtime diagnostic evidence;
3. canonical SHA-bound pytest manifest evidence;
4. caller-supplied exact-SHA CI metadata;
5. explicit completed workflow-run metadata;
6. external verification.

The v448-v457 layer binds item 5 to the exact item-3 manifest and capability provenance.

It still preserves:

`externally_verified=False`

because the repository service validates explicitly supplied completed-run metadata and does not independently fetch GitHub.

## Current persistence verification coverage

The green suite covers:

- load/recovery integrity;
- atomic persistence rollback;
- exact persisted-byte optimistic concurrency;
- POSIX kernel-backed write locking;
- crash-like fd-close lock release;
- persistent inert coordination-file compatibility;
- file fsync, atomic replace and directory fsync;
- operator readiness/default-deny access;
- release observability and deterministic audit;
- capability provenance;
- canonical JUnit → SHA-bound JSON manifest;
- manifest tamper validation;
- test-manifest → capability provenance binding;
- failed-suite evidence preservation;
- completed workflow-run evidence;
- exact SHA/workflow/event/run-id/run-number binding;
- green-tests + failed-final-run distinction;
- contradictory final-success/failed-tests rejection;
- workflow-run capability enrichment and deterministic audit.

## Current release-hardening target

Persistence runtime and evidence mechanics are now mature enough that the next practical step is a release checklist/runbook rather than another evidence abstraction.

The release closure should explain:

- which exact diagnostics an operator checks;
- which blockers prevent release;
- how kernel-lock contention is handled;
- how durability warnings are handled;
- what evidence proves the exact tested revision;
- what remains unverified;
- what must never be auto-retried/deleted/executed.

It must remain read-only and operator-facing.

## Verification infrastructure

The `Verify` workflow produces:

- `revision.txt`;
- `pytest-junit.xml`;
- `test-report.json`.

A completed workflow run is a separate evidence layer from the earlier test manifest.

No test result or run conclusion transfers to another SHA.

## Historical baselines

Historical exact baselines remain evidence only for their own SHAs, including:

- `11883f901d3bb344816735b834392a59185c0c81` — **982 passed**;
- `d0286d45f23e6da17b33afbb269ce109f8a72e3b` — **1197 passed**;
- `3a5bbe9332492073555ef258038e4a4db9e7bf85` — **1234 passed**;
- `1a31258db514e18842f61d240b9040bbf7eeac46` — **1244 passed**;
- `95270b66667bd789a120f3efb3afecb4e50a867d` — **1254 passed**;
- `d18b5a8c5e913477e749c15c3df233cda51d4bc4` — **1265 passed**;
- `379352ad66cf90debc2cebdf701dc2e4ef1170ed` — **1276 passed**.

## Verification policy

Every safety-critical PR must pass full GitHub Actions verification before merge.

Every resulting `main` SHA must receive its own successful push verification before becoming the current exact baseline.

Focused regressions supplement but do not replace the full-suite result.

## Safety

Verification/provenance does not:

- alter Product Decisions;
- enable Product Task Draft execution;
- execute business actions;
- mutate Ozon;
- change mapping authorization;
- change financial calculations;
- modify runtime user/task data.

## Related implementation

- `.github/workflows/verify.yml`
- `app/services/task_persistence_release_observability_service.py`
- `app/services/task_persistence_capability_provenance_service.py`
- `app/services/task_persistence_verification_manifest_provenance_service.py`
- `app/services/task_persistence_workflow_run_evidence_service.py`
- `tests/test_task_persistence_workflow_run_evidence_v448_v457.py`
- `project_brain/TASK_PERSISTENCE_WORKFLOW_RUN_EVIDENCE_V1.md`
- `project_brain/CURRENT_CHECKPOINT_V458_V462.md`

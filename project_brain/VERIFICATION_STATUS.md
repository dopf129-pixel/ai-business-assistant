# Verification Status

Date: 2026-08-30

## Latest verified baseline entering v403-v407

Latest exact verified `main` at the start of this reconciliation:

`1a31258db514e18842f61d240b9040bbf7eeac46`

Latest merged runtime batch at this revision:

`v393-v402: add task persistence release observability`

Full-suite verification for this exact SHA:

- GitHub Actions workflow: `Verify`
- event: `push`
- run number: **35**
- conclusion: **success**
- result: **1244 passed**
- failed: **0**
- exact SHA-bound: **yes**

This is the exact SHA-bound baseline for the start of the v403-v407 docs-only reconciliation. A later docs-only merge creates a different main SHA and requires its own successful push verification.

## Current persistence verification coverage

The current green suite covers:

- terminal task lifecycle/recovery integrity;
- malformed and unreadable task-store handling;
- atomic save rollback;
- exact persisted-byte optimistic concurrency;
- POSIX kernel-backed task write locking;
- crash-like fd-close lock release;
- persistent inert coordination-file compatibility;
- task-file fsync and parent-directory fsync semantics;
- operator readiness;
- default-deny operator access;
- human-readable persistence diagnostics;
- release capability evidence;
- release readiness and blocker/warning projection;
- explicit incident classification;
- deterministic SHA-256 release audit receipts;
- forged release snapshot/incident rejection;
- operator-only `/task-persistence-release` production wiring.

## Verification infrastructure

The repository contains a GitHub Actions full-verification workflow.

The workflow:

1. checks out the exact revision;
2. installs verification dependencies;
3. compiles the application;
4. initializes the deterministic test schema;
5. records revision metadata;
6. runs the full pytest suite;
7. uploads JUnit and revision artifacts.

Ozon credentials are not supplied to the verification environment.

The workflow is development verification only and does not execute seller actions.

## Historical baselines

Earlier exact baselines remain historical evidence for their own SHAs only, including:

- `11883f901d3bb344816735b834392a59185c0c81` — **982 passed**;
- `d0286d45f23e6da17b33afbb269ce109f8a72e3b` — **1197 passed**;
- `3a5bbe9332492073555ef258038e4a4db9e7bf85` — **1234 passed**.

No historical count may be transferred to a later SHA.

## Rule

A test result verifies a repository revision only when:

1. the report is bound to an exact commit SHA;
2. the report identity matches its SHA and test counts;
3. the report SHA equals the revision being described.

A green report for another SHA is `STALE_BASELINE`, not `CURRENT_VERIFIED`.

An unbound report may describe a run but cannot verify any revision.

## Current verification policy

Every safety-critical feature PR must pass the full GitHub Actions verification workflow before merge.

After squash merge, the resulting `main` SHA must receive its own successful push verification before it becomes a current exact verified baseline.

Focused regression files supplement but do not replace the full-suite signal.

## Safety

Verification does not:

- alter Product Decisions;
- enable Product Task Draft execution;
- execute business actions;
- mutate Ozon;
- change mapping authorization;
- change financial calculations;
- modify runtime user data.

## Related implementation

- `.github/workflows/verify.yml`
- `requirements-dev.txt`
- `app/services/terminal_safe_assistant_task_service.py`
- `app/services/task_persistence_operational_service.py`
- `app/services/task_persistence_release_observability_service.py`
- `tests/test_task_persistence_release_observability_v393_v402.py`
- `project_brain/TASK_PERSISTENCE_RELEASE_OBSERVABILITY_V1.md`
- `project_brain/CURRENT_CHECKPOINT_V403_V407.md`

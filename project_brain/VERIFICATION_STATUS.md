# Verification Status

Date: 2026-08-30

## Latest verified baseline entering v353-v357

Latest exact verified `main` at the start of this reconciliation:

`d0286d45f23e6da17b33afbb269ce109f8a72e3b`

Latest merged batch at this revision:

`v343-v352: add task persistence crash durability evidence`

Full-suite verification for this exact SHA:

- GitHub Actions workflow: `Verify`
- event: `push`
- run number: **21**
- conclusion: **success**
- result: **1197 passed**
- failed: **0**
- exact SHA-bound: **yes**

This is the exact SHA-bound baseline for the start of the v353-v357 docs-only reconciliation. A later docs-only merge creates a new main SHA and must receive its own push verification before that SHA is called current-verified.

## Verification infrastructure

The repository now contains a GitHub Actions full-verification workflow.

The workflow:

1. checks out the exact revision;
2. installs the verification dependencies;
3. compiles the application;
4. initializes the deterministic test schema;
5. records revision metadata;
6. runs the full pytest suite;
7. uploads JUnit and revision artifacts.

Ozon credentials are not supplied to the verification environment.

The workflow is development verification only and does not execute seller actions.

## Historical baseline

The earlier user-confirmed baseline:

- SHA: `11883f901d3bb344816735b834392a59185c0c81`
- result: **982 passed**
- failed: **0**

remains valid historical evidence for that SHA only. It is superseded as the current baseline by the exact verified main above.

## Rule

A test result verifies a repository revision only when:

1. the report is bound to an exact commit SHA;
2. the report identity matches its SHA and test counts;
3. the report SHA equals the revision being described.

A green report for another SHA is `STALE_BASELINE`, not `CURRENT_VERIFIED`.

An unbound report may describe a run but cannot verify any revision.

## Current verification policy

Every safety-critical feature PR must pass the full GitHub Actions verification workflow before merge.

After squash merge, the resulting `main` SHA must receive its own successful push verification before it becomes the new current verified baseline.

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
- `tests/test_ci_verification_foundation_v269_v278.py`
- `app/services/assistant_project_verification_service.py`
- `project_brain/CURRENT_CHECKPOINT_V353_V357.md`

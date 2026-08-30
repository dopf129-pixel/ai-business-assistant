# Verification Status

Date: 2026-08-30

## Latest verified baseline entering v428-v432

Latest exact verified `main` at the start of this reconciliation:

`d18b5a8c5e913477e749c15c3df233cda51d4bc4`

Latest merged verification batch:

`v418-v427: add SHA-bound CI verification manifest`

Full-suite verification for this exact SHA:

- GitHub Actions workflow: `Verify`
- event: `push`
- run number: **41**
- conclusion: **success**
- result: **1265 passed**
- failed: **0**
- exact SHA-bound: **yes**
- canonical JSON artifact: **yes**

Artifact:

`verification-d18b5a8c5e913477e749c15c3df233cda51d4bc4`

The artifact contains the workflow verification payload generated after pytest and is bound to this exact SHA by artifact name and workflow metadata.

## Current verification coverage

The green suite now covers:

- task persistence integrity, concurrency, kernel locking and crash durability;
- operator-only persistence diagnostics and release observability;
- capability provenance and exact-SHA CI metadata binding;
- deterministic release/provenance audit receipts;
- CI JUnit normalization;
- canonical SHA-bound test-report identity;
- deterministic CI verification-manifest identity;
- tampered manifest rejection;
- current-vs-stale project verification;
- real workflow generation of `verification-artifacts/test-report.json`.

## Verification infrastructure

The `Verify` workflow:

1. checks out the exact revision;
2. installs explicit verification dependencies;
3. compiles the application;
4. initializes deterministic test schema;
5. records revision metadata;
6. runs full pytest with JUnit output;
7. generates canonical SHA-bound `test-report.json` with `if: always()`;
8. uploads revision metadata, JUnit and JSON manifest with `if: always()`.

Workflow permissions remain `contents: read`.

Ozon credentials are explicitly empty.

## Evidence semantics

A successful workflow run verifies only its exact recorded commit SHA.

A green report for another revision is `STALE_BASELINE`.

The canonical JSON manifest is stronger than manually transcribed counts because its identity is deterministically recomputed from exact SHA, counts and workflow metadata.

The repository runtime does not automatically fetch GitHub artifacts. Any future provenance import must be explicit, locally validated and exact-SHA matched.

Validation of a local/caller-supplied artifact does not by itself justify `externally_verified=True`.

## Historical baselines

Earlier exact baselines remain evidence only for their own SHAs, including:

- `11883f901d3bb344816735b834392a59185c0c81` — **982 passed**;
- `d0286d45f23e6da17b33afbb269ce109f8a72e3b` — **1197 passed**;
- `3a5bbe9332492073555ef258038e4a4db9e7bf85` — **1234 passed**;
- `1a31258db514e18842f61d240b9040bbf7eeac46` — **1244 passed**;
- `95270b66667bd789a120f3efb3afecb4e50a867d` — **1254 passed**.

## Current verification policy

Every safety-critical feature PR must pass full GitHub Actions verification before merge.

After squash merge, the resulting `main` SHA must receive its own successful push verification before it becomes the current exact verified baseline.

Focused regressions supplement but do not replace the full-suite signal.

## Safety

Verification does not:

- alter Product Decisions;
- enable Product Task Draft execution;
- execute business actions;
- mutate Ozon;
- change mapping authorization;
- change financial calculations;
- modify runtime user/task data.

## Related implementation

- `.github/workflows/verify.yml`
- `app/services/assistant_ci_verification_manifest_service.py`
- `app/ci_verification_manifest.py`
- `app/services/assistant_project_verification_service.py`
- `app/services/task_persistence_capability_provenance_service.py`
- `tests/test_ci_verification_manifest_v418_v427.py`
- `project_brain/CI_VERIFICATION_MANIFEST_V1.md`
- `project_brain/CURRENT_CHECKPOINT_V428_V432.md`

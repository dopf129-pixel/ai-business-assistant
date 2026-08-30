# Verification Status

Date: 2026-08-30

## Latest verified baseline entering v443-v447

Latest exact verified `main`:

`379352ad66cf90debc2cebdf701dc2e4ef1170ed`

Latest merged capability-provenance batch:

`v433-v442: bind canonical verification manifests to persistence capability provenance`

Full-suite verification for this exact SHA:

- GitHub Actions workflow: `Verify`
- event: `push`
- run number: **45**
- conclusion: **success**
- result: **1276 passed**
- failed: **0**
- exact SHA-bound: **yes**
- canonical JSON test manifest generated: **yes**

## Current evidence layers

The project now distinguishes:

1. implementation-contract evidence;
2. runtime diagnostic evidence;
3. canonical SHA-bound pytest manifest evidence;
4. caller-supplied exact-SHA CI metadata;
5. final GitHub workflow-run conclusion evidence;
6. external verification.

These are not interchangeable.

The v433-v442 bridge binds layer 3 into persistence capability provenance.

It deliberately does **not** claim layer 5 or layer 6.

## Current persistence verification coverage

The green suite covers:

- persistence load/recovery integrity;
- exact persisted-byte optimistic concurrency;
- POSIX kernel-backed write locking;
- file fsync, atomic replace and parent-directory fsync;
- operator readiness and default-deny access;
- release observability and deterministic release audit;
- capability provenance;
- canonical JUnit → SHA-bound JSON test manifest;
- manifest identity/tamper validation;
- exact-SHA project verification;
- verification-manifest → capability-provenance import;
- failed-suite evidence preservation;
- cross-snapshot lineage rejection;
- explicit distinction between test-suite evidence and final CI-run success.

## Verification infrastructure

The `Verify` workflow produces:

- `verification-artifacts/revision.txt`;
- `verification-artifacts/pytest-junit.xml`;
- `verification-artifacts/test-report.json`.

The JSON manifest is generated after pytest and before the full job is complete.

Therefore:

- `test_suite_passed=True` may be proven by the manifest;
- final workflow-run success must be established separately from completed-run evidence.

## Current next verification target

Add a development-side final workflow-run evidence contract that requires exact:

- head SHA;
- workflow name;
- event;
- run ID;
- run number;
- completed status;
- success conclusion.

It must bind to the same revision/test manifest without network access from production runtime and without setting `externally_verified=True` merely because metadata was validated.

## Historical baselines

Historical exact baselines remain evidence only for their own SHAs, including:

- `11883f901d3bb344816735b834392a59185c0c81` — **982 passed**;
- `d0286d45f23e6da17b33afbb269ce109f8a72e3b` — **1197 passed**;
- `3a5bbe9332492073555ef258038e4a4db9e7bf85` — **1234 passed**;
- `1a31258db514e18842f61d240b9040bbf7eeac46` — **1244 passed**;
- `95270b66667bd789a120f3efb3afecb4e50a867d` — **1254 passed**;
- `d18b5a8c5e913477e749c15c3df233cda51d4bc4` — **1265 passed**.

## Verification policy

Every safety-critical PR must pass full GitHub Actions verification before merge.

Every resulting `main` SHA must receive its own successful push verification before it becomes current verified baseline.

No test count or workflow conclusion is transferable to another revision.

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
- `app/services/assistant_ci_verification_manifest_service.py`
- `app/services/assistant_project_verification_service.py`
- `app/services/task_persistence_capability_provenance_service.py`
- `app/services/task_persistence_verification_manifest_provenance_service.py`
- `tests/test_task_persistence_verification_manifest_provenance_v433_v442.py`
- `project_brain/TASK_PERSISTENCE_VERIFICATION_MANIFEST_PROVENANCE_V1.md`
- `project_brain/CURRENT_CHECKPOINT_V443_V447.md`

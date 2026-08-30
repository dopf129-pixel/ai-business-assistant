# Task Persistence Release Closure V1

Date: 2026-08-30  
Stages: v463-v472  
Architecture Review Required: Yes

## Goal

Close the kernel-backed task-persistence hardening track with one deterministic, read-only release-review checklist and operator runbook built from existing canonical runtime and verification evidence.

This is **release review readiness**, not deployment and not release approval.

## Inputs

The closure service consumes:

1. `TaskPersistenceReleaseObservabilityService.build_release_report()`;
2. `TaskPersistenceWorkflowRunEvidenceService.build_report()`;
3. the exact verification manifest;
4. the exact revision ID;
5. explicit completed workflow-run metadata.

No network fetch is performed.

## v463 — Release-review closure

A clean report may produce:

`READY_FOR_RELEASE_REVIEW`

only when all required checks are satisfied and there are no runtime warnings.

This state does not mean:

- deployed;
- release approved;
- externally verified;
- seller action executed.

## v464 — Capability checklist

All six persistence capabilities are required:

- optimistic concurrency;
- kernel lock guard;
- atomic replace;
- file fsync;
- directory fsync;
- coordination-file ownership neutrality.

Any false capability blocks review.

## v465 — Durability warning handling

`TASK_DIRECTORY_FSYNC_ERROR` blocks release review even though the underlying write may already be committed.

The runbook requires manual filesystem/durability inspection.

It never claims that rename alone proves crash durability.

## v466 — Lock contention handling

`TASK_FILE_WRITE_LOCKED` blocks release review.

The runbook instructs the operator to wait for the active writer and rebuild the checklist.

It explicitly does not authorize coordination-file deletion.

## v467 — Failed test manifest

A canonical failed pytest manifest blocks release review.

Failed test evidence is preserved rather than converted to an infrastructure error or hidden.

## v468 — Post-test failure

Green pytest plus a failed final workflow run also blocks review.

The checklist keeps separate checks for:

- test suite success;
- final workflow-run success;
- absence of post-test failure.

## v469 — Manual release review

A clean checklist ends with:

`MANUAL_RELEASE_REVIEW`

The final step says that deployment and approval are outside this report.

All runbook steps are manual.

## v470 — Deterministic closure audit

The closure ID binds:

- exact revision;
- runtime release audit;
- workflow provenance audit;
- verification-manifest ID;
- test-report ID;
- run ID / run number;
- exact checklist;
- blockers;
- warnings;
- closure state.

The audit receipt additionally binds the runbook and no-deployment/no-execution flags.

No timestamp is fabricated.

## v471 — Safety boundary

Every closure report keeps:

- `externally_verified=False`;
- `deployment_allowed=False`;
- `release_approved=False`;
- `automatic_retry_allowed=False`;
- `automatic_lock_recovery_allowed=False`;
- `manual_lock_removal_allowed=False`;
- `business_execution_ready=False`;
- `mutation_ready=False`;
- `read_only=True`;
- `deployed=False`;
- `executed=False`.

## v472 — Data minimization

Closure evidence contains no:

- task-store path;
- user ID;
- PID;
- fabricated observation timestamp.

The report is derived from already sanitized canonical evidence.

## What this package never does

It never:

- deploys code;
- approves a release;
- retries writes;
- removes a coordination file;
- mutates task persistence;
- executes Product Decisions;
- executes Product Task Drafts;
- mutates Ozon;
- changes mapping authorization;
- changes financial calculations;
- modifies `data/users.json`.

## Release-review interpretation

### READY_FOR_RELEASE_REVIEW

Means the current canonical runtime checks and exact verification evidence satisfy the checklist.

A human may review the release.

### BLOCKED

Means at least one required check or runtime warning remains unresolved.

The operator must resolve the evidence and rebuild the checklist.

### Deployment

Not represented by this package.

### External verification

Not represented by this package.

## Verification

Focused regressions cover:

1. clean release-review readiness;
2. exact six-capability checklist;
3. durability warning runbook;
4. real lock contention;
5. failed pytest evidence;
6. green tests + failed final run;
7. manual-review terminal step;
8. deterministic audit and forged lineage rejection;
9. no business/execution permissions;
10. no path/PID/timestamp leakage.

Full GitHub Actions verification is required before merge.

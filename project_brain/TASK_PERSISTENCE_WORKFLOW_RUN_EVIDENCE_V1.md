# Task Persistence Final Workflow-Run Evidence V1

Date: 2026-08-30  
Stages: v448-v457  
Architecture Review Required: Yes

## Goal

Bind explicit completed GitHub Actions workflow-run metadata to the already canonical SHA-bound verification manifest and task-persistence capability provenance.

This layer stays separate from the earlier test-report manifest because `test-report.json` is generated before the GitHub job has fully completed.

No production runtime GitHub fetch is introduced.

## v448 — Completed-run evidence schema

`TaskPersistenceWorkflowRunEvidenceService.build_run_evidence()` accepts only explicit metadata containing:

- exact 40-character `head_sha`;
- workflow `Verify`;
- supported event;
- positive run ID;
- positive run number;
- `status=completed`;
- supported conclusion.

Machine status and GitHub run status are separate fields:

- machine status: `TASK_PERSISTENCE_WORKFLOW_RUN_EVIDENCE_READY`;
- run status: `run_status=completed`.

## v449 — Fail-closed metadata validation

Non-completed, malformed or unsupported run evidence is rejected.

The service does not infer completion from a test manifest or from a run number alone.

## v450 — Exact manifest binding

Completed-run evidence binds to a canonical verification manifest only when all of these match exactly:

- head SHA;
- workflow;
- event;
- run ID;
- run number.

No fuzzy or latest-main matching is used.

## v451 — Post-test failure semantics

A test manifest may be green while the final workflow run is not successful.

This can happen when a later step fails after pytest.

The contract preserves this as:

- `test_suite_passed=True`;
- `final_ci_run_success_reported=False`;
- `post_test_failure_possible=True`.

The test result is not rewritten as failed and the final run is not rewritten as successful.

## v452 — Contradictory success rejection

Under the current workflow contract, a final successful run with a canonical failed pytest manifest is contradictory.

That combination fails closed as:

`TASK_PERSISTENCE_WORKFLOW_RUN_STATE_CONTRADICTORY`.

## v453 — Exact run identity

A mismatch in any of:

- SHA;
- run ID;
- run number;
- workflow;
- event

breaks the manifest binding.

## v454 — Capability provenance enrichment

The service recomputes the existing verification-manifest provenance and enriches each canonical capability with:

- `completed_workflow_run_bound=True`;
- `final_ci_run_success_reported=<bool>`;
- `externally_verified=False`.

The original capability identity and evidence mode remain unchanged.

## v455 — Deterministic audit

The final audit binds:

- capability manifest ID;
- verification manifest ID;
- test report ID;
- verification-provenance binding ID;
- workflow-manifest binding ID;
- workflow-run evidence ID;
- revision;
- run ID and run number;
- test-suite outcome;
- final-run outcome;
- capability list.

Forging any key lineage ID invalidates the audit.

The receipt is deterministic SHA-256 local evidence.

## v456 — Evidence identity

Completed-run evidence has its own deterministic ID.

Changing conclusion or other bound fields without recomputing that identity fails validation.

## v457 — Safety and wiring

This package is not automatically wired into `create_telegram_core()`.

The service performs no GitHub network request.

It accepts explicit completed-run metadata supplied by development tooling.

Every report keeps:

- `network_fetch_performed=False`;
- `externally_verified=False`;
- `automatic_retry_allowed=False`;
- `automatic_lock_recovery_allowed=False`;
- `manual_lock_removal_allowed=False`;
- `business_execution_ready=False`;
- `mutation_ready=False`;
- `read_only=True`;
- `executed=False`.

This package never:

- writes task persistence;
- executes Product Decisions;
- executes Product Task Drafts;
- calls Ozon mutation APIs;
- changes mapping authorization;
- changes financial calculations;
- modifies `data/users.json`.

## Evidence semantics

### Test-suite evidence

Comes from canonical `test-report.json`.

### Completed workflow-run evidence

Comes from explicit metadata for a completed GitHub Actions run.

### External verification

Still not provided here.

The service validates supplied completed-run metadata but does not independently fetch GitHub, therefore:

`externally_verified=False`.

## Verification

Focused regressions cover:

1. completed-run evidence schema;
2. malformed/non-completed rejection;
3. exact manifest binding;
4. post-test failure preservation;
5. contradictory final-success/failed-tests rejection;
6. SHA/run identity mismatch;
7. capability enrichment;
8. deterministic report/audit;
9. forged capability lineage rejection;
10. tampered run evidence rejection;
11. safety and no production auto-wiring.

Full GitHub Actions verification is required before merge.

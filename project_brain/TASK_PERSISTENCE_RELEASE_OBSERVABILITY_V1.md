# Task Persistence Release Observability V1

Date: 2026-08-30  
Stages: v393-v402  
Architecture Review Required: Yes

## Goal

Make the kernel-backed task persistence boundary release-observable without introducing autonomous recovery or a second persistence owner.

The package turns existing persistence evidence into a deterministic release-readiness snapshot, incident classification and audit receipt.

No source timestamp is invented.

## v393 — Capability evidence

`TerminalSafeAssistantTaskService.get_persistence_diagnostics()` now exposes explicit boolean evidence for the persistence mechanics already implemented in code:

- `optimistic_concurrency_guard=True`;
- `atomic_replace_required=True`;
- `file_fsync_required=True`;
- `directory_fsync_required=True`;
- `coordination_file_ownership_neutral=True`.

Kernel-lock capability comes from `get_write_lock_diagnostics()`.

These fields describe implementation requirements/guards. They do not claim a particular business task was executed.

## v394 — Release snapshot

`TaskPersistenceReleaseObservabilityService.build_snapshot()` combines:

1. canonical operational readiness;
2. persistence capability diagnostics;
3. kernel-lock diagnostics.

The result is:

`TASK_PERSISTENCE_RELEASE_SNAPSHOT_READY`

with:

- `release_ready`;
- blockers/warnings;
- exact capability map;
- missing capability names;
- current lock inspection state;
- last save and lock-release evidence.

## v395 — Capability gate

A required capability set to false becomes:

`RELEASE_CAPABILITY_MISSING:<capability>`

and blocks release readiness.

If kernel locking is unavailable, the release snapshot fails closed rather than treating the environment as writable.

## v396 — Incident classification

Incident categories come only from explicit blocker/warning evidence.

Current categories include:

- `LOCK_CONTENTION`;
- `LOCK_INSPECTION`;
- `STORE_INTEGRITY`;
- `RELEASE_CAPABILITY`;
- `DURABILITY`;
- `LOCK_RELEASE`;
- `STORE_RECONCILIATION`;
- `SAVE_FAILURE`.

Coordination-file presence alone is not an incident category.

## v397 — Deterministic audit receipt

`build_audit_receipt()` creates a SHA-256 receipt from canonical release evidence.

The receipt:

- is deterministic for identical evidence;
- contains no path;
- contains no user ID;
- contains no exception text;
- contains no PID;
- fabricates no timestamp;
- does not persist itself.

The receipt proves only that the supplied canonical diagnostic evidence was internally consistent at the time it was built.

It is not external verification.

## v398 — Operator presentation

Authorized release reports receive human-readable Russian guidance through the existing persistence presentation service.

Ready, contention, durability and generic blocker cases are separated without changing the underlying machine-readable evidence.

## v399 — Operator-only route

New explicit route:

`/task-persistence-release`

Additional text tokens include:

- `готовность persistence`;
- `готовность хранилища задач`;
- `task persistence release`.

Authorization is checked before the release service is called.

The existing default-deny operator allowlist is reused.

## v400 — Production Telegram composition

`create_telegram_core()` constructs exactly one `TaskPersistenceOperationalService`.

The same instance feeds:

- the current operator status route;
- `TaskPersistenceReleaseObservabilityService`.

Both remain bound to the same hardened `TerminalSafeAssistantTaskService`.

No parallel persistence owner or write adapter is created.

## v401 — Forgery resistance

Release snapshot validation recomputes:

- exact capability key set;
- missing-capability list;
- required blocker presence;
- `release_ready`.

Incident validation recomputes:

- incident categories;
- incident detection;
- human-review requirement;
- blocker/warning identity.

A forged snapshot or incident is rejected before an audit receipt is produced.

## v402 — Safety boundary

Every release artifact keeps:

- `automatic_retry_allowed=False`;
- `automatic_lock_recovery_allowed=False`;
- `manual_lock_removal_allowed=False`;
- `business_execution_ready=False`;
- `mutation_ready=False`;
- `read_only=True`;
- `executed=False`.

This package never:

- retries a failed save;
- deletes the coordination file;
- infers lock owner, age or staleness;
- executes recovered intent;
- executes Product Decisions;
- executes Product Task Drafts;
- mutates Ozon;
- changes mapping authorization;
- changes finance calculations;
- writes `data/users.json`.

## Evidence semantics

The release audit receipt is deterministic local evidence.

It does not claim:

- external verification;
- source freshness;
- deployment success;
- process liveness beyond explicit current lock evidence;
- seller business execution.

No observation timestamp is generated because the service has no authoritative timestamp source for this evidence.

## Verification

Focused tests cover:

1. release capability diagnostics;
2. clean release readiness;
3. missing kernel-lock capability;
4. real cross-instance contention;
5. deterministic audit receipt;
6. operator presentation;
7. default-deny release route;
8. Telegram composition;
9. forged evidence rejection;
10. invariant safety flags.

Full GitHub Actions verification is required before merge.

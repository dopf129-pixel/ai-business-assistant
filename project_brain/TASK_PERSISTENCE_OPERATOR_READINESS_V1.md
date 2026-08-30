# Task Persistence Operator Readiness V1

Date: 2026-08-30  
Stages: v358-v367  
Architecture Review Required: Yes

## Goal

Expose the hardened task persistence state to an operator through a deterministic read-only runtime path without enabling lock deletion, persistence recovery, business execution, or Ozon mutation.

The production task owner already protects load, save, concurrency, write locking and crash durability. Before this batch, those diagnostics were only available as internal methods and were not projected into an operator-facing readiness state.

## v358 — Write-lock inspection

`TerminalSafeAssistantTaskService.get_write_lock_diagnostics()` performs a read-only `stat` check of the internal lock artifact.

Canonical states:

- `ABSENT`: `lock_present=False`, ownership `NONE`;
- `PRESENT`: `lock_present=True`, ownership `UNKNOWN`;
- `CHECK_ERROR`: `lock_present=None`, ownership `UNKNOWN`.

A check error never normalizes to false absence.

The contract never infers lock age, owner, PID, liveness or staleness.

`stale_proven=False` always.

## v359 — Operational projection

`TaskPersistenceOperationalService` consumes exactly three read-only sources from the production owner:

1. load diagnostics;
2. persistence diagnostics;
3. write-lock diagnostics.

It returns one deterministic operator state:

- `READY`;
- `WARNING`;
- `BLOCKED`.

This state is operational visibility only. It is not write permission.

## v360 — Load blockers

`UNREADABLE` and `INVALID_ROOT` task stores are blockers.

Loaded stores with reconciliation issues are warnings rather than silently clean states.

Missing stores may be `READY` because absence is a legitimate empty persistence state.

## v361 — Save blockers and warnings

A canonical `FAILED` last-save state is blocking.

A post-commit directory-fsync warning remains a warning, not a failed write.

Lock-release degradation remains a separate warning dimension.

## v362 — Unowned lock boundary

A present lock produces:

- blocker `TASK_WRITE_LOCK_PRESENT_UNOWNED`;
- next action `VERIFY_WRITE_LOCK_OWNER_MANUALLY`;
- `write_lock_stale_proven=False`;
- `automatic_lock_recovery_allowed=False`;
- `manual_lock_removal_allowed=False`.

The projection does not authorize deletion even after telling an operator what must be verified.

A later explicit lock-removal authorization protocol would require a separate architecture.

## v363 — Fail-closed diagnostic consistency

The operational service does not trust arbitrary supplied diagnostic dictionaries.

It validates canonical relationships including:

- load state ↔ issue list ↔ loaded count;
- save state ↔ issue code ↔ rollback flag;
- lock state ↔ presence ↔ ownership ↔ manual intervention;
- all existing persistence safety guards.

Contradictory evidence returns a blocked invalid-diagnostics result.

## v364 — Explicit runtime route

`AssistantTaskPersistenceOperationalRuntimeService` handles only explicit persistence-status phrases such as:

- `статус хранилища задач`;
- `диагностика хранилища задач`;
- `task persistence status`;
- `task persistence diagnostics`.

Unrelated requests return `None` and continue through the existing assistant flow.

## v365 — Entry routing

`AssistantEntryService` accepts the runtime as an optional constructor dependency.

When present, the explicit persistence route is checked before normal business planning.

No route is activated without dependency injection.

## v366 — Production Telegram composition

`create_telegram_core()` wires the operational runtime to the exact `TerminalSafeAssistantTaskService` instance used by task execution/recovery.

The factory now accepts optional `task_service=None` DI.

Default behavior remains the same hardened owner. Explicit injection allows isolated tests and controlled composition without touching production task data.

## v367 — Safety audit

The operator route always keeps:

- `read_only=True`;
- `executed=False`;
- `business_execution_ready=False`;
- `mutation_ready=False`;
- `automatic_lock_recovery_allowed=False`;
- `manual_lock_removal_allowed=False`.

It never:

- deletes a lock;
- retries a save;
- writes task state;
- executes recovered intent;
- executes Product Decisions;
- executes Product Task Drafts;
- calls Ozon mutation APIs;
- changes mapping authorization;
- changes finance calculations;
- touches `data/users.json`.

## Important stale-lock rule

A lock being present is not evidence that it is stale.

File age, observation time, process assumptions or an empty lock file are not enough to prove ownership or safe deletion.

This version provides operator visibility and guidance only.

## Verification

Focused tests cover:

1. absent lock;
2. present lock without owner/stale inference;
3. lock-check uncertainty;
4. clean readiness;
5. unowned-lock blocker;
6. durability-warning semantics;
7. forged diagnostic rejection;
8. explicit runtime routing;
9. entry routing before business flow;
10. production Telegram composition with isolated DI.

Full GitHub Actions verification is required before merge.

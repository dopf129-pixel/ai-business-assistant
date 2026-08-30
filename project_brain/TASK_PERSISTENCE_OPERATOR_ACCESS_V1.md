# Task Persistence Operator Access and Presentation V1

Date: 2026-08-30  
Stages: v368-v377  
Architecture Review Required: Yes

## Goal

Restrict the task persistence operational route to explicitly configured operators and make authorized results human-readable without weakening the persistence safety boundary.

The v358-v367 route exposed only non-sensitive persistence diagnostics, but it was reachable by any Telegram user who knew the diagnostic phrase. This batch changes the route to default-deny.

## v368 — Default-deny operator policy

`TaskPersistenceOperatorAccessPolicy` accepts an explicit list of positive integer Telegram user IDs.

With no configured IDs:

- access is denied;
- the route remains present but does not read persistence diagnostics;
- no operator ID is inferred from profile or task ownership.

## v369 — Exact user identity

Only exact positive integer IDs are accepted.

The policy rejects:

- zero;
- negative values;
- booleans;
- strings;
- `None`.

The policy diagnostics expose only:

- whether access is configured;
- count of authorized IDs;
- default-deny status.

The IDs themselves are never returned.

## v370 — Authorization before diagnostics

`AssistantTaskPersistenceOperationalRuntimeService` now receives `user_id`.

The sequence is:

1. normalize the explicit operator command;
2. check operator authorization;
3. only if authorized, build persistence diagnostics;
4. only if diagnostics are valid, render the operator presentation.

Unauthorized requests do not call the operational service.

## v371 — Production composition default deny

`create_telegram_core()` accepts:

`task_persistence_operator_user_ids=None`

Default `None` means an empty allowlist and denied access.

Enabling the operator route requires explicit composition-time DI.

The existing hardened task owner remains mandatory; unsafe task-service injection is still rejected.

## v372 — Human-readable ready state

Authorized `READY` results include a Russian `message` suitable for the existing Telegram response formatter.

The message states that persistence has no critical blockers while also preserving that automatic lock recovery is disabled.

## v373 — Unowned lock guidance

For `TASK_WRITE_LOCK_PRESENT_UNOWNED`, the operator message explicitly says:

- owner is not proven;
- stale status is not proven;
- do not delete the lock automatically;
- manually verify ownership and deletion safety first.

The message never includes the lock path, PID or inferred age.

## v374 — Durability warning presentation

`TASK_DIRECTORY_FSYNC_ERROR` is presented as post-commit crash-durability uncertainty.

The message preserves the existing semantic truth:

- the write completed;
- directory durability could not be confirmed;
- it is not presented as a rolled-back or failed write.

## v375 — Explicit operator command

Authorized operators may use:

`/task-persistence`

The existing text phrases continue to work.

Unrelated text returns `None` and continues through the normal assistant flow.

## v376 — user_id propagation

`AssistantEntryService` passes `user_id` only to the task persistence operational runtime.

Other runtime routes retain their existing call signatures and behavior.

## v377 — Safety audit

Authorized and unauthorized results both preserve:

- `read_only=True`;
- `executed=False`;
- `business_execution_ready=False`;
- `mutation_ready=False`;
- `automatic_lock_recovery_allowed=False`;
- `manual_lock_removal_allowed=False`.

The route never:

- deletes a lock;
- retries a persistence operation;
- exposes configured operator IDs;
- exposes task store paths;
- infers PID, lock owner, lock age or stale state;
- executes Product Decisions;
- executes Product Task Drafts;
- calls Ozon mutation APIs;
- changes mapping authorization;
- changes finance calculations;
- adds any direct write to `data/users.json`.

Existing shared Telegram user-context behavior is unchanged by this package; the operator access/runtime services themselves do not use user storage as an authorization source.

## Operator configuration boundary

This version intentionally does not load the allowlist from `data/users.json`, task state, memory or inferred roles.

Operator IDs must be explicitly supplied to the composition root.

A future external configuration source would require its own review.

## Verification

Focused tests cover:

1. default deny;
2. strict positive-integer identity;
3. denial before diagnostic access;
4. default-deny Telegram composition;
5. ready-state presentation;
6. unowned-lock safety message;
7. durability warning semantics;
8. explicit slash command;
9. user_id propagation;
10. authorized production composition without ID/path leakage.

Full GitHub Actions verification is required before merge.

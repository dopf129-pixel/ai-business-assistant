# Task Persistence Integrity v248-v255

## Goal

Close restart/recovery gaps in the existing long-running task implementation without introducing a parallel task engine or new autonomous execution behavior.

The existing `AssistantTaskService` remains the owner of persistent task state.

## v248 — Atomic task-state writes

`AssistantTaskService.save()` now writes JSON to a same-directory temporary file, flushes and fsyncs it, then replaces the target with `os.replace`.

If replacement fails:

- the previous task file remains intact;
- the temporary file is cleaned up;
- the exception is not hidden.

Loaded top-level JSON must be a mapping; malformed top-level shapes fail closed to an empty in-memory task set.

## v249 — Persist failed actions

`fail_action()` now:

- stores `FAILED` plus the error;
- clears the matching `pending_action`;
- persists immediately.

Clearing pending state is important because after JSON reload the serialized pending copy is no longer the same Python object as the canonical action entry.

A failed action therefore cannot remain falsely recoverable as an in-progress pending action.

## v250 — Persist replan requests

`request_replan()` now persists:

- `replan_requested=True`;
- the explicit replan reason.

These flags now survive service restart.

## v251 — Owner-controlled retry preparation

New `AssistantTaskService.prepare_retry_action()` owns the retry state transition:

- only a `FAILED` action can be prepared;
- retry attempt must be a positive integer;
- status becomes `NEW`;
- error/retry metadata is cleared;
- pending action is cleared;
- state is persisted.

`AssistantActionExecutionService.retry_action()` delegates to this owner method when available. A legacy fallback still calls `save()` when the injected task service exposes it.

## v252 — Owner-controlled applied replanning

New `AssistantTaskService.apply_replan()` owns replacement of the persisted action plan:

- action list must be a list;
- the plan is deep-copied into task state;
- `replanned=True`;
- `replan_requested=False`;
- pending action is cleared;
- optional reason is retained;
- state is persisted.

`AssistantActionExecutionService.replan_failed_action()` delegates to this owner method when available.

## v253 — Malformed persisted shape fails closed

A syntactically valid JSON file with a non-mapping top level is not treated as task state.

No task is fabricated from malformed storage.

## v254 — Recovery remains non-executing

Recovery of FAILED/replanned/retry-prepared state only restores metadata.

It never implicitly invokes an executor or completes an action.

## v255 — Mutation integrity regressions

Focused tests cover:

- invalid retry attempts;
- external mutation of a replanning result after persistence;
- failure/retry/replan state across fresh service instances;
- atomic replacement failure preserving the old file.

## Existing execution boundary

This work hardens persistence of the legacy task engine. It does not connect Product Decisions or Product Task Drafts to the legacy Action Executor.

Product Decision invariants remain unchanged:

- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

No mutating Ozon API path is added.

## Storage boundary

This change touches `data/tasks.json` behavior only through the existing `AssistantTaskService` default path.

It does not modify `data/users.json`.

## Validation status

Focused tests are added in:

`tests/test_task_persistence_integrity_v248_v255.py`

The full repository pytest suite is not claimed as executed for this branch in the connector-only environment. The last confirmed full-suite baseline remains SHA-bound in `project_brain/VERIFICATION_STATUS.md`.

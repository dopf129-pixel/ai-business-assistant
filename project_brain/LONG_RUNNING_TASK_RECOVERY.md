# Long-running Task Recovery

## Status

Validated on 2026-08-29.

The existing `AssistantTaskService` already provides the persistence primitives required for long-running tasks. This stage therefore locks the recovery behavior with regression tests instead of introducing a parallel task service.

## Recovery contract

- task state is persisted and loaded again when `AssistantTaskService` is recreated;
- an `IN_PROGRESS` pending action remains pending after restart and is returned by `get_current_action()`;
- a paused task remains `PAUSED` after restart and a later resume is persisted;
- completed action progress survives restart;
- after completed work, the next unfinished `NEW` action can continue;
- service recovery never executes a pending action implicitly.

## Validation

Added `tests/test_long_running_task_recovery.py` covering four restart/recovery scenarios.

Full repository validation reported by the project owner:

`388 passed`

## Safety boundary

Recovery restores persisted task state only. It does not authorize or implicitly perform external actions. Product Decision execution remains disconnected from the legacy Action Executor and mutating Ozon APIs unless a separate business decision explicitly changes that boundary.

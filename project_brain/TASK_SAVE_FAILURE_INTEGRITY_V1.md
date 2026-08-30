# Task Save Failure Integrity v1

Date: 2026-08-30

Stages: v313-v322

## Goal

Prevent the production task owner from keeping in-memory state ahead of durable task persistence after an atomic write failure.

## Save behavior

`TerminalSafeAssistantTaskService.save()` delegates to the existing atomic JSON save implementation.

On success it records only non-sensitive persistence metadata:

- `last_save_state=SUCCEEDED`;
- no save issue;
- no rollback claim.

On failure it:

1. records `last_save_state=FAILED` and stable issue code `TASK_FILE_WRITE_ERROR`;
2. reloads the durable task file through the hardened read/validation boundary;
3. restores in-memory task state to whatever is actually durable (or an empty fail-closed state if the source is unavailable);
4. marks `last_save_rolled_back=True`;
5. re-raises the original exception to the caller.

The service therefore does not convert a failed persistence attempt into a successful task API result.

## Existing atomic-save guarantees

The inherited save path still uses:

- a sibling temporary file;
- flush and `fsync`;
- `os.replace`;
- temporary-file cleanup in `finally`.

This batch does not replace that primitive.

## Persistence diagnostics

`get_persistence_diagnostics()` returns read-only metadata only:

- load source state;
- last save state;
- stable save issue code;
- whether recovery reloaded durable state;
- valid loaded task count;
- `read_only=True`;
- `executed=False`.

It does not expose file paths, raw exception strings, task contents or user identifiers.

## Recovery semantics

For a failed mutation against an existing valid file, memory returns to the previously durable record.

For a failed first write when no file exists, memory returns to an empty store.

A later successful explicit mutation replaces the failure diagnostics with a successful save state.

## Safety boundary

This work does not:

- retry business actions;
- execute recovered pending actions;
- connect Product Decisions or Product Task Drafts to the legacy Action Executor;
- call mutating Ozon APIs;
- change mapping authorization;
- change finance calculations;
- modify `data/users.json`.

## Verification

Focused regressions:

`tests/test_task_save_failure_integrity_v313_v322.py`

The complete repository `Verify` workflow must pass on the PR merge revision before merge.

Architecture Review Required: Yes, because production persistence failure behavior changes.

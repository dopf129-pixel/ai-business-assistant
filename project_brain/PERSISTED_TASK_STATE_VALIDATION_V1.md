# Persisted Task State Validation v1

Date: 2026-08-30

Stages: v293-v302

## Goal

Fail closed when legacy task persistence contains malformed state, while preserving valid historical tasks and avoiding any automatic execution or restart-time rewrite.

## Validation boundary

`TerminalSafeAssistantTaskService` validates loaded records before exposing them to planner/executor flows.

A persisted task is rejected in memory when:

- the task entry is not a dictionary;
- task status is explicitly present but not a known `TaskStatus`;
- `actions` is not a list;
- any action entry is not a dictionary.

A missing task status remains backward compatible with the legacy `ACTIVE` default.

## Pending action normalization

A persisted `pending_action` must be either:

- `None`; or
- a dictionary.

Any other shape is normalized to `None` in recovered memory and reported as `INVALID_PENDING_ACTION_NORMALIZED`.

This prevents malformed persisted data from becoming executable pending intent.

## Restart semantics

Validation and normalization happen in memory during load.

The source JSON file is not rewritten merely because invalid state was discovered during restart. A later explicit task mutation may persist the current valid in-memory state through the existing atomic save path.

## Diagnostics

`get_load_diagnostics()` exposes:

- issue count;
- issue codes;
- number of valid tasks loaded;
- `read_only=True`;
- `executed=False`.

Diagnostics intentionally omit user identifiers.

## Terminal integration

After persisted-state validation, existing terminal reconciliation still runs:

- active tasks with all actions `DONE/SKIPPED` may derive `DONE`;
- terminal tasks expose no next action;
- terminal pending/replan intent is sanitized by the v283-v292 owner boundary.

## Safety boundary

This work does not:

- execute recovered actions;
- connect Product Decisions or Product Task Drafts to the legacy executor;
- enable Ozon mutation;
- modify mapping authorization;
- modify finance calculations;
- modify `data/users.json`.

## Verification

Focused regression coverage:

`tests/test_persisted_task_state_validation_v293_v302.py`

The repository `Verify` workflow must pass on the exact PR merge revision before merge.

Architecture Review Required: Yes, because this changes production task recovery behavior.

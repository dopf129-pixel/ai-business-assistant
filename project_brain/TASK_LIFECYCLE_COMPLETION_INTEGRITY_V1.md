# Task Lifecycle Completion Integrity v256-v263

## Goal

Make overall task lifecycle state agree with terminal action progress, including after process restart.

Before this change, a task could have every action in `DONE/SKIPPED` while the task itself remained `ACTIVE`.

## v256 — Final completion promotes task to DONE

When the final unfinished action becomes `DONE`, `AssistantTaskService` derives:

`task.status = DONE`

and persists it in the same owner-service write.

No separate execution is triggered by this promotion.

## v257 — Final skip also completes the task

A task is complete when it has at least one action and every action is terminal:

- `DONE`;
- `SKIPPED`.

The final explicit skip therefore promotes the overall task to `DONE`.

## v258 — Conditional skip completion

`get_current_action()` already performs legacy conditional skip evaluation.

If that existing evaluation skips the last remaining action, the owner service now finalizes the overall task before saving.

This does not add a new condition engine or execute an action.

## v259 — Legacy persisted-state reconciliation

On load, historical task records are checked in memory.

An old record with:

- task status `ACTIVE`;
- non-empty action list;
- every action `DONE/SKIPPED`;

is exposed as `DONE` in recovered state.

Load reconciliation does not rewrite the file and does not execute anything.

## v260 — Terminal precedence

Explicit terminal task statuses keep precedence.

A `CANCELLED` or task-level `SKIPPED` record is not converted to `DONE` merely because its actions happen to be terminal.

## v261 — Terminal mutation guard

Task-owner mutation methods reject changes after overall task status becomes terminal:

- start action;
- complete action;
- skip action;
- arbitrary action-status update;
- fail action;
- retry preparation;
- applied replan;
- replan request.

The terminal error includes the existing terminal task status.

## v262 — Generic status updates respect completion invariant

Legacy `update_action_status()` remains available.

If it makes the final non-terminal action `DONE/SKIPPED`, the overall task is promoted to `DONE`.

## v263 — Execution result consistency

After the legacy execution service completes the last action:

- returned `completed=True`;
- progress is fully done;
- `next_action=None`;
- persisted task status is `DONE`;
- restart preserves the same state.

## Active-task semantics

`has_active_task()` now returns false for:

- `DONE`;
- task-level `SKIPPED`;
- `CANCELLED`.

It remains true for non-terminal task states.

## Derived completion versus explicit state transitions

Overall `DONE` here is a derived invariant from action completion, not a user-requested state transition.

The task state machine continues to control explicit pause/resume/cancel transitions.

## Safety boundary

This work only reconciles and protects legacy task state.

It does not:

- connect Product Decisions to the legacy Action Executor;
- connect Product Task Drafts to execution;
- auto-run recovered actions;
- add Ozon mutation;
- change finance calculations;
- modify `data/users.json`.

Product Decision execution flags remain false.

## Validation

Focused regression coverage:

`tests/test_task_lifecycle_completion_integrity_v256_v263.py`

The full repository pytest suite is not claimed as executed for this branch.

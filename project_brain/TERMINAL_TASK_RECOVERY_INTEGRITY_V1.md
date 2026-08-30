# Terminal Task Recovery Integrity v1

Date: 2026-08-30

Stages: v283-v292

## Goal

Keep terminal legacy task state free of live execution/recovery intent across completion, explicit terminal transitions, process restart and production composition.

## Production owner

`TerminalSafeAssistantTaskService` extends the legacy `AssistantTaskService` instead of changing its public API.

`create_telegram_core()` now composes the terminal-safe owner. The legacy class remains available for compatibility and focused legacy tests.

## Terminal sanitization

For task statuses:

- `DONE`;
- `SKIPPED`;
- `CANCELLED`;

live recovery fields are normalized in memory to:

- `pending_action=None`;
- `replan_requested=False`;
- `replan_reason=None`.

Historical action results, statuses and unrelated task metadata are preserved.

## Derived completion

When the inherited lifecycle logic derives `DONE` because every action is `DONE/SKIPPED`, the terminal-safe owner sanitizes recovery intent in the same service operation before the next read.

## Explicit terminal transition

After an allowed explicit transition to a terminal task status, stale recovery intent is sanitized and persisted.

This does not create a new transition or bypass `TaskStateMachine`.

## Restart behavior

Load reconciliation sanitizes terminal state in memory.

It does not rewrite the persisted file merely because the process restarted. This preserves the existing read/reconcile boundary while ensuring recovered runtime state cannot expose a live pending/replan intent for a terminal task.

## Mutation guard

`clear_pending_action()` remains available for active tasks.

On a terminal task it returns the existing terminal-task error rather than performing an owner-level mutation. Loaded stale pending state is already normalized during reconciliation.

## Production behavior

The Telegram core now returns `TerminalSafeAssistantTaskService` as its `task_service`.

All existing executor/planner/business-flow DI references receive the same hardened instance.

## Safety boundary

This work only hardens the legacy task owner.

It does not:

- connect Product Decisions to the legacy Action Executor;
- connect Product Task Drafts to execution;
- infer or execute replenishment/price changes;
- call a mutating Ozon API;
- change mapping authorization;
- change finance calculations;
- modify `data/users.json`.

Product Decision execution flags remain unchanged and false.

## Verification

Focused regressions:

`tests/test_terminal_task_recovery_integrity_v283_v292.py`

Repository CI must pass the complete pytest suite on the exact PR revision before merge.

Architecture Review Required: Yes, because production task-owner composition changes.

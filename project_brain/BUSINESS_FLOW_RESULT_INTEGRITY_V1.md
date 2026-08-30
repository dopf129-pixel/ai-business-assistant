# Business Flow Result Integrity v1

Date: 2026-08-30

Package: v582-v590

## Gap

`AssistantBusinessFlowService` is the seller-facing orchestration boundary above
intent detection, planning, task lifecycle commands, and current-action execution.

Before this package it trusted downstream result shapes and frequently used
optimistic defaults. This created several false-success paths:

- malformed intent results could raise while indexing `intent["error"]`;
- malformed execution results could default to `error=False` and
  `"Действие выполнено"`;
- cancel/pause/resume errors could still be paired with success wording;
- errored `get_next_action()` could look like “no action available” success;
- post-skip next-action read failures were ignored after the skip mutation;
- continue could ignore a failed `set_pending_action()`;
- planner `error=True` or malformed result could be rewritten as top-level
  `error=False`.

## Contract

The Business Flow now validates the existing result boundary before presenting a
successful seller-facing response.

### Intent

A consumed intent result must be a dictionary with exact boolean `error`.

- explicit `error=True` is preserved;
- successful intent must contain a non-empty string command;
- malformed intent fails closed with `INVALID_INTENT_RESULT`.

### Execute / confirm execute

A successful execution result must contain:

- exact boolean `error=False`;
- non-empty string message;
- optional `action` / `next_action` as dictionary or `None`;
- boolean `completed`;
- valid non-negative integer progress with `done <= total`.

Missing optional `completed` and `progress` keep the prior defaults.

Explicit execution failure remains failure. A missing failure message uses the
stable code `EXECUTION_RETURNED_ERROR`; malformed success uses
`INVALID_EXECUTION_RESULT`. No malformed payload is allowed to claim
“Действие выполнено”.

### Task lifecycle commands

Cancel, pause, resume, task reads, skip, and continue validate exact boolean
`error` results.

- explicit failures are not paired with success wording;
- malformed results fail closed with deterministic codes;
- initial skip next-action read must succeed before mutation;
- the selected skip action must be a dictionary with a non-empty title;
- skip result is validated before presentation;
- post-skip next-action read is also validated;
- if skip has already committed and the later read fails, the returned error
  preserves the actually skipped action and sets `next_action=None`; it does not
  pretend the mutation was rolled back;
- continue validates both the next-action read and the existing
  `set_pending_action` result.

### Planner result

A successful planner result must contain:

- exact boolean `error=False`;
- `actions` as a list of dictionaries;
- `count` as a non-boolean, non-negative integer;
- `count == len(actions)`.

Explicit planner failure remains failure. Malformed success fails closed with
`INVALID_PLANNER_RESULT`.

## Safety

This package does not:

- add a service, executor, action type, runtime route, or mutation endpoint;
- change Product Decision / Product Task Draft execution policy;
- connect Ozon mutation APIs;
- infer missing business evidence;
- change finance formulas, advertising semantics, or sales/stock thresholds;
- add automatic retries or rollback;
- change task persistence format;
- modify `data/users.json`.

The package only prevents the existing seller-facing flow from promoting an
invalid or failing downstream result to apparent success.

## Partial-side-effect semantics

The skip path may mutate task state before reading the following action.
If that post-skip read fails, the flow returns an error containing the confirmed
skipped action. It does not claim rollback and does not automatically retry.

This preserves the single existing task-service mutation owner and avoids false
state reporting.

## Architecture Review

Architecture Review Required: Yes.

Reason:

- existing seller-facing orchestration contract changes;
- the package spans execution-adjacent task and planning boundaries;
- implementation plus regression coverage exceeds the ~300-line review threshold.

Review focus:

- constructor DI unchanged;
- explicit downstream failure semantics preserved;
- valid success shapes remain compatible;
- malformed payloads fail closed before later mutation where possible;
- a committed skip is never misrepresented as rolled back;
- no execution authorization or mutation capability is added.

## Verification Plan

Required evidence layers:

1. exact feature-branch push verification;
2. PR synthetic merge-ref verification;
3. squash merge;
4. separate exact squash-main push verification;
5. docs-only reconciliation on the verified squash-main SHA.

No verification evidence transfers between SHAs.

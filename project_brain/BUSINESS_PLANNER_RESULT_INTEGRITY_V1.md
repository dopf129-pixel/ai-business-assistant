# Business Planner Result Integrity v1

Date: 2026-08-30

Package: v575-v581

## Gap

`AssistantBusinessPlannerService` previously trusted the shape and success semantics
of recommendation, planning, Action Plan execution, and task-creation results.

The most important failure mode was downstream error suppression:

- `AssistantActionPlanExecutorService` could correctly return `error=True`;
- `AssistantBusinessPlannerService` then read `actions/count`;
- it returned a new top-level `error=False` result;
- seller-facing planning could therefore look successful even though the execution
  orchestration had already failed closed.

Malformed payloads could also raise `TypeError` / `KeyError` or be normalized into
empty-looking success.

## Contract

The planner now validates each existing boundary before continuing.

### Recommendation result

A successful result must be a dictionary with exact boolean `error=False` and a
list `recommendations`.

- explicit `error=True` is returned unchanged;
- malformed success fails closed with `INVALID_RECOMMENDATION_RESULT`;
- general-only recommendations remain non-actionable and do not enter planning.

### Planning result

A successful result must be a dictionary with exact boolean `error=False` and a
list `plan`.

- explicit `error=True` is returned unchanged;
- malformed success fails closed with `INVALID_PLANNING_RESULT`.

### Action Plan execution result

A successful result must contain:

- exact boolean `error=False`;
- `actions` as a list of dictionaries;
- `count` as a non-boolean, non-negative integer;
- `count == len(actions)`.

Explicit downstream `error=True` is preserved unchanged.
Malformed success fails closed with `INVALID_PLAN_EXECUTION_RESULT`.

### Task creation result

When the existing optional task-service path is used, its result must contain an
exact boolean `error` field.

- explicit task creation failure is returned unchanged;
- malformed task creation result fails closed with
  `INVALID_TASK_CREATION_RESULT`;
- no task service and zero-action success retain existing compatible behavior.

## Safety

This package does not:

- add a service, executor, action type, runtime route, or mutation path;
- authorize Product Decision or Product Task Draft execution;
- connect Ozon mutation APIs;
- infer missing business evidence;
- change sales/stock/finance/marketing thresholds or formulas;
- change persistence format;
- modify `data/users.json`.

No new business execution permission is introduced. The change only prevents an
existing orchestration layer from converting downstream failure into apparent
success.

## Architecture Review

Architecture Review Required: Yes.

Reason:

- existing Business Planner orchestration contract changes;
- the boundary is execution-adjacent and seller-facing;
- package size including regressions/docs exceeds the ~300-line review threshold.

Review focus:

- constructor DI remains unchanged;
- explicit downstream errors are preserved;
- valid action ordering and result shape remain compatible;
- general recommendations remain presentation-only;
- malformed results fail closed before task creation;
- no additional business execution is enabled.

## Verification Plan

Required evidence layers:

1. exact feature-branch push verification;
2. PR synthetic merge-ref verification;
3. squash merge;
4. separate exact squash-main push verification;
5. docs-only reconciliation on the verified squash-main SHA.

No evidence transfers between SHAs.

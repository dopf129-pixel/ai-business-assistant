# Executor Error-Result Lifecycle Integrity V1

Date: 2026-08-30  
Stages: v541-v547  
Architecture Review Required: Yes

## Gap

AssistantActionExecutionService already handled raised executor exceptions through
the persisted FAILED lifecycle.

However, an executor/router could return a normal result object with
`error=True`. In `execute_current_action()` that result previously bypassed the
exception branch and continued into `complete_action()`.

That could persist an action as DONE, finalize its task, and record DONE feedback
/history even though the executor explicitly reported failure.

This is a lifecycle-integrity defect for any fail-closed executor, including
Sales, Stock, Finance and Marketing paths.

## Contract

The direct router contract remains unchanged:

- `AssistantActionRouterService.execute(action)` returns the executor result as-is;
- direct callers can still inspect `error=True` without an exception.

The persisted execution boundary is hardened:

- `AssistantActionRouterService.run(action)` is the action-runner boundary used by
  AssistantActionExecutionService;
- an executor result with explicit `error=True` becomes a controlled exception;
- a non-dict executor result fails closed as `INVALID_EXECUTOR_RESULT`;
- a malformed non-boolean/non-null `error` field also fails closed as
  `INVALID_EXECUTOR_RESULT`;
- an explicit error without a usable message becomes the stable
  `EXECUTOR_RETURNED_ERROR` code;
- unrelated result payload fields are not stringified into the persisted error.

The existing AssistantActionExecutionService exception path then remains the
single persisted failure lifecycle owner.

## Persisted failure semantics

For executor error results:

- action status becomes FAILED;
- task stays active rather than being finalized DONE;
- pending action is cleared by the existing task service failure path;
- task progress does not count the failed action as done;
- retry policy is evaluated from the normalized error text;
- feedback is recorded as FAILED, not DONE;
- history event is `execution_failed`, not `execution_completed`;
- `complete_action()` is not reached.

Existing retry preparation remains unchanged and can move a FAILED action back
to NEW with an incremented attempt.

## Success compatibility

Successful executor results continue through the existing completion path:

- action becomes DONE;
- task may become DONE when all actions are terminal-success states;
- completion feedback/history remain unchanged.

`run()` also continues accepting result dictionaries with `error=False` or no
`error` field for backward compatibility.

## Safety

This package does not:

- add a new executor;
- add a new runtime route;
- execute Product Decisions or Product Task Drafts;
- add seller/business mutation;
- add Ozon mutation;
- change retry limits;
- change task persistence format;
- modify `data/users.json`.

The change makes an existing execution boundary fail closed. It does not grant
new execution permission.

## Architecture review

Architecture Review Required: Yes because this is a production persisted-action
lifecycle boundary whose incorrect behavior can falsely record failed work as
completed.

Review criteria:

- use the existing router and execution service; no new service/layer;
- preserve direct `execute()` compatibility;
- preserve existing exception-based FAILED lifecycle as the single owner;
- do not duplicate task mutation logic in the router;
- do not stringify arbitrary executor payloads into persisted errors;
- preserve retry/history/feedback behavior;
- preserve successful completion behavior;
- no external mutation or Product Decision execution connection.

## Verification

Regression coverage is in:

`tests/test_executor_error_result_lifecycle_v541_v547.py`

It covers:

1. direct router error-result compatibility;
2. executor error result -> FAILED, not DONE;
3. active task and zero completed progress after failure;
4. pending-action cleanup;
5. failure-only history and feedback;
6. existing retry preparation after an error result;
7. non-retryable error policy;
8. stable fallback error without payload stringification;
9. malformed executor result fail-closed behavior;
10. malformed `error` flag fail-closed behavior;
11. successful result still completes action and task.

Full GitHub Actions verification is required before merge.

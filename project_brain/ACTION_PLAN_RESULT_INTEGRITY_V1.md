# Action Plan Result Integrity V1

Date: 2026-08-30  
Stages: v568-v574  
Architecture Review Required: Yes

## Gap

AssistantActionPlanExecutorService previously trusted generator, priority and execution
service payloads through direct dictionary indexing.

Consequences:

- malformed stage result could raise KeyError / TypeError;
- priority-stage explicit error could be ignored;
- execution-stage explicit error could be wrapped as top-level `error=False`;
- malformed executed/count output could look like a successful plan result;
- downstream exception text could escape through an unhandled exception.

## Contract

The existing three-stage orchestration remains:

1. action generation;
2. priority resolution;
3. action execution.

No new stage or runtime route is added.

### Generator boundary

Accepted success result:

- dict;
- `error=False` exactly;
- non-empty list/tuple `actions`;
- every generated action is a dict.

Explicit `error=True` is returned unchanged.

Malformed result fails closed with a stable internal code.

### Priority boundary

For every generated action:

- priority service receives a dict action;
- result must be dict;
- `error=False` exactly;
- result `action` must be dict.

Explicit `error=True` is returned unchanged and later actions/execution are not run.

### Execution boundary

Execution result must be:

- dict;
- `error=False` exactly;
- `executed` list;
- integer non-negative `count` that is not bool;
- `count == len(executed)`;
- every executed entry is a dict.

Explicit `error=True` is returned unchanged rather than being converted into success.

### Exception normalization

Exceptions from generator, priority or execution stages are converted into stable
non-secret failure codes. Raw exception text is not returned.

## Fail-closed result

Malformed orchestration evidence returns:

- `error=True`;
- stable `message` code;
- `actions=[]`;
- `count=0`.

This result does not imply task/action completion.

## Compatibility

Valid existing orchestration output is preserved:

- top-level success shape remains `error=False`, `actions`, `count`;
- generated action order is preserved through priority resolution;
- execution service still owns individual action execution semantics;
- explicit downstream service errors remain downstream-owned error results.

## Execution safety

This package does not:

- add a new executor/action type/runtime route;
- alter Product Decision or Product Task Draft execution;
- add Ozon mutation;
- infer missing action context;
- change sales/stock/finance/marketing thresholds;
- change task persistence format;
- modify `data/users.json`.

The package only prevents malformed orchestration results from being promoted to
successful plan output.

## Architecture review

Required because this package changes the existing Action Plan orchestration contract
at a safety-critical boundary and exceeds the approximate 300-line threshold with
tests/documentation.

Review points:

- constructor DI unchanged;
- no new layer/service;
- stable deterministic failure codes;
- downstream explicit errors preserved;
- no raw exception-secret leakage;
- no later stage after an earlier-stage failure;
- valid action order preserved;
- no execution permission added.

## Verification

Focused regressions cover:

1. valid success contract;
2. generator explicit error;
3. malformed generator results;
4. generator exception;
5. empty generated plan;
6. non-dict generated action;
7. priority explicit error;
8. malformed priority results;
9. priority exception;
10. execution explicit error;
11. execution exception;
12. malformed executed/count results;
13. multiple-action order preservation;
14. first priority failure stops later stages.

Full exact-branch-SHA GitHub Actions verification and PR merge-ref verification are
required before merge. The squash-main SHA requires its own push Verify.

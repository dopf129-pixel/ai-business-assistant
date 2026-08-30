# Recommendation Context Integrity V1

Date: 2026-08-30  
Stages: v561-v567  
Architecture Review Required: Yes

## Gap

AssistantRecommendationService could create sales or stock recommendations from a
boolean problem flag even when the corresponding domain context was empty or
malformed. Finance context accepted any truthy object and could fail while converting
it to dict.

The downstream AssistantBusinessPlannerService also treated the generic presentation
fallback as an actionable recommendation. As a result, messages such as
"Недостаточно данных для полной оценки бизнеса" or "Критичных проблем не найдено"
could be passed through planning/action generation and appear as executed work.

## Contract

Actionable domain recommendations require a non-empty dictionary context:

- sales_down=True requires valid sales_context;
- low_stock=True requires valid stock_context;
- finance recommendation requires valid finance_context and finance evidence not
  explicitly unavailable;
- marketing keeps its existing explicit evidence + non-empty context requirement.

A positive problem flag without valid action context does not create a domain action.
It produces the non-actionable insufficient-data presentation fallback instead.

Malformed non-dict report input fails closed with an explicit recommendation error.

## General recommendation boundary

Recommendation type `general` is presentation-only.

AssistantBusinessPlannerService filters `general` before planning. If no actionable
recommendations remain:

- planning service is not called;
- action-plan executor is not called;
- no task is created;
- actions=[];
- count=0.

Existing actionable domain recommendations continue through the existing planner and
executor path unchanged.

## Execution safety

This package does not:

- add a new executor or runtime route;
- add Product Decision or Product Task Draft execution;
- infer missing sales/stock/finance evidence;
- change sales/stock/finance thresholds;
- mutate Ozon;
- alter persistence format or data/users.json.

The change removes execution-looking behavior from insufficient/clean presentation
messages; it does not add business execution permission.

## Architecture review

Required because the package changes the existing Recommendation -> Planning action
boundary and prevents generic presentation recommendations from entering execution.

Review points:

- no new service/layer;
- constructor DI unchanged;
- valid domain recommendation payloads preserved;
- invalid/missing domain context fails closed;
- no general recommendation can create an action/task;
- no new mutation capability;
- no Product Decision recomputation;
- no finance formula changes.

## Verification

Focused regressions cover:

1. malformed non-dict report;
2. sales problem without valid context;
3. valid sales context contract;
4. stock problem without valid context;
5. valid stock context contract;
6. malformed finance context;
7. valid finance context contract;
8. general insufficient-data recommendation not reaching planner/executor/task;
9. actionable recommendation preserving the existing planner path;
10. clean general fallback remaining presentation-only.

Full exact-branch-SHA GitHub Actions verification and PR merge-ref verification are
required before merge. The resulting squash-main SHA requires its own push Verify.

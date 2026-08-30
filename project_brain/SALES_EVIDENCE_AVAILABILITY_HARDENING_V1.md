# Sales Evidence Availability Hardening V1

Date: 2026-08-30  
Stages: v534-v540  
Architecture Review Required: Yes

## Gap

The configured Sales Intelligence path previously conflated unavailable evidence
with a verified non-decline state.

Two concrete failure modes existed:

1. SalesContextProvider used a default `change_percent=0` when the revenue
   comparison field was missing, which could turn unavailable comparison
   evidence into `sales_down=False`;
2. SalesIntelligenceService used zero defaults for missing output metrics, which
   could turn missing revenue/profit facts into numeric zero and could treat a
   missing comparison change as a stable-sales insight.

Those semantics could suppress a sales action or create a false clean-state
impression.

## Provider contract

Historical no-data mode remains unchanged:

- SalesContextProvider without required dependencies still returns
  `report=None, period_data=None`;
- AssistantEntryService constructed with no data dependencies keeps its legacy
  hardcoded report.

For a configured sales data path:

- confirmed decline keeps the existing `sales_down=True` + `sales_context`
  payload, with no new availability field;
- complete non-decline evidence returns `sales_down=False` and
  `sales_evidence_available=True`;
- missing, malformed, failed or partial comparison evidence returns
  `sales_down=False` and `sales_evidence_available=False`;
- unavailable evidence does not create a sales action.

## Required source evidence

SalesContextProvider fails closed on:

- missing or malformed product collections;
- malformed product targets;
- malformed/current or previous period payloads;
- failed or malformed period-profit results;
- empty period-profit evidence;
- malformed or failed analytics results;
- missing, malformed, boolean or non-finite revenue `change_percent`.

Explicit numeric zero `change_percent=0` remains valid stable evidence.

Valid period profit evidence may still be passed to the independent Finance
Context provider even when sales comparison evidence is unavailable.

## Sales Intelligence contract

SalesIntelligenceService rejects malformed action context before invoking the
analytics service.

Required sales metrics:

- revenue / `gross_sales`;
- gross profit / `gross_profit`.

These must be finite numeric values.

Optional metrics:

- business profit;
- business margin.

Missing optional business metrics remain `None`, not zero.

Explicit numeric zero remains valid.

A missing or malformed comparison change produces no sales trend insight; it is
not treated as stable.

## Presentation

AssistantSalesExecutorService renders unknown metrics as `—`.

It does not render Python `None` or invent numeric zero for unavailable values.

## Recommendation semantics

When no other recommendation exists and
`sales_evidence_available=False`, the generic fallback says:

`Недостаточно данных для полной оценки бизнеса`

instead of claiming:

`Критичных проблем не найдено`.

## Execution safety

This package does not:

- change the sales-decline threshold;
- infer a business action from unavailable evidence;
- alter Product Decision rules;
- execute Product Task Drafts;
- add a new Action Executor route;
- mutate Ozon;
- use availability metadata as authorization.

## Architecture review

Required because the package changes production sales report/recommendation
semantics and existing Sales Intelligence input/output handling across multiple
runtime surfaces. The package also exceeds the approximate 300 changed-line
review threshold after tests and documentation.

Review confirms:

- no new service/layer;
- no new runtime route;
- legacy no-data mode preserved;
- confirmed decline action context preserved;
- configured incomplete evidence fails closed;
- explicit zero remains distinct from missing;
- required revenue/gross-profit evidence is not invented;
- unknown business-profit/margin values remain unknown;
- no hidden side effects;
- no seller/business execution permission is introduced;
- no persistence or `data/users.json` change.

## Verification

Focused regressions cover:

1. legacy provider without dependencies;
2. malformed products;
3. missing comparison change;
4. non-finite comparison change;
5. complete non-decline evidence;
6. preserved confirmed-decline action context;
7. empty profit evidence;
8. configured partial Entry path;
9. generic fallback under unavailable sales evidence;
10. malformed action context before analytics;
11. missing required store metrics;
12. unknown business metrics;
13. explicit zero sales metrics;
14. missing comparison change not becoming stable;
15. explicit zero comparison remaining stable;
16. executor rendering unknown metrics as `—`.

Full GitHub Actions verification is required before merge.

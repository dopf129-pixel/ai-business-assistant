# Stock Evidence Availability Hardening V1

Date: 2026-08-30  
Stages: v527-v533  
Architecture Review Required: Yes

## Gap

StockContextProvider previously used the same `low_stock=False` result for two
different situations:

1. complete evidence showed no low-stock risk;
2. required stock/sales/period evidence was missing, malformed or failed.

That ambiguity could suppress the stock recommendation and later allow the
generic recommendation fallback to say that no critical problems were found
when stock evidence had not actually been checked.

## Contract

Confirmed low-stock evidence keeps the existing action context shape:

- `low_stock=True`;
- existing `stock_context.stock_data`;
- existing `stock_context.sales_data`;
- existing `stock_context.period_days`.

No new execution field is added to the low-stock action context.

When no low-stock risk is found:

- complete assortment evidence -> `low_stock=False` and
  `stock_evidence_available=True`;
- missing, malformed, failed or partial evidence -> `low_stock=False` and
  `stock_evidence_available=False`.

The availability flag is report metadata only. It is not execution permission.

Legacy compatibility is preserved for the historical AssistantEntryService mode
that is constructed with no data dependencies at all: that mode keeps its
existing hardcoded report behavior. The new availability semantics apply when
the stock data path is actually configured or an explicit StockContextProvider
is injected.

## Complete-evidence requirement

The provider fails closed when any of these are unavailable or malformed:

- product service;
- analytics service;
- metrics service;
- product list;
- valid positive period length;
- product target identifiers;
- FBO available stock;
- sales count.

Mixed valid + failed assortment evidence remains unavailable instead of
producing a clean no-risk result.

## Numeric evidence

For stock and sales quantities:

- boolean values are rejected;
- non-finite values are rejected;
- negative values are rejected;
- explicit numeric zero remains valid where semantically allowed.

For period days:

- value must be finite and strictly positive.

## Cross-product evidence

StockIntelligenceService rejects stock and sales payloads with different
product identifiers.

It also fails closed on malformed numeric evidence rather than converting it
into valid stock/sales facts.

Explicit zero sales remains a valid `NO_SALES` state.

## Recommendation semantics

The general fallback remains non-actionable.

If `stock_evidence_available=False`, it says:

`Недостаточно данных для полной оценки бизнеса`

instead of:

`Критичных проблем не найдено`

A stock action is still generated only when `low_stock=True`.

## Execution safety

This package does not:

- infer replenishment quantity;
- create a replenishment draft;
- enable Product Decision execution;
- alter Product Task Draft execution;
- add a new Action Executor route;
- add Ozon mutation;
- treat evidence availability as authorization.

## Architecture review

Required because the package changes production report/recommendation semantics
and modifies multiple stock-intelligence surfaces with a package larger than
the approximate 300 changed-line threshold.

Review confirms:

- no new service/layer;
- no new runtime route;
- confirmed low-stock action context remains backward compatible;
- historical no-data AssistantEntryService fallback remains backward compatible;
- unavailable evidence does not create a stock action;
- explicit zero sales remains distinct from missing evidence;
- no business execution permission is introduced;
- no persistence or `data/users.json` change;
- no Product Decision/Ozon mutation wiring.

## Verification

Focused regressions cover:

1. missing dependencies;
2. empty products;
3. complete verified safe stock;
4. missing stock metrics;
5. sales errors;
6. partial assortment evidence;
7. preserved low-stock action context;
8. malformed/non-finite/boolean/negative evidence;
9. cross-product evidence;
10. explicit zero sales / NO_SALES;
11. general fallback wording with unavailable evidence;
12. existing clean fallback with complete evidence;
13. invalid period evidence.

Full GitHub Actions verification is required before merge.

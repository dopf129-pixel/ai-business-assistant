# Unknown Advertising Financial Evidence V1

Date: 2026-08-30  
Stages: v514-v520  
Architecture Review Required: Yes

## Gap

Production Telegram composition passed `advertising_cost=0` even when no
advertising evidence source was connected.

That converted missing evidence into a known zero and could allow
`BusinessAnalyticsService` / `BusinessProfitService` to expose a calculated
business-profit value that implicitly assumed zero advertising spend.

Presentation services also converted `None` financial values into zero.

## Contract

Advertising evidence now distinguishes:

- `None` — advertising expense evidence is unavailable;
- `0` — explicit known zero;
- positive numeric value — explicit known advertising cost.

No fuzzy inference or automatic advertising fetch is introduced.

## Production composition

`create_telegram_core(..., advertising_cost=None)` now defaults to unknown.

The optional argument is appended for backward compatibility.

A caller may explicitly inject `advertising_cost=0` when zero is known.

## Business analytics

When advertising evidence is unknown:

- advertising result has `configured=False`;
- advertising cost remains `None`;
- revenue and gross profit remain available;
- business profit and margin remain `None`;
- missing evidence includes `advertising`;
- if tax is also unconfigured, missing evidence also includes `tax`.

Tax errors are preserved and are not hidden by the advertising state.

## Presentation

Unknown values render as `—` in:

- AdvertisingDashboardService;
- BusinessProfitDashboardService;
- AssistantSalesExecutorService business-profit/margin details.

Unknown values are never rendered as zero or Python `None`.

## Financial safety

This package does not:

- alter Ozon fee calculations;
- subtract RETURN / ADVERTISING / STORAGE evidence a second time;
- claim complete accounting net profit;
- infer complete return economics;
- auto-classify advertising operations;
- create an advertising provider or hidden API fetch.

It corrects only the missing-evidence semantics of the existing business analytics path.

## Execution safety

No Product Decision rule, Product Task Draft lifecycle, Action Executor mapping,
seller mutation or Ozon mutation is added or changed.

## Architecture review

Required because production composition and an existing financial evidence
contract change.

Review result:

- optional DI remains backward compatible;
- explicit zero remains distinguishable from missing evidence;
- no new service/layer;
- no hidden side effect;
- no invented runtime state;
- no financial double counting;
- downstream sales analysis preserves unknown values;
- presentation does not promote unknown to zero;
- no `data/users.json` change.

## Verification

Focused regressions cover:

1. production default unknown;
2. explicit zero injection;
3. business-profit blocking;
4. combined tax/advertising missing evidence;
5. explicit-zero business-profit calculation;
6. dashboard unknown presentation;
7. sales-analysis unknown presentation;
8. Sales Intelligence unknown propagation;
9. tax-error preservation.

Full GitHub Actions verification is required before merge.

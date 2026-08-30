# Finance Context Evidence Hardening V1

Date: 2026-08-30  
Stages: v521-v526  
Architecture Review Required: Yes

## Gap

FinanceContextProvider previously normalized absent `gross_sales` and
`gross_profit` values to zero.

That allowed incomplete period-profit evidence to become apparently valid
finance context.

The same pipeline passed period `gross_profit` under the generic key
`profit`, while Finance Intelligence used seller-facing wording such as
"Бизнес работает с положительной прибылью". The source evidence does not prove
complete accounting profit because tax, advertising, returns and other business
expenses are not necessarily included in this context.

## Contract

Provider-generated finance context now requires complete source rows:

- any explicit source row with `error=True` fails closed;
- every source row requires finite numeric `gross_sales`;
- every source row requires finite numeric `gross_profit`.

Missing, malformed, boolean, non-finite or explicitly failed source evidence fails closed.

Explicit numeric zero remains valid evidence.

FinanceContextProvider keeps its existing output shape for backward compatibility.

FinanceIntelligenceService classifies its own direct inputs deterministically
without requiring a new provider field:

- missing explicit profit -> `DERIVED_REVENUE_MINUS_EXPENSES`;
- explicit caller profit without scope -> `CALLER_PROVIDED`.

Seller-facing wording remains generic unless an explicit compatible scope is
already supplied by a direct caller.

## Arithmetic

For complete source evidence, existing arithmetic is preserved:

- revenue = sum(gross_sales);
- profit = sum(gross_profit);
- expenses = revenue - profit;
- margin = profit / revenue where revenue is non-zero.

This package does not change the formula. It changes validation and semantic
scope only.

The `expenses` value is therefore described as expenses by available period
evidence, not complete business expenses.

## Finance Intelligence wording

Positive / negative / zero results are described as a calculated gross result.

The pipeline no longer claims that the whole business is profitable or at
accounting break-even based solely on PERIOD_GROSS_PROFIT evidence.

Finance Executor labels are likewise scoped to:

- "Расчётный валовый результат";
- "Расходы по доступным данным";
- "Маржинальность по доступным данным".

## Financial safety

This package does not:

- alter FinanceService fee_breakdown;
- subtract marketplace fees twice;
- infer tax, advertising, storage or returns costs;
- claim complete return economics;
- claim accounting net profit;
- change period-profit formulas.

## Execution safety

No Product Decision rule, Product Task Draft lifecycle, Action Executor mapping,
seller mutation or Ozon mutation is added or changed.

## Architecture review

Required because an existing finance-context contract and seller-facing
financial semantics are changed and the package modifies multiple pipeline
surfaces.

Review result:

- no new service or layer;
- no new runtime route;
- existing complete-evidence arithmetic preserved;
- missing evidence fails closed;
- explicit zero remains distinct from missing;
- existing FinanceContextProvider output shape is preserved;
- no hidden side effects;
- no financial double counting;
- no execution permission is introduced;
- no `data/users.json` change.

## Verification

Focused regressions cover:

1. malformed period payload;
2. missing required gross_sales / gross_profit;
3. malformed / non-finite / boolean values;
4. explicit zero;
5. backward-compatible provider output shape;
6. neutral Finance Intelligence wording;
7. deterministic direct-caller scopes;
8. decline wording;
9. evidence-scoped Finance Executor presentation;
10. malformed Finance Intelligence current/previous context rejection;
11. error-only rows do not become zero evidence;
12. mixed valid + error rows fail closed instead of producing partial totals.

Full GitHub Actions verification is required before merge.

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

Provider-generated finance context now requires, for every non-error source row:

- finite numeric `gross_sales`;
- finite numeric `gross_profit`.

Missing, malformed, boolean or non-finite values fail closed.

Explicit numeric zero remains valid evidence.

Provider output now carries:

`profit_scope=PERIOD_GROSS_PROFIT`

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
- source scope is explicit;
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
5. explicit PERIOD_GROSS_PROFIT scope;
6. neutral Finance Intelligence wording;
7. decline wording;
8. scoped Finance Executor presentation;
9. error-only rows do not become zero evidence.

Full GitHub Actions verification is required before merge.

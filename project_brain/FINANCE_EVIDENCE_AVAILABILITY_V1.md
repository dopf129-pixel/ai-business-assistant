# Finance Evidence Availability Propagation V1

Date: 2026-08-30
Stages: v554-v560
Architecture Review Required: Yes

## Gap

FinanceContextProvider already failed closed when period finance evidence was
missing or malformed, but AssistantEntryService discarded that absence.

If Sales and Stock evidence were both verified safe while Finance evidence was
unavailable, the recommendation fallback could still say:

`Критичных проблем не найдено`

That was stronger than the available evidence supported.

## Contract

- successful derived FinanceContextProvider output adds
  `finance_evidence_available=True`;
- failed derived finance context with non-null period evidence adds
  `finance_evidence_available=False`;
- no period evidence does not invent a finance availability state;
- an explicit incoming non-empty `finance_context` remains authoritative and
  is marked available;
- a false availability flag suppresses finance recommendation even if a
  contradictory finance_context is present;
- legacy direct recommendation callers that provide finance_context without the
  new metadata remain backward compatible.

## Recommendation semantics

When no other recommendation exists and
`finance_evidence_available=False`, the general fallback says:

`Недостаточно данных для полной оценки бизнеса`

instead of claiming that no critical problems were found.

## Finance safety

This package does not:

- alter FinanceContextProvider output shape;
- alter revenue / gross-profit arithmetic;
- alter FinanceService fee_breakdown;
- double-subtract marketplace fees;
- infer advertising, tax, storage or return costs;
- claim accounting net profit.

## Execution safety

No Product Decision rule, Product Task Draft execution, Action Executor route,
Ozon mutation, persistence format or `data/users.json` change is introduced.

## Architecture review

Required because production report/recommendation semantics change and the
package exceeds the approximate 300 changed-line review threshold with tests
and documentation.

Review confirms:

- no new service/layer;
- no new runtime route;
- explicit finance-context compatibility preserved;
- missing evidence is not converted to a clean conclusion;
- no new finance calculation;
- no business execution permission.

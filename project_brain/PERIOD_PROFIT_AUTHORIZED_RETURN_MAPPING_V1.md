# Period Profit Authorized Return Mapping v1

`PeriodProfitQueryService` can consume a previously authorized immutable return-financial mapping artifact.

The mapping is applied only when all safety/lineage flags match the authorized contract. The query then uses exact authorized operation names to classify existing Ozon `fee_breakdown` rows as return-financial evidence.

This does not alter the period profit formula and does not subtract matched amounts again because those amounts are already represented inside `net_accrual`.

If the artifact is missing or unsafe, it is ignored and no automatic activation occurs.

Safety remains explicit:

- read-only analytics only;
- `returns_profit_adjustment_allowed=False`;
- no Ozon mutation;
- no Product Decision execution;
- `executed=False`.

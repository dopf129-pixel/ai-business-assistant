# Period Profit Return Financial Query v1

`PeriodProfitQueryService` now exposes `return_financial_evidence` built from the exact aggregated `fee_breakdown` of the same period-profit summary.

The constructor accepts optional `return_financial_operation_names`. Only exact names from this explicit policy are matched. With no configured policy, the evidence artifact reports `policy_configured=False` and does not infer financial return impact.

Matched return-related fee values remain evidence only. They are already part of Ozon `net_accrual`, therefore `returns_profit_adjustment_allowed=False` remains fixed and the period profit is not changed.

The existing separate Returns API evidence remains independent and continues to prove return records, not monetary impact.

Review classification: Architecture Review Required because the query response contract is extended. Read-only analytics only.
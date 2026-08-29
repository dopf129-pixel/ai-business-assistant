# Period Profit Return Financial Evidence v1

Adds a pure read-only contract for identifying return-related finance operations from Ozon `fee_breakdown` data.

The contract deliberately uses exact caller-provided operation names only. It does not perform substring, language, type-id, or semantic guessing.

Matched finance operations are evidence only. `returns_profit_adjustment_allowed=False` remains fixed because fee-breakdown amounts are already components of Ozon `net_accrual`; subtracting them again would double count costs.

No default return-operation policy is invented in this stage. Until an explicit verified mapping is supplied, `policy_configured=False` and financial return impact is not claimed.

Read-only analytics only; no Ozon mutation, Product Decision mutation, Action Executor use, or execution path.
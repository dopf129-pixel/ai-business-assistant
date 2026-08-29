# Period Profit Advertising and Storage Evidence v1

Adds a pure read-only exact-name evidence contract for `ADVERTISING` and `STORAGE` operation scopes.

Only explicitly configured operation names can match `fee_breakdown`. No substring or semantic guessing is allowed.

Matched amounts are treated as evidence for expenses already represented inside `net_accrual`; `profit_adjustment_allowed=False` and `automatic_classification_allowed=False` remain explicit.

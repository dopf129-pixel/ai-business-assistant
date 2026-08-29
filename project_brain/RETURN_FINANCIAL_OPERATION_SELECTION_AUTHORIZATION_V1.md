# Return Financial Operation Selection Authorization v1

Authorizes or rejects a previously human-selected set of exact Ozon accrual operation `type_id` values.

`AUTHORIZE` permits only use of the selected exact operation names for return-financial evidence mapping. It does not activate any automatic mapping, mutate Ozon, or change the period-profit formula.

Safety remains explicit:

- `financial_evidence_mapping_allowed=True` only after AUTHORIZE;
- `returns_profit_adjustment_allowed=False`;
- `automatic_activation_allowed=False`;
- `read_only=True`;
- `executed=False`.

# Assistant Return Operation Review Runtime v1

Adds a read-only direct assistant route for explicit requests to inspect real Ozon accrual operation types used for manual return-mapping review.

Recognized examples include requests for `типы начислений Ozon`, `финансовые типы Ozon`, and `операции Ozon для возвратов`.

The route runs before period-profit and the general planner flow. Unrelated text is passed through unchanged.

Safety remains explicit:

- no automatic return classification;
- `mapping_activation_allowed=False`;
- `returns_profit_adjustment_allowed=False`;
- `read_only=True`;
- `executed=False`.

Production wiring uses the existing return-operation review report factory and does not introduce Ozon mutation or Product Decision execution.

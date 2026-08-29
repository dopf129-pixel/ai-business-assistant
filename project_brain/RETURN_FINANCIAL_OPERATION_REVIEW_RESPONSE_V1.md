# Return Financial Operation Review Response v1

Formats the read-only return-operation review report for a human operator.

The response lists exact Ozon source `type_id`, `name`, and optional `description` values and explicitly states that no operation is classified as return-related automatically.

Safety remains explicit:

- manual verification is required before mapping;
- `mapping_activation_allowed=False`;
- `returns_profit_adjustment_allowed=False`;
- `read_only=True`;
- `executed=False`.

This stage introduces presentation only; no Ozon mutation or profit adjustment.

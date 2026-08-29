# Return Financial Operation Review Report v1

Builds a read-only human-review report over the real Ozon accrual operation catalog.

Every source operation is exposed with `return_related=None` and `human_verification_required=True`. The report deliberately does not infer return semantics from names or descriptions.

Safety remains explicit:

- `mapping_activation_allowed=False`;
- `returns_profit_adjustment_allowed=False`;
- `read_only=True`;
- `executed=False`.

New service => Architecture Review Required.

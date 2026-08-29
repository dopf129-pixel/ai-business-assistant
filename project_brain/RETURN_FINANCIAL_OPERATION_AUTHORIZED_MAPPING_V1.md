# Return Financial Operation Authorized Mapping v1

Builds a deterministic immutable artifact from a successfully authorized human selection of exact Ozon accrual operation types.

The artifact contains exact `type_id` and operation names plus a SHA-256-derived `mapping_id` over canonicalized selected operations. It is not persisted in v1 and does not activate itself automatically.

Safety remains explicit:

- `mapping_authorized=True` only from authorized input;
- `financial_evidence_mapping_allowed=True`;
- `immutable_artifact=True`;
- `persistent=False`;
- `returns_profit_adjustment_allowed=False`;
- `automatic_activation_allowed=False`;
- `read_only=True`;
- `executed=False`.

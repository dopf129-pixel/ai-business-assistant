# Return Financial Operation Review Candidate v1

Builds a deterministic review artifact from explicitly selected `type_id` values in the real Ozon accrual-type catalog.

Unknown or invalid IDs block the artifact. The contract copies exact source names/descriptions and never infers return semantics.

A ready candidate still has:

- `review_required=True`;
- `mapping_authorized=False`;
- `returns_profit_adjustment_allowed=False`;
- `read_only=True`;
- `executed=False`.

This is a pure contract; no Ozon mutation or profit adjustment is introduced.

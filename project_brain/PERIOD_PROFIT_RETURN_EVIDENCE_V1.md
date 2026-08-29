# Period Profit Return Evidence v1

Adds a read-only service over the existing Ozon `/v1/returns/list` client method.

The service proves whether return records are present for a requested period and optionally an offer. It preserves only descriptive/source fields and explicitly does not infer monetary return impact.

Safety contract:

- `financial_impact_supported=False`;
- `returns_profit_adjustment_allowed=False`;
- `read_only=True`;
- `executed=False`.

This avoids deriving non-buyouts or return losses from cancelled FBO postings and avoids treating undocumented monetary-looking fields as confirmed profit adjustments.

Review classification: Architecture Review Required because a new service is introduced.

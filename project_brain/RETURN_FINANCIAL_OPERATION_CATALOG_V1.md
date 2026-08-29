# Return Financial Operation Catalog v1

Loads the real Ozon finance accrual type catalog through the existing `FinanceService.load_accrual_types()` path.

The catalog exposes only source `type_id`, `name`, and `description` values for review. It does not infer which operations are return-related and does not activate any return-profit mapping.

Safety flags remain explicit:

- `return_classification_applied=False`;
- `mapping_activation_allowed=False`;
- `read_only=True`;
- `executed=False`.

New service => Architecture Review Required.

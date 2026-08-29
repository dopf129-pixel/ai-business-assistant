# Return Financial Operation Selection v1

Builds a human-selection artifact from exact `type_id` values visible in the real Ozon operation review report.

Unknown IDs and empty selections block. Selected rows are copied from the report without semantic inference.

A ready selection has `human_selected=True` but still requires separate authorization:

- `authorization_required=True`;
- `mapping_authorized=False`;
- `returns_profit_adjustment_allowed=False`;
- `read_only=True`;
- `executed=False`.

No Ozon mutation, Product Decision execution, or profit adjustment is introduced.

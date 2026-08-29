# Period Profit Mapping Re-review v1

Adds a read-only, human-controlled re-review workflow for active period-profit mappings when the current Ozon accrual catalog has drifted.

Stages:

1. Build a targeted candidate only for `type_id`s reported as missing or renamed by the mapping quality report.
2. Require explicit human confirmation for every affected operation.
3. Build a replacement mapping draft while preserving unaffected operations.
4. Produce an exact diff against the active mapping.
5. Require a separate `AUTHORIZE` or `REJECT` decision.

Human confirmation supports only explicit actions: `KEEP`, `USE_CURRENT`, `REMOVE`, or `REPLACE` with an exact replacement `type_id` that exists in the current source catalog. No semantic matching, fuzzy search, substring inference, or automatic remapping is allowed.

Authorization remains deliberately limited. Even an authorized replacement only sets `mapping_build_allowed=True`; it keeps `registry_save_allowed=False`, `activation_allowed=False`, `automatic_activation_allowed=False`, and `profit_adjustment_allowed=False`. A later stage must build a normal immutable mapping artifact and pass through the existing persistence/activation workflow.

No Ozon mutation, Product Decision execution, or profit-formula change is introduced.

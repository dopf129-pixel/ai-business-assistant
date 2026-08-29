# Period Profit Mapping Admin Workflow v1

Adds an admin-facing control layer for persisted period-profit mapping revisions.

The workflow is intentionally two-step: first build a preview for `ACTIVATE` or `ROLLBACK`, then require a separate explicit `APPLY` decision. `REJECT` never mutates the registry.

History and preview are read-only. Apply can only switch the active evidence-mapping revision in the local registry; it cannot mutate Ozon, execute Product Decisions, or change the period-profit formula.

Safety remains explicit:

- `automatic_apply_allowed=False`;
- explicit `APPLY` is required before registry activation or rollback;
- `ozon_mutation=False`;
- `profit_adjustment_allowed=False`;
- audit responses explicitly state that Ozon and profit formula are unchanged.

This stage adds a new admin service over the existing registry, so Architecture Review Required.

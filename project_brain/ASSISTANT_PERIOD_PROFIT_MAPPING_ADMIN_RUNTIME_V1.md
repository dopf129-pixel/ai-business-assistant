# Assistant Period Profit Mapping Admin Runtime v1

Adds a natural-language assistant/admin route over the existing period-profit mapping registry admin workflow.

Supported scopes are `RETURN`, `ADVERTISING`, and `STORAGE`. The route can show registry history, build an activation/rollback preview for an exact revision, prepare `APPLY` or `REJECT`, and return an audit response after an explicit apply.

Safety remains explicit:

- ordinary history and preview requests are read-only;
- a revision reference alone never changes the active mapping;
- `REJECT` never calls registry apply;
- only text with a separate explicit apply intent can produce the existing `APPLY` decision artifact;
- registry changes affect evidence mapping only;
- `ozon_mutation=False`;
- `profit_adjustment_allowed=False`;
- Product Decision execution is unchanged and not introduced here.

The mapping-admin runtime is checked before other direct assistant routes so an explicit mapping administration command is not swallowed by general period-profit handling.

This introduces a new assistant runtime service and production routing dependency, so Architecture Review Required.

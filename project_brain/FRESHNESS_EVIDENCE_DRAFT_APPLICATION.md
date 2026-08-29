# Freshness Evidence Draft Application v1

## Goal

Apply validated v28 readiness evidence to a matching Product Task draft object while preserving all business-decision and execution boundaries.

## Allowed mutation

Only these freshness fields may be changed:
- `sales_source_recorded_at`
- `sales_observed_at`
- `stock_source_recorded_at`
- `stock_observed_at`
- `unit_economics_source_recorded_at`
- `unit_economics_observed_at`

The function requires exact `draft_id` and `sku` binding and independently re-whitelists readiness evidence before mutation.

## Audit and idempotency

Each successful application returns:
- changed field names/count
- before/after audit values for freshness fields
- `idempotent_noop=True` when the draft already contains the exact evidence

Business fields are not rewritten.

## Safety boundary

Always remains false:
- `product_decision_recomputed`
- `product_decision_mutated`
- `ozon_mutation_called`
- `execution_allowed`
- `execution_ready`
- `executed`

## Persistence boundary

This stage mutates the supplied draft object only. It does not yet connect that draft to a durable database/file repository. Durable storage will require an explicit repository layer so the implementation cannot accidentally reuse `data/users.json`, the legacy Action Executor, or any mutating Ozon path.

Targeted exact minimal-checkout pytest: `11 passed in 0.05s`.

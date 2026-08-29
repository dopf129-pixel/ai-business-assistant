# Period Profit Mapping Quality v1

Adds read-only quality diagnostics for active `RETURN`, `ADVERTISING`, and `STORAGE` mappings.

The quality layer compares each active mapping with the current real Ozon accrual operation catalog and evaluates:

- active revision age;
- configurable freshness threshold (default 90 days);
- missing source `type_id` values;
- source operation name changes for the same `type_id`;
- manual review requirement;
- deterministic per-scope quality score and consolidated overall score.

Catalog drift is evidence only. A disappeared or renamed operation never causes an automatic remap, activation, registry mutation, Ozon mutation, Product Decision execution, or profit adjustment.

An unconfigured scope is reported as `NOT_CONFIGURED` and is not treated as a defective mapping. If the source catalog is unavailable, configured mappings require review because drift cannot be verified.

Production factory wiring is provided through `create_period_profit_mapping_quality_service()`, using the existing mapping registry plus the real `FinanceService -> ReturnFinancialOperationCatalogService` source.

This introduces a new quality service and production factory, so Architecture Review Required.

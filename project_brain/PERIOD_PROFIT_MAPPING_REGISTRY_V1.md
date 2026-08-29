# Period Profit Mapping Registry v1

Adds local versioned persistence for reviewed and authorized `RETURN`, `ADVERTISING`, and `STORAGE` mapping artifacts.

The registry stores immutable revisions and a separately controlled active revision per scope. Saving a revision does not activate it unless `activate=True` is explicitly supplied. Activation and rollback write lineage events but never mutate Ozon or period-profit business data.

Production loading is read-only: `create_period_profit_query()` loads only active mappings and injects them into existing evidence contracts. Missing registry files or missing active revisions result in no mapping for that scope.

Safety remains explicit:

- only previously authorized immutable mapping artifacts can be persisted;
- unsafe artifacts with profit-adjustment permission are rejected;
- activation changes evidence classification policy only;
- rollback changes the active evidence mapping revision only;
- no Ozon mutation is introduced;
- no automatic Product Decision execution is introduced;
- no return/advertising/storage amount is subtracted from profit again;
- runtime registry data lives under `data/` by default and is not a source-controlled mapping artifact.

This adds a new persistence service and production dependency, so Architecture Review Required.
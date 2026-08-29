# Period Profit Mapping Registry Recovery v1

Adds explicit, fail-closed recovery controls for the period-profit mapping registry.

Stages:

- assistant health route exposes registry health without mutation;
- corrupt registries can produce a quarantine preview;
- preview requires a separate `APPLY` or `REJECT` decision;
- only explicit `APPLY` may move the corrupt runtime file to a quarantine path;
- after quarantine the registry falls back to an empty supported-schema state;
- schema migration is preview-only and reports that no migration implementation is available yet.

Safety remains explicit: no automatic repair, no automatic migration, no Ozon mutation, no Product Decision execution, and no profit adjustment. Quarantine preserves the corrupt source file under a separate runtime path instead of rewriting it.

The recovery runtime is routed before mapping-admin commands so health/recovery language cannot be accidentally interpreted as an activation command.

This adds a new recovery service and assistant runtime route, so Architecture Review Required.

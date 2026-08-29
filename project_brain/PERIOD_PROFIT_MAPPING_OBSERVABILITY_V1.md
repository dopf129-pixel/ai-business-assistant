# Period Profit Mapping Observability v1

Adds read-only operational observability for the persisted `RETURN`, `ADVERTISING`, and `STORAGE` mapping registry.

The observability layer provides:

- registry health snapshot;
- active/latest revision diagnostics per scope;
- stale-active mapping warnings;
- loadable mapping scope summary;
- audit event summary;
- production readiness report.

A stale active revision is advisory only: it does not invalidate a healthy mapping and never switches revisions automatically. Corrupt or non-loadable registries remain fail-closed through the existing registry safety contract.

Period-profit responses may surface stale/corrupt mapping warnings, but these warnings do not change `net_accrual`, profit, coverage semantics, or any Ozon data.

Safety remains explicit:

- read-only diagnostics;
- no automatic mapping activation;
- no Ozon mutation;
- no Product Decision execution;
- no profit adjustment;
- stale status is a configuration warning, not a causal business claim.

A new observability service is introduced and production period-profit wiring is extended, so Architecture Review Required.

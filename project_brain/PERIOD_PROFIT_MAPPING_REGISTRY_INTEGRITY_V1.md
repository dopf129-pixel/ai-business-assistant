# Period Profit Mapping Registry Integrity v1

Stages v114-v118 harden the runtime mapping registry used for `RETURN`, `ADVERTISING`, and `STORAGE` evidence mappings.

The registry now validates schema version `1`, root/scopes structure, revision numbering, immutable revision flags, active-revision references, and deterministic mapping integrity. Mapping IDs are recomputed from canonical operations using the same rules as the authorized mapping builders. A tampered ID or operation payload therefore invalidates the registry for runtime loading.

Registry reads are fail-closed. Invalid JSON, unsupported schema versions, malformed scope state, invalid revision lineage, or mapping-integrity failures make `load_allowed=False` and `writable=False`. Production mapping loaders then receive `None` instead of an unsafe artifact. Corrupt runtime data is not silently replaced or overwritten.

A deliberately older active revision is reported as `active_revision_stale=True` when a newer saved revision exists. This is advisory only: if the active revision is structurally valid and integrity-verified it remains loadable until a human explicitly activates another revision.

The health response exposes schema version, issues, load/write permission, active/latest revision IDs, stale status, and whether the active mapping is loadable. Health checks are read-only and never change Ozon or the period-profit formula.

Safety invariants remain unchanged:

- `fail_closed=True` for corrupt or incompatible registry data;
- no automatic mapping activation;
- no Ozon mutation;
- no Product Decision execution;
- no profit adjustment from mapping activation;
- advertising, storage, and return evidence already represented in `net_accrual` is never subtracted twice.

This modifies a production persistence service and therefore remains Architecture Review Required.

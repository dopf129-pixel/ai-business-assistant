# Decision 066 — versioned FIFO cost ledger with a strict inventory cutoff gate

Date: 2026-11-06  
Topic: implement seller-confirmed FIFO cost history without conflating cost, inventory, planning, and finance sources.

## Context

The repository has dated seller cost history, mutable current-cost projection, Period Profit, Return COGS gates, and tenant-scoped Planning Workspace. FIFO needs an immutable quantity/cost event timeline, but the current Ozon adapters do not prove a common inventory/physical-sale cutoff. Reusing planning persistence for factual cost authority or treating a finance accrual date as a physical outflow would create an unsupported profit result.

## Decision

- Add a dedicated `FifoCostRepository` over the existing tenant-local `ozon_assistant.db` path. It owns only FIFO factual events, stream projections and allocation revisions. It does not create another database or alter `PlanningWorkspaceRepository` ownership. Planning migrations use their own `planning_schema` table; FIFO migrations use a separate `fifo_cost_schema` table and an atomic transaction. SQLite `PRAGMA user_version` is left unchanged.
- Preserve legacy cost tables and behavior before explicit per-SKU FIFO cutover. Do not auto-backfill current/history rows into quantity layers. After cutover, no reader may silently fall back to mutable legacy cost when the FIFO stream is incomplete.
- Keep each finance SKU and posting digest as its immutable sale identity even when an allowlisted, confirmed historical-SKU mapping resolves multiple finance SKUs to the same exact store/product/offer/catalog-SKU FIFO stream. Reconcile the union of those aliases against the complete stream allocation set, then attribute units and COGS back by posting digest; missing or extra sale evidence remains incomplete. A stream-wide layer explanation must not be presented as a per-alias breakdown.
- Store immutable allowlisted FIFO events and immutable allocation revisions; update only a derived stream projection under one SQLite immediate transaction with CAS and idempotency. Corrections append and supersede; they never rewrite prior evidence.
- Treat inventory source, supplier cost, physical movements, and financial recognition as separate evidence. A finance accrual is not a second sale, and current FC02 data does not yet prove physical sale time or a shared stock watermark.
- `INVENTORY_CUTOFF_UNRECONCILED` blocks FIFO COGS from factual Period Profit. An explicitly labeled model/simulation may be separate, but may never be stored or presented as factual COGS. Owner-confirmed inputs retain owner provenance and are not called Ozon facts.
- Reuse `TaxService`, canonical forward price calculation, existing Return COGS recognition/authorization gates, tenant storage/backup and saved-plan snapshot owners. Ozon remains read-only.

## Consequences

- The FIFO source gap is explicit and independently testable. The implementation may ship guarded source diagnostics and model previews, but factual profit integration requires the source gate to close.
- New tables remain in the normal tenant database backup/restore boundary. Migrations are additive and isolated from Planning Workspace's global schema version.
- The change is an architectural extension and requires independent architecture review before merge. No merge, deployment, real seller request, or bot launch is authorized in this implementation task.

## Status

Accepted for implementation within the user-approved FC00–FC35 task; independent review is required before merge. The factual cutoff gate remains blocked pending sanitized owner validation.

## Addendum — 2026-11-07: durable late-entry cases

- Extend this same `FifoCostRepository` and `fifo_cost_schema` boundary to schema v13. Seven transition-case/evidence/preview/commit tables remain in the existing tenant-local `ozon_assistant.db`; do not create a separate database or change Planning Workspace's `PRAGMA user_version`/schema owner.
- Rebuild `fifo_cost_rate_changes` transactionally for the new `cost_input_mode`. Existing rows are carried forward unchanged as `COMPONENTS`; `TOTAL_LANDED` is represented with null component columns. Never invent component splits for a previously recorded total cost.
- Encrypted supply lookup references reuse the credential Fernet key through a shared provider. No new key or secret store is introduced. If the existing key is unavailable or invalid, preserve the non-secret case evidence as awaiting evidence and do not persist a plaintext lookup reference.
- The v12→v13 migration disables foreign-key enforcement only on its own SQLite connection before `BEGIN IMMEDIATE`, restores indexes/triggers, performs `foreign_key_check` before commit, rolls back on any failure, and restores foreign-key enforcement in `finally`. Credential storage format/behavior and existing FIFO history remain unchanged.
- This is a scoped extension of Decision 066, not a new source of accounting truth. It does not close the historical inventory cutoff gate or authorize factual Period Profit integration.

## Addendum — 2026-11-08: exact cutoff partition in Period Profit

- Extend the same tenant FIFO schema to v14 with append-only cutoff mapping-set headers and sale-identity rows. Mapping evidence is committed in the same SQLite transaction as the transition's rate, allocation, projection and `APPLIED` case revision; it is not a second source database or a finance ledger.
- For financial periods that touch the physical cutoff, Period Profit may combine pre-cutoff legacy unit cost at the evidenced physical date and post-cutoff FIFO COGS only through the exact finance-sale identity bridge. A missing, stale or incomplete bridge is an explicit incomplete result. Do not infer the partition from financial recognition dates or silently fall back to allocation dates.
- Financial recognition still determines tax/profit period; physical date determines FIFO ordering and historical legacy rate. The explanation and export projection must carry the same stream, allocation and cutoff-mapping revisions. This remains an implementation extension of the already accepted cutoff gate, not permission to apply synthetic history to the owner store.

## Addendum — 2026-11-08: late-entry completion verification status

- The late-entry implementation through FL32 has synthetic coverage for acceptance evidence across restart, double-confirm concurrency, schema/backup round-trip and idempotent replay. The production code is in the review branch; these checks do not mean it is merged, deployed, or accepted against the owner's live store.
- The case reported by the owner remains `USER_VALIDATION_PENDING` and factual FIFO COGS remains `SOURCE_BLOCKED`. The known `1,191` vs `1,192` inventory discrepancy, missing complete post-05.11 movements, per-supply identities/acts, and exact physical cutoff must be resolved with their own source provenance before applying any history.
- No change to the decision boundary: no inferred receipt, no date-from-status shortcut, and no synthetic acceptance may unlock factual Period Profit.

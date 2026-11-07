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

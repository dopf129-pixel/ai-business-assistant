# Decision 064 — versioned unit-economics evidence and experiment ownership

Date: 2026-10-28
Topic: extend existing per-SKU price planning with auditable evidence and owner-controlled experiments.

## Decision

- Preserve `UnitPriceScenarioService` and the active-store `TaxService` as the only forward calculation and tax owners. The extension is additive; an absent contract keeps legacy semantics and is never relabelled as an extended complete model.
- Normalize new expense and quantity evidence into versioned, exact owner/store/product/offer/SKU/sale-schema contracts. Keep source date basis, coverage, amount sign, numerator/denominator, attribution, status, origin, correction/dedup and component ownership explicit. Missing, partial, unavailable, unknown, conflict, unsupported and confirmed zero are distinct.
- Separate `WINDOW_COST_ALLOCATION` from `STRICT_RETAINED_COHORT`; a period allocation is never called a retained cohort. Reconciliation-only CPC and account residual are never added twice or silently assigned to SKU. Cross-docking retains supplied units as its denominator and is never converted to sold units.
- Use `PlanningWorkspaceRepository` and its tenant SQLite DB as the sole persistence/migration/CAS/backup authority. Experiment phases/results are append-only projections; raw API rows and raw posting/return identifiers remain transient.
- Lifecycle actions are owner-confirmed and revision-bound. The bot does not change Ozon prices, schedule background collection or hide retries. One active experiment/observation guard exists per exact SKU/schema identity, with baseline-to-candidate switch atomic.
- Keep lifecycle states separate from quality/result statuses. A failed gate preserves available monetary evidence but cannot yield strict RUB/unit profit or candidate ranking. Late source corrections append a new result revision and preserve earlier conclusions.
- Keep finite quotas: 100 experiments per store, 10 phases per experiment, 20 result revisions per phase, 64 KiB per serialized record and 10-item repository listing page; stricter existing store-wide caps win. Shared user-triggered source ceiling is 120 seconds/128 actual HTTP attempts or a stricter parent trace.

## Reason

Extended cost evidence combines finance dates, Performance report dates, return status changes, physical supply counts, and manual assumptions. Treating these as interchangeable amounts/units would double-count expense or fabricate per-sale profit. A single canonical calculator and one tenant repository preserve existing tax, rounding, access-control, migration, and backup behavior while allowing an owner-controlled multi-phase comparison.

## Status

Design accepted for W04–W37 implementation. No runtime/schema implementation is claimed in W03. Implementations must follow the gate matrix and migration/transition contracts in `UNIT_ECONOMICS_W03_CONTRACTS_ARCHITECTURE_2026-10-28.md`; deviations require a new reviewed decision before changing shared contracts.

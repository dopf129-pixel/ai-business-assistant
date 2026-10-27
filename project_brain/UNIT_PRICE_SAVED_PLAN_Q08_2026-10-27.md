# Q08 acceptance: frozen tariff and saved-plan compatibility

Date: 2026-10-27  
Implementation branch: `codex/price-profit-per-unit-implementation-20261027`  
Stage: Q08, frozen tariff snapshot and saved-plan integration.

## Accepted behavior

- Current-price and manually confirmed profiles are resolved through the canonical tariff resolver before the existing unit-price forward calculation.
- A single-plan v3 revision freezes the exact tariff source/profile identity, content and state revisions, candidate bands, resolved rate and advertising basis used at capture time.
- Reopening or changing candidate prices reuses that bounded snapshot and performs no source/API/database reads. Explicit refresh creates a new plan revision and can adopt a newer profile revision.
- Single-plan v1/v2 remain readable and frozen. A legacy commission is not applied to a different price; changed-price commission stays unknown until the owner explicitly confirms a rate or refreshes the source snapshot. A refreshed copy does not inherit stale manual commission.
- A complete explicit manual range is selected over one matching current-price point. Competing matching ranges stay `CONFLICT`. Incomplete source/profile results remain unresolved, including `SOURCE_UNAVAILABLE` results with partial candidate records.
- Session-only and persistent profile selection use the same exact owner/store/product/offer/SKU/scheme/date scope. Repeated profile references are deduplicated before resolution.

## Verification

The linked isolated Windows/Python 3.12.10 Q04–Q08 test profile passed **371 tests in 8.41 seconds**. It covered tariff source/resolution/parser, profile persistence and migrations, saved-plan capture/reopen/refresh, scenario calculations, planning adapters, advertising and batch consumers.

The five protected tracked JSON files were hashed before and after the test run; all hashes matched. Tests used a new temporary storage root and pytest basetemp. Dotenv and pytest plugin autoload were disabled. No live Ozon or Telegram requests, real bot process, owner database, `.env`, or ignored runtime storage was used.

## Architecture and limits

Q08 adds a pure frozen-snapshot adapter and extends existing calculator/planning orchestration and the saved-plan allowlist with additive schema v3. `UnitPriceScenarioService` remains the only financial forward engine. Historical v1/v2 payloads are not rewritten. This is an architecture-review-required change. The full repository pytest, CI, backup/restore drill and live owner workflow remain pending later stages; Q08 is not a production-readiness claim.

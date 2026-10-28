# Q09 acceptance: compare candidate prices by unit profit

Date: 2026-10-27  
Implementation branch: `codex/price-profit-per-unit-implementation-20261027`  
Stage: Q09 — explicit 2–10 seller-price comparison.

## Accepted behavior

- The owner can compare 2–10 distinct seller prices. Each available row is calculated by the existing `UnitPriceScenarioService`; comparison does not duplicate tax or rounding formulas.
- Each candidate price resolves its own commission from the same frozen tariff snapshot. A current-price point and a legacy saved-plan rate apply only at their exact source price. A gap, conflict, expired profile or unavailable tariff keeps candidate profit unknown; such a row cannot win as zero.
- The result preserves the target-margin objective and shows the baseline, evidence basis, advertising basis, per-candidate commission/provenance, profit per successful unit, delta versus baseline, and all tied maximum candidates after canonical money rounding.
- The Telegram route confirms application of a selected price by running the canonical forward calculation with the selected row's commission and checking that the calculated profit matches the candidate result. A mismatch leaves the scenario unchanged.
- The first screen calculation captures and freezes the bounded profile set in the scoped active scenario. Candidate edits reuse it. Only explicit owner confirmation of a tariff creates a refreshed scenario snapshot; stale versions are rejected.
- A manual commission entered in the active scenario is an exact-price override only. It may resolve the captured price over an overlapping stored range, but neighboring prices still use the frozen range or stay unknown.

## Verification

Focused isolated Windows/Python 3.12.10 profile: **120 passed in 3.16s** across target planning, public scenario Telegram runtime, tariff profile runtime, saved-plan flow, and snapshot adapter.

Linked Q04–Q09 isolated profile: **378 passed in 8.90s** across 22 tariff, planning, scenario, source, and consumer test files. Five protected tracked owner-data JSON SHA-256 hashes matched before and after. The test run used a new `%TEMP%` storage root and pytest basetemp, with dotenv and pytest plugin autoload disabled. No live credentials, Ozon/Telegram API, owner database, ignored runtime storage, or bot process were used. `git diff --check` passed.

## Architecture and limits

This extends the existing price-planning result and Telegram scenario interaction. `UnitPriceScenarioService` remains the sole financial forward engine; tariff resolution remains snapshot-only during local comparison. A legacy exact-price-only plan can produce one known candidate but cannot substantiate alternative prices. Q09 does not model a price-driven change in advertising efficiency; all rows currently share the explicitly displayed seller-revenue DRR basis. Q10 will add separate advertising modes and compensation thresholds.

This is **Architecture Review Required**. Q09 does not establish that a checked winner is a global optimum or a demand forecast, and the full repository CI is deferred to Q33–Q35.

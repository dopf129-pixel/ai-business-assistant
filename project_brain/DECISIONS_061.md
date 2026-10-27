# Decision 061 — unit price tariff and observation persistence

Date: 2026-10-27
Topic: durable tenant-scoped tariff assumptions and price observations for unit price planning.

## Decision

- Preserve `UnitPriceScenarioService` and active-store `TaxService` as the only forward financial calculation. Resolver, comparison, advertising thresholds and recommendation gates prepare or interpret inputs; they do not reproduce the finance formula.
- Keep the existing tenant `ozon_assistant.db`. `PlanningWorkspaceRepository` remains the single owner of SQLite schema migration, connections, transaction boundaries and additive typed persistence for tariff profile and observation/result revisions. Application services validate and orchestrate; pure resolver/comparison components perform no I/O.
- Manual tariffs are explicit assumptions keyed by owner/store/product/offer/SKU/sale scheme/effective date. A frozen plan records the exact profile revision and resolved rate for each evaluated seller price. A current-price commission point never implies a range.
- An explicit manual commission entered in the active scenario after returning from a legacy plan is represented as a singleton scenario override. It may resolve that exact captured seller price, including over an overlapping stored range, but it must not resolve neighboring prices. Candidate comparison reads one frozen snapshot; local price/advertising edits do not refresh it.
- When one complete confirmed price range and a single current-price point both match the same price, the explicit range is selected. Multiple matching non-point ranges or multiple current points remain a conflict. If the source/profile listing is incomplete, a frozen `SOURCE_UNAVAILABLE` result never resolves later from its partial candidate list.
- Observations are local analytical records created by explicit owner action and explicit completed-day refresh. The bot never changes Ozon price, schedules background reads, infers a past price from the current card, or rewrites previous result versions.
- Use additive schema migration, bounded allowlisted payloads, exact owner/store scope, idempotency and CAS. Old plan schema/calculation versions remain readable and frozen. Any upgrade is an explicit new revision/copy. Tariff changes cannot rewrite saved plans, reports or observations.
- New records stay inside existing backup/restore roots and are covered by isolated synthetic recovery verification.

## Reason

This feature persists seller-owned commission assumptions and historical price evidence, which are planning evidence, not Ozon accounting facts. Reusing the planning database and its transaction/CAS/backup boundaries avoids a second database and preserves tenant isolation and existing saved plans. One canonical calculator keeps tax and rounding behavior consistent.

## Status

Contract adopted for this implementation by the user's task. Q04 implements and tests the pure bounded resolver; Q05 verifies the official API boundary and maps only an exact current-price FBO point, leaving hypothetical ranges unavailable; Q06 adds durable tenant-scoped manual tariff persistence; Q07 wires explicit Telegram input/preview/confirmation with stale-ticket checks and session-only resolver-compatible profiles; Q08 connects tariff resolution to the canonical scenario and freezes single-plan schema v3 while retaining historical v1/v2 behavior; Q09 compares 2–10 prices using candidate-specific tariffs from one frozen snapshot and preserves exact-price manual overrides without propagating them. Q10–Q14 threshold work, Q15 observations, Q26 restore and Q35 exact-head CI remain outstanding. The overall feature is not production-validated.

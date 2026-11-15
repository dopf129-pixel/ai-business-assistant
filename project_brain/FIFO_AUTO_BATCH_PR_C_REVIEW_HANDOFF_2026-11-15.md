# FIFO automatic batch — PR C independent review handoff

Date: 2026-11-15. Status: PR C #736 is open as a draft. The first published revision `9fab872dbb591297d2aae1440cb9370a8c187560` passed exact-head Verify run [43661914317](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/43661914317). The live PR description is the source of truth for the current base/head SHA and exact Verify run; if this packet changes the head, the PR description must be refreshed after CI.

## PR chain and verification state

| Part | PR | Branch | Base | Current reviewed head / Verify |
|---|---|---|---|---|
| Specification | [#733](https://github.com/dopf129-pixel/ai-business-assistant/pull/733) | `codex/fifo-auto-batch-rule-spec-20261113` | `main` | spec head `0fa8b7835829a710bf86adda1c3737d8286c42de`; Verify [43432990867](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/43432990867) passed. |
| PR A | [#734](https://github.com/dopf129-pixel/ai-business-assistant/pull/734) | `codex/fifo-auto-batch-foundation-20261113` | spec branch at `0fa8b7835829a710bf86adda1c3737d8286c42de` | head `305a892d1c3ef730f0796ff9cb8059c8582c0713`; Verify [43596110972](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/43596110972) passed. |
| PR B | [#735](https://github.com/dopf129-pixel/ai-business-assistant/pull/735) | `codex/fifo-auto-batch-sources-20261113` | PR A at `305a892d1c3ef730f0796ff9cb8059c8582c0713` | head `dda4571baa79b95d632391cc0fee5cb7ca21b661`; Verify [43617884850](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/43617884850) passed. |
| PR C | [#736](https://github.com/dopf129-pixel/ai-business-assistant/pull/736), draft | `codex/fifo-auto-batch-integration-20261113` | PR B at `dda4571baa79b95d632391cc0fee5cb7ca21b661` | First revision `9fab872dbb591297d2aae1440cb9370a8c187560`, Verify [43661914317](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/43661914317) passed. Use the PR description for current final revision. |

The PRs are intentionally stacked and draft. Do not merge, deploy, start the bot, or make live Ozon/Telegram requests as part of this review.

## PR C scope

FB20–FB30 wire the existing production composition root, scoped read-only refresh/card and continuation, reviewable supply rows, source-bound owner decisions, freshness/readiness/application gates, FIFO integration and retry behavior, backup/restore, downstream consumer compatibility, full-isolated verification, and owner documentation. The new path never creates cost layers or applies FIFO from a supply rule alone. Independent R1 cutoff/inventory-movement evidence remains required.

## B01–B45 regression map

“Synthetic” means a regression uses fake Ozon transport and temporary SQLite. It does not establish the seller's live payload or the owner's business case.

| Cases | Primary regression files / concern |
|---|---|
| B01–B07, B26–B31 | `tests/test_fifo_cost_batch_rule_regressions.py`, `test_fifo_cost_batch_rule_service.py`, `test_fifo_cost_batch_rule_classifier.py`, `test_fifo_cost_batch_rule_contracts.py`, `test_fifo_cost_batch_supply_store.py`, `test_telegram_fifo_cost_transition_runtime_service.py`; unknown/empty historical total, explicit first-day selection, dated interval boundaries, stale tickets, exact tenant/case/SKU binding, idempotency. |
| B08, B11, B41, B44–B45 | `tests/test_fifo_cost_batch_bundle_normalizer.py`, `test_fifo_cost_batch_supply_source.py`; exact SKU composition, planned quantity kept distinct from dispatched/accepted quantity, empty/partial, unsupported fields/state, incomplete bundle composition. |
| B09–B10, B13, B15 | `tests/test_fifo_cost_batch_supply_deduplicator.py`; order declaration is a control, duplicate/overlap deduplication, cumulative/revised evidence, downward correction review. |
| B12, B14, B16–B17, B34 | `tests/test_fifo_cost_supply_acceptance_reconciliation_service.py`, `test_fifo_cost_transition_supply_reconciliation_service.py`; multiple acts, cumulative accepted totals, explicit zero versus missing, partial accepted subtotal, correction review, no inferred receipt date. |
| B18–B22, B42 | `tests/test_fifo_cost_batch_supply_source.py`, `test_fifo_cost_batch_scan_checkpoint_service.py`; status gaps, cursor/budget limits, overlap/repeated cursor, restart, CAS, TTL, profile binding, stable membership under status refresh. |
| B20–B21 | `tests/test_fifo_cost_batch_scan_checkpoint_service.py`, `test_fifo_cost_batch_supply_source.py`; bounded HTTP/time budget and resumable checkpoint behavior. |
| B23–B25 | `tests/test_fifo_cost_batch_manifest_builder.py`; exact date-window controls, mismatch review, legacy unbounded control remains labeled and does not cap future supplies. |
| B32 | `tests/test_fifo_cost_temporal_rate_replay.py`; historical FIFO rate replay across cost boundaries. |
| B33–B37 | `tests/test_fifo_cost_transition_production_workflow.py`, `test_fifo_cost_transition_readiness_service.py`, `test_fifo_cost_transition_review_service.py`, `test_fifo_cost_transition_apply_service.py`; shipped is not accepted, R1 remains independent, synthetic successful wiring, stale-source apply rejection. |
| B38 | `tests/test_fifo_cost_return_repository.py`, `test_fifo_cost_return_evidence_normalizer.py`; return lineage remains on the source sale/FIFO basis. |
| B39 | `tests/test_saved_planning_plan_telegram_flow.py`; saved downstream plans remain frozen/versioned through restart and revisions. |
| B40 | `tests/test_fifo_cost_transition_schema_v13.py`, `test_fifo_cost_transition_schema_v16.py`, `test_fifo_cost_backup_restore.py`; additive migrations, rollback/future-version failure, data preservation, public backup/dry-run restore/restore for auto rule and manifest. |
| B43 | `tests/test_fifo_cost_batch_rule_classifier.py`, `test_fifo_cost_batch_supply_deduplicator.py`, `test_fifo_cost_supply_acceptance_reconciliation_service.py`; cancellation does not silently erase proven dispatch; corrections require review. |

The run is the authoritative proof that all configured tests executed; the mapping above is a navigation aid, not a claim that every test name contains its B-number.

## Current quantity prompt trace

The former unknown-total prompt no longer asks the owner to calculate every shipment. The existing cost/date/old-stock draft continues into a choice between a dated manual control and `Считать по поставкам Ozon`. The automatic path persists one scoped SKU rule without a lifetime total, refreshes only on explicit owner action, and shows a bounded redacted list. Confirmed dispatch dates after the rule boundary may classify automatically. Same-day `Нет / не уверен` saves a pending empty boundary, includes no first-day shipment by default, and requires exact owner selection from reviewed rows. Opening the card performs no source call. Incomplete coverage, unknown dispatch date, source failure, stale review or quantity unknown remains incomplete; none is changed to zero or a physical inventory fact.

## Source capability and unresolved evidence

See [FIFO_BATCH_SUPPLY_SOURCE_CONTRACT_2026-11-13.md](FIFO_BATCH_SUPPLY_SOURCE_CONTRACT_2026-11-13.md), including its FB19 matrix. Owner-provided official descriptions confirm the parent order list/detail fields and bundle request/response shape, pagination, `sku` and `quantity`. A bundle quantity is declared composition only. The documents do not prove actual dispatch time, physical receipt time, the complete nested supply-state enum, all seller-specific payload behavior, or complete historical inventory/supply coverage. Repeated mutable pages and missing cursor proof fail closed. Test fixtures and the successful end-to-end normalized source are synthetic.

`OWNER_CASE_VERIFIED=false`. The owner's live seller records were not queried; no credentials, private data, or IDs were used. `R1` (a complete cutoff inventory/movement source reconciled with receipt, sale, return and other movements) remains **NOT_VERIFIED**. A rule or even a complete manifest cannot bypass it or authorize factual FIFO apply by itself.

## Storage, rollback and privacy

- PR A adds FIFO schema v17 for scoped immutable rule/decision/observation/control records and a CAS checkpoint while preserving legacy mode.
- PR B upgrades v17 to v18 for scan-to-observation links. Migration tests exercise older-version upgrades, injected rollback and future-version fail-closed behavior; see `tests/test_fifo_cost_transition_schema_v13.py` and `test_fifo_cost_transition_schema_v16.py`.
- Review fixes add FIFO schema v19 continuation side storage; see `DECISIONS_067.md`. The migration is additive and preserves the v18 checkpoint table and its existing <=8 KiB tokens. The side table is included in backup/restore metadata and source fingerprints. Backup/verify/dry-run-restore/restore is covered by `tests/test_fifo_cost_backup_restore.py::test_public_backup_restore_preserves_fifo_auto_batch_rule_and_manifest`.
- Opaque identifiers and continuation/lookups remain encrypted in scoped storage. Telegram selection rows omit raw supply/order IDs, SKU IDs, product names and barcodes. Public status contains bounded counts, status/category summaries and safe issue codes. Synthetic fixtures only; no owner credentials or `.env` content are included.
- Rollback path is the project's verified backup/dry-run-restore workflow. Do not hand-edit FIFO tables or downgrade a schema version.

## Local verification before publication

- Review regressions R1–R8: **125 passed in 8.64s** across the affected FIFO batch service, store, source, manifest, Telegram, contracts and migration modules. The tests cover exact-case binding, legacy identity preservation, rule-chain replay, benign outside/exclusion outcomes, overlapping decision correction, 1 MiB continuation persistence with v18 migration preservation, masked candidate identities, and one-snapshot manifest sealing.
- Schema/checkpoint migration profile: **29 passed in 2.63s**. Full disposable Windows/Python 3.12 suite: **5,446 passed in 108.09s**, no skips/deselections; isolated `compileall -q app tests` passed with one pre-existing float-identity `SyntaxWarning`.
- `git diff --check` passes; no tracked `data/` file is part of the change. `.fl12-deps/` is preserved and excluded.
- FB30 first-day-choice regressions: **36 passed**.
- Linked FIFO batch, transition/readiness/review/apply/service profile after FB30: **177 passed in 20.24s**; all are synthetic/local tests.
- Full configured suite at FB29 SHA `cc329692d5c259595ef1419f9dbfde483071da66`: **5,437 passed in 104.33s**, but it predates the FB30 code change and must not be attributed to PR C final head.
- Production Docker build/runtime smoke and hosted Windows/Linux exact-head CI for the review-fix SHA: pending. Refresh the live PR description and this table after publishing the new head and CI run.
- No live Ozon/Telegram request, owner data, Desktop bot change/start, merge or deployment.

## Review focus

Please examine the integration boundary between rule confirmation, manifest freshness, production readiness and atomic apply; checkpoint resume and source mutation; Telegram stale callback/idempotency; handling of explicit first-day empty selection; preservation of old FIFO/returns/saved-plan behavior; and the strong separation between declared bundle quantities and dispatch/acceptance/R1 facts. Architecture review is required.

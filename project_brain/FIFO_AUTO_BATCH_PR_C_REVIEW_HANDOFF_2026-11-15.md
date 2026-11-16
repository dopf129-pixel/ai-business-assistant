# FIFO automatic batch — PR C independent review handoff

Date: 2026-11-15. Status: PR C #736 is open as a draft. Review-fix code SHA `fe6ad7748601c2759d6c467b7c24ca354785710e` passed exact-head Verify run [43707563054](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/43707563054). The live PR description is the source of truth for current base/head SHA and latest exact Verify run; if this packet changes the head, refresh the PR description after CI.

## PR chain and verification state

| Part | PR | Branch | Base | Current reviewed head / Verify |
|---|---|---|---|---|
| Specification | [#733](https://github.com/dopf129-pixel/ai-business-assistant/pull/733) | `codex/fifo-auto-batch-rule-spec-20261113` | `main` | spec head `0fa8b7835829a710bf86adda1c3737d8286c42de`; Verify [43432990867](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/43432990867) passed. |
| PR A | [#734](https://github.com/dopf129-pixel/ai-business-assistant/pull/734) | `codex/fifo-auto-batch-foundation-20261113` | spec branch at `0fa8b7835829a710bf86adda1c3737d8286c42de` | head `305a892d1c3ef730f0796ff9cb8059c8582c0713`; Verify [43596110972](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/43596110972) passed. |
| PR B | [#735](https://github.com/dopf129-pixel/ai-business-assistant/pull/735) | `codex/fifo-auto-batch-sources-20261113` | PR A at `305a892d1c3ef730f0796ff9cb8059c8582c0713` | head `dda4571baa79b95d632391cc0fee5cb7ca21b661`; Verify [43617884850](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/43617884850) passed. |
| PR C | [#736](https://github.com/dopf129-pixel/ai-business-assistant/pull/736), draft | `codex/fifo-auto-batch-integration-20261113` | PR B at `dda4571baa79b95d632391cc0fee5cb7ca21b661` | Review-fix code SHA `fe6ad7748601c2759d6c467b7c24ca354785710e`; Verify [43707563054](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/43707563054) passed. Use the live PR description for current final revision. |

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

## Additional review findings fixed after R1–R8

- Historical acceptance: when the newest scan still contains a supply, the manifest now reads a bounded history of observations for that exact current supply set. A novel accepted-quantity decrease remains `REVIEW_REQUIRED`; older supplies absent from the latest scan do not leak back into its candidate set.
- Owner membership correction: an existing same-outcome decision for only part of a selected group no longer suppresses a new grouped decision. A later opposite choice and a subsequent correction to the original choice are appended and resolved by confirmation time; conflicting same-time outcomes remain fail-closed.
- Stale preview: confirmation now compares its exact scan ID/revision with the newest scoped checkpoint in the same write transaction. A newer partial, failed, or published scan invalidates the old preview.
- Restart continuation: a fresh Telegram runtime rehydrates the latest exact-scope scan and validates the encrypted continuation locally before offering resume. Restored HTTP-attempt counts are shown as “не сохранено” instead of being fabricated as zero.
- Failed refresh visibility: a new source scan first persists a `STAGING` checkpoint; a no-progress source failure advances it to `FAILED`. This prevents an earlier `PUBLISHED` scan from appearing current after an unsuccessful refresh. Logical checkpoint timestamps advance monotonically to keep newest-scan selection unambiguous under a fixed clock.
- Regressions: `test_latest_manifest_reconciles_acceptance_against_prior_observations`, `test_telegram_bundle_review_confirms_exact_set_without_fifo_writes_or_identity_leaks`, `test_telegram_restores_durable_partial_scan_and_resumes_after_runtime_restart`, and `test_unavailable_new_scan_is_persisted_and_supersedes_previous_published_scan`.

## Local verification before publication

- Review regressions R1–R8: **125 passed in 8.64s** across the affected FIFO batch service, store, source, manifest, Telegram, contracts and migration modules. The tests cover exact-case binding, legacy identity preservation, rule-chain replay, benign outside/exclusion outcomes, overlapping decision correction, 1 MiB continuation persistence with v18 migration preservation, masked candidate identities, and one-snapshot manifest sealing.
- Schema/checkpoint migration profile: **29 passed in 2.63s**. Full disposable Windows/Python 3.12 suite: **5,446 passed in 108.09s**, no skips/deselections; isolated `compileall -q app tests` passed with one pre-existing float-identity `SyntaxWarning`.
- `git diff --check` passes; no tracked `data/` file is part of the change. `.fl12-deps/` is preserved and excluded.
- FB30 first-day-choice regressions: **36 passed**.
- Linked FIFO batch, transition/readiness/review/apply/service profile after FB30: **177 passed in 20.24s**; all are synthetic/local tests.
- Additional five-finding follow-up: focused profile **53 passed**; linked FIFO batch/production/readiness/review/apply profile **189 passed**. `git diff --check` and tracked `data/` equality passed. Exact-head Verify [43754510424](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/43754510424) passed on `26e7d3c4617189d93b57d61405c59acfc803b453`: Windows/Linux full suites and compile, production Docker build/runtime smoke, SHA-bound report and artifact upload all succeeded. The published artifact is `verification-ab329dc31e38d19d1b35cff338f0095585dc1248`.
- Full configured suite at FB29 SHA `cc329692d5c259595ef1419f9dbfde483071da66`: **5,437 passed in 104.33s**, but it predates the FB30 code change and must not be attributed to PR C final head.
- Exact-head Verify [43707563054](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/43707563054) passed on review-fix code SHA `fe6ad7748601c2759d6c467b7c24ca354785710e`, including Windows/Linux full suites, compile, Docker build/runtime smoke and SHA-bound artifact. A documentation-only follow-up may advance HEAD; the live PR body remains the source of truth for latest head/checks.
- No live Ozon/Telegram request, owner data, Desktop bot change/start, merge or deployment.

## Review focus

Please examine the integration boundary between rule confirmation, manifest freshness, production readiness and atomic apply; checkpoint resume and source mutation; Telegram stale callback/idempotency; handling of explicit first-day empty selection; preservation of old FIFO/returns/saved-plan behavior; and the strong separation between declared bundle quantities and dispatch/acceptance/R1 facts. Architecture review is required.

## Initial dispatch-date correction review fix — 2026-11-16

The case `dispatch_date` is the original boundary for the FIFO batch transition. Active successor rules may start later, but the complete immutable chain remains grounded in the first `CONFIRM` event. Freshness now extracts that root boundary from the persisted history and compares it with the current case date at all three paths: active-rule read, pre-source collection basis, and manifest read. If the root event is missing, ambiguous, or outside the bounded history, successors fail closed. A later successor boundary is not compared directly to the original case date.

Regression: `test_rule_rehydration_keeps_closed_base_event_and_manifest_uses_active_interval` first proves a valid Nov 12 successor over the Nov 5 root and a complete current manifest, then edits the case's original date to Nov 14. Active-rule freshness becomes false, collection returns `FIFO_BATCH_RULE_CASE_INPUTS_STALE`, and manifest returns no manifest with `FIFO_BATCH_MANIFEST_RULE_CASE_INPUTS_STALE`. The same test confirms a successor without the root history cannot independently establish freshness. The test reproduced the review finding before the code change. Focused Windows/Python 3.12 rule/manifest profile: **27 passed in 5.30s**. Full isolated pytest: **5,458 passed in 139.69s**; `compileall`, `git diff --check`, and tracked-data equality passed. Exact-head Verify is pending; see the live PR body for current revision and CI.


## Manifest count boundary correction — 2026-11-16

The public `undecided_supply_count` is a subset of supplies found in the current API scan. Missing historical supplies and unmatched owner-only declarations remain unresolved evidence for membership completeness; historical missing keys, unknown totals and issue codes remain sealed. They do not inflate a current-row counter or bypass readiness. This preserves the existing strict `undecided_supply_count <= found_supply_count` contract and avoids an unhandled `CONTRACT_INVALID` when all supplies disappear or missing/owner-only records outnumber current rows.

Regression matrix: 2 prior / 0 current; 3 prior / 1 current; 3 prior / 1 current with unknown dispatch; existing 2 prior / 1 current; plus 0 current / 1 owner-only and 1 current / 2 owner-only. Six cases failed before the fix and pass afterward. Missing-history cases traverse the real readiness review and remain blocked. Full isolated pytest: **5,458 passed in 94.85s**. Compile passed with the existing unrelated float-identity warning; diff checks and unchanged tracked data passed. The initial disposable run omitted a public CSV template (5,457 passed / 1 setup failure); after restoring the template, the entire suite passed. Current-head hosted verification is pending; use the live PR body for exact SHA/check status.

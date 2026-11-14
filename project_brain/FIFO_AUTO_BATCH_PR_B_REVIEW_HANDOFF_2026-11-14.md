# Independent review handoff — FIFO automatic batch PR B

Date: 2026-11-14  
Branch: `codex/fifo-auto-batch-sources-20261113`  
Target base: `codex/fifo-auto-batch-foundation-20261113` at PR A checkpoint `305a892d1c3ef730f0796ff9cb8059c8582c0713`  
PR: [#735 — Add FIFO automatic supply source and manifest](https://github.com/dopf129-pixel/ai-business-assistant/pull/735) (draft, stacked on PR A).  
Published implementation/docs checkpoint: `fdd62a59ff9da483bd1b17e164626fd0bdd3287b`. Verify run [43616178291](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/43616178291) passed for that exact SHA (Windows/Linux full suites, compile, Linux production Docker build/runtime smoke, and SHA-bound report). This handoff is now being finalized with documentation-only changes; the resulting new PR head requires a fresh exact-SHA Verify run before the package is final.  
Classification: architecture review required (new source, normalization, checkpoint, deduplication, and manifest modules; schema v18; cross-service contracts).

## Scope delivered by PR B

FB11–FB18 add a bounded read-only supply scan boundary using existing Ozon list/details wrappers, an explicit unverified bundle adapter boundary, typed bundle normalization, existing acceptance reconciliation, durable encrypted scan checkpoints, owner/API evidence deduplication, a pure quantity manifest, and negative-source regressions. These services are not yet wired into production batch refresh/readiness and do not create FIFO rates, layers, events, allocations, or COGS.

## Verification

- Windows Python 3.12 disposable-copy full suite: **5,405 passed in 99.02s**; `compileall app` passed. The copy excluded `.git`, `.venv`, real `data/`, and `.env`; it used only a synthetic `USN_INCOME` 6% policy, sanitized `.env.example`, and the preserved dependency bundle. Test runtime storage was confined to the disposable copy. One preliminary attempt had 8 isolation-setup failures because it set a storage-root override and excluded the sanitized example file; the corrected clean run passed without code changes.
- Linked FIFO batch source/normalizer/acceptance/checkpoint/dedup/manifest/schema plus existing cross-docking and planning cross-docking regressions: **233 passed in 9.62s**.
- Changed modules and linked tests compiled; `git diff --check` passed; `git diff --exit-code -- data` passed. `.fl12-deps/` remains untracked and excluded. PR B exact-head hosted CI is pending until publication.
- No live Ozon/Telegram request, local Desktop bot, owner DB, merge, or deployment was used.

## Source capability matrix and unresolved source gaps

The authoritative matrix is in [FIFO_BATCH_SUPPLY_SOURCE_CONTRACT_2026-11-13.md](FIFO_BATCH_SUPPLY_SOURCE_CONTRACT_2026-11-13.md), section “FB19 — source capability matrix at PR B checkpoint.” In short:

- List and details calls use existing wrappers with page/detail bounds, budgets, continuation validation, overlap checks, and fail-closed unknown-state handling. This verifies the local adapter boundary only; Ozon's raw schema, complete raw state enum, cursor terminal proof, and complete historical coverage remain unverified.
- Ozon's public guide confirms the bundle operation concept (`supply_id` + `bundle_id`, SKU and quantity result), but not exact request/response fields, pagination, mapping to nested supplies, or planned-versus-shipped semantics. The adapter intentionally returns `UNKNOWN` with zero HTTP attempts; no guessed payload parser is included.
- Acceptance acts use the existing normalizer/reconciler. Act creation/capture time does not establish physical receipt time.
- A complete inventory movement source is still unknown. R1 remains an independent blocker to factual FIFO apply.

## B-matrix ownership

| Matrix rows | Coverage location / current status |
|---|---|
| B01–B07 | Rule continuation/confirmation/classification regressions in `test_fifo_cost_batch_rule_regressions.py`, `test_fifo_cost_batch_rule_service.py`, `test_fifo_cost_batch_rule_classifier.py`, and the existing `test_telegram_fifo_cost_transition_runtime_service.py`. |
| B08, B11, B41, B44–B45 | `test_fifo_cost_batch_bundle_normalizer.py`, `test_fifo_cost_batch_supply_source.py`; exact SKU, planned vs shipped, empty/partial, unknown raw fields, and missing composition. |
| B09–B10, B13, B15 | `test_fifo_cost_batch_supply_deduplicator.py`; parent ORDER is not added to child supplies, repeated evidence is deduplicated, and novel cumulative decreases require review. |
| B12, B14, B16–B17, B34 | `test_fifo_cost_supply_acceptance_reconciliation_service.py` and `test_fifo_cost_transition_supply_reconciliation_service.py`; partial/missing acts, known zero, multiple acts, corrections, and no invented receipt time. |
| B18–B22, B20–B21, B42 | `test_fifo_cost_batch_supply_source.py` and `test_fifo_cost_batch_scan_checkpoint_service.py`; status gaps, cursor/budget limits, repeated/overlapping pages, restart, CAS, TTL, and profile binding. |
| B23–B25 | `test_fifo_cost_batch_manifest_builder.py`; dated exact-window controls, mismatch review, legacy unbounded label, and no permanent cap. |
| B26–B31 | `test_fifo_cost_batch_rule_service.py`, `test_fifo_cost_batch_rule_classifier.py`, `test_fifo_cost_batch_supply_store.py`, `test_fifo_cost_batch_rule_regressions.py`, and `test_telegram_fifo_cost_transition_runtime_service.py`; version boundary, stale preview/callback, exact scope and idempotent confirmation. |
| B32–B39 and B43 | End-to-end physical receipt, sale/return lineage, frozen downstream plan, and cancellation/return movement behavior remain PR C responsibilities; not claimed complete by PR B. |
| B40 | Additive FIFO schema migration and injected rollback/version-isolation regressions are present in PR A/PR B migration tests. Full backup/restore acceptance remains FB28 in PR C. |
| B36–B38 | Positive prepare/apply/restart/retry, stale apply, and old-cost return lineage require the integration workflow and remain PR C. |

## Migration, data, and privacy review

- FIFO schema changes are additive. PR A introduced v17; PR B introduces the v17→v18 scan-observation/checkpoint migration. Existing migration rollback coverage and `PRAGMA user_version` isolation protect Planning; full backup/restore is deferred to FB28.
- Opaque supplier identifiers are encrypted in durable lookup payloads. Public manifest summaries and callbacks expose no raw supply/order IDs. Owner declarations and Seller API observations preserve separate provenance; parent ORDER controls are not counted as additional supplies.
- Existing legacy-total mode remains default for saved cases. Automatic source mode is explicit. None of these source totals initializes an infinite stock balance or proves inventory movements.
- No owner data or credentials are used in tests or included in this handoff.

## Review request

Please review the immutable rule/scan binding, checkpoint CAS and encryption boundary, exact SKU/supply identity, parent-vs-child deduplication, partial/unknown quantity semantics, manifest freshness and date-window controls, and the intentional absence of a raw bundle adapter. Do not interpret this PR as claiming automatic production-complete quantities or R1 closure.

# FIFO late-entry completion — independent review packet

## Independent follow-up review R9–R11 — 2026-11-13

- **R9 / baseline attribution:** Period Profit exposes full-month SKU COGS, not COGS attributed to each affected finance identity. The impact now stays candidate-only unless full-month SKU COGS exactly equals the reconstructed baseline subset; it no longer labels an unproven difference as earlier same-SKU cost. Exact per-identity attribution is not implemented, so incomplete attribution cannot produce a profit delta.
- **R10 / cutoff mapping:** the production collector receives the exact typed READY `FifoCutoffBridgeResult`. It requires a complete bijection between the finance batch and pre/post cutoff bridge identities, exact reconstruction-to-post-cutoff equality, matching source fingerprint/scope/case revision, and valid physical dates. It aggregates only post-cutoff identities; it does not silently drop unknown finance rows.
- **R11 / reopen marker:** the `last_expired_preview_reopen` audit marker is excluded from evidence fingerprints. A repository-backed regression covers a fresh prepare, TTL expiry, exact CAS reopen, and second prepare with the same immutable month snapshot and reconstruction fingerprint.
- Local verification: linked FIFO profile **59 passed**, full isolated pytest **5,287 passed in 92.32s**, compileall and diff checks passed, and tracked `data/` is unchanged. Full-suite test copy excluded owner data and used a synthetic tax policy. PR #732 checks should be consulted for hosted exact-head status.
- **R1 remains open:** no supported complete inventory movement ledger has been established; the owner's real cutoff case remains unverified. This packet does not claim factual FIFO COGS or readiness to apply the owner's case.

## Owner-confirmed cutoff receiving follow-up — 2026-11-10

- The owner approved manual entry only for the missing `supplier_receiving` bucket. The Telegram path binds the nonnegative whole-number entry to one tenant/store/SKU case, the exact saved one-day stock report and cutoff; explicit zero is preserved. It is not represented as Ozon data, and no current act/status date is backdated.
- The typed cutoff bridge carries the owner input separately from accepted FIFO stock. Atomic initial-cutover validation rereads the encrypted, confirmed cutoff evidence and the latest matching opening composition; an unknown report `reserved` bucket is resolved only from that owner-confirmed composition. A regression proves receiving units cannot be added to FIFO opening layers.
- Local linked verification after this follow-up: 77 focused tests passed; positive/negative workflow plus atomic-apply profile: 21 passed; isolated full pytest: **5,264 passed in 87.28s**; compile/data/diff checks passed. Current-SHA hosted CI remains pending until publication. No owner data, live seller calls, Telegram or bot process was used. The actual owner cutoff quantity and real-case apply remain unverified; not merge-ready until CI/review closes.

## Follow-up FR27/FR30 checkpoint — 2026-11-10

- The current local follow-up fixes the missing `TaxService` import in the production assistant factory and retains a supported degraded composition when Period Profit runtime is absent. Late-entry/backup test fixtures now supply the full-month bounds and exact reconstruction/tax-policy fingerprints required by the strict preview contract.
- The stock-management importer maps known Ozon sub-buckets into canonical defective/seller-withdrawal totals and preserves the original source values. It leaves `supplier_receiving` unknown when the workbook omits it. A production-path regression verifies `SOURCE_BLOCKED`, `ready_to_apply=False`, and `AWAITING_EVIDENCE`; it does not fabricate readiness.
- Linked correction/backup/production profile: **67 passed**. Isolated disposable-copy full pytest: **5,258 passed in 86.19s** with a synthetic tax configuration; compileall and preserved-data checks passed.
- The positive FR27 prepare/apply/restart path remains blocked by the absence of authoritative historical `supplier_receiving` at cutoff. The worktree changes are not committed or published and have no current-head hosted CI result. PR #730 and the follow-up are **not ready to merge**; FR28–FR31 remain open by dependency. `OWNER_CASE_VERIFIED=false`.

Date: 2026-11-08  
Specification: [LUNA_FIFO_LATE_ENTRY_COMPLETION_TASK_2026-11-07.md](LUNA_FIFO_LATE_ENTRY_COMPLETION_TASK_2026-11-07.md), PR #727  
Architecture contract: [DECISIONS_066.md](DECISIONS_066.md)  
Acceptance matrix: [FIFO_LATE_ENTRY_NUMERICAL_ACCEPTANCE_FL30_2026-11-08.md](FIFO_LATE_ENTRY_NUMERICAL_ACCEPTANCE_FL30_2026-11-08.md)  
Execution log: [LUNA_FIFO_LATE_ENTRY_COMPLETION_PROGRESS_2026-11-07.md](LUNA_FIFO_LATE_ENTRY_COMPLETION_PROGRESS_2026-11-07.md)

## Delivery stack and review boundary

These are three dependent PRs. Review and merge them in order; do not merge a dependent PR before its base. PRs #728 and #729 have earlier exact-head green runs. PR #730 is **not ready to merge**: independent review found production wiring and multi-rate replay gaps, and the correction set below has not yet been committed or verified on a current head. Earlier green runs do not cover these changes.

| PR | Scope | Base | Head at stack publication | Changed files | State |
|---|---|---|---|---:|---|
| [#728](https://github.com/dopf129-pixel/ai-business-assistant/pull/728) | FL00–FL11: foundation, case/evidence store, supply observations | `main` `d8d4ba00c85acf14ba9a960f56a755fbe30b555c` | `5b4f85881301b8d5b4a7977d67fa59e13d2647db` | 33 | Ready for review; exact-head CI green |
| [#729](https://github.com/dopf129-pixel/ai-business-assistant/pull/729) | FL12–FL23: reports, reconciliation, replay, atomic apply | PR #728 head `5b4f85881301b8d5b4a7977d67fa59e13d2647db` | `7abf5d79d608bf377f79df3b425b50d73de4d81c` | 44 | Ready for review; exact-head CI green |
| [#730](https://github.com/dopf129-pixel/ai-business-assistant/pull/730) | FL24–FL35: Telegram, consumers, Period Profit, acceptance and this packet | PR #729 head `7abf5d79d608bf377f79df3b425b50d73de4d81c` | Previous published SHA `5178d50110a445e8313e7e4b2979cfc43dcfbe89`; local corrections are uncommitted | 48 + local follow-up | **Not ready**; production bridge/apply wiring and multiple-rate replay remain unresolved; current exact-head CI pending |

### Current dependent correction PRs — 2026-11-10

| PR | Scope | Base | Head | Hosted checks |
|---|---|---|---|---|
| [#731](https://github.com/dopf129-pixel/ai-business-assistant/pull/731) | FR02–FR11: temporal replay and multi-rate readers | PR #730 head `8e6b528c462c322b78b0c5e1d82fb782f4bbeab4` | `af7d93324eea9952d60fc26553d8ed673bd8834f` | Full isolated suite: 5,170 passed. Verify run [42790983173](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/42790983173) passed Windows/Linux and production Docker build/runtime smoke. No B-scope production regressions remain in this PR. |
| [#732](https://github.com/dopf129-pixel/ai-business-assistant/pull/732) | FR12–FR31: durable bridge, review/apply, production integration, owner cutoff evidence | PR #731 head `af7d93324eea9952d60fc26553d8ed673bd8834f` | Implementation integration checkpoint `0ae37298b832775c1f6431a97924420b311ec358` | Verify run [42793814822](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/42793814822) passed Windows/Linux full suites, compile, Docker build/runtime smoke, and SHA-bound report. A documentation-only status-sync commit follows; use PR #732 Checks for the exact latest head. Owner cutoff and real-case apply remain unverified. |

## R-A / R-B remediation map

| Finding | Changed functions and scope | Regression evidence |
|---|---|---|
| R-A — no production path to READY/APPLIED | PR #732: `create_fifo_cost_transition_workflow` / `create_telegram_assistant`; `FifoCostTransitionEvidenceService.load/build_cutoff_bridge`; `FifoCostTransitionReviewService.assess`; `FifoCostTransitionApplyService.prepare/read_preview/apply`; repository preview/commit transaction; Telegram evidence and exact-preview callbacks. | `test_production_workflow_builder_wires_durable_evidence_review_apply_and_runtime`; `test_complete_saved_sources_rebuild_the_actual_cutoff_bridge_after_restart`; `test_prepare_seals_real_impact_without_changing_fifo_until_apply`; `test_apply_commits_exact_seal_and_recovers_same_commit_after_restart_and_ttl`; `test_ready_preview_ticket_binds_exact_persisted_seal_and_replays_commit`. Synthetic sources and temporary SQLite only. |
| R-B — replay does not support multiple rates | PR #731: temporal replay kernel and `FifoCostReplayService.preview`; repository prefix replay and rate-change preview/commit; `FifoCostHistoryService` per-rate balance reader; return/outflow lineage; current unit-cost adapter. The single-open-rate exception is explicit and quantity remains unknown; missing multi-rate rows remain blocked. | `test_mr01_mr02_mr03_pure_kernel_replays_three_rates_without_inventing_receipts`; `test_fr09_replays_three_rates_from_prefix_and_publishes_atomically`; MR04–MR07 replay/return tests; `test_fr11_history_current_cost_export_and_period_profit_use_replayed_rates`; current-consumer regression. |

## MR01–MR22 numerical acceptance trace

All rows are synthetic; no owner business values are used to construct a passing fixture. Implementation integration SHA `0ae37298b832775c1f6431a97924420b311ec358` passed Windows/Linux/Docker Verify; this packet is then updated by a documentation-only status sync, whose current-head result is linked from PR #732 Checks. MR01–MR11 are also covered by PR #731's exact-head Verify. Owner-case verification remains false.

| Matrix | Test evidence | Result basis |
|---|---|---|
| MR01–MR03 | `test_mr01_mr02_mr03_pure_kernel_replays_three_rates_without_inventing_receipts`; `test_fr09_replays_three_rates_from_prefix_and_publishes_atomically` | Exact COGS 92.30 / 1614.20 / 166.00 ₽, aggregate 1,872.50 ₽, 10-unit predecessor residual, 7-unit residual, atomic publication. |
| MR04–MR05 | `test_mr04_mr05_return_from_closed_rate_restores_cost_and_origin_before_current_rate`; `test_fr10_partial_return_restores_last_fifo_basis_for_mr04_mr05` | Return restores 16 ₽ lineage at return position; resale adds 16 ₽, aggregate 1,888.50 ₽, previous sale COGS unchanged. |
| MR06 | `test_mr06_outflow_consumes_only_finite_fifo_layers_before_rate_sale` | Outflow 21 ₽ is separate; sales COGS 85.95 ₽. |
| MR07 | `test_mr07_open_rate_values_sales_but_never_claims_known_quantity_or_values_outflow` | Sale COGS 58.60 ₽; known quantity stays unknown; unsupported outflow blocks. |
| MR08 | `test_fr06_end_of_local_date_boundary_follows_same_day_sale`; `test_fr06_exact_timestamps_compare_in_store_timezone_not_utc_date` | Store-local end-of-day and UTC/local date crossing. |
| MR09 | `test_fr06_exact_same_instant_boundary_and_sale_block_when_order_changes_basis`; `test_fr08_repository_blocks_missing_rate_reconciliation_and_keeps_no_write` | Ambiguous or unreconciled order blocks with no business write. |
| MR10 | `test_fr06_duplicate_boundary_and_permuted_source_rows_keep_one_stable_fingerprint`; `test_fr06_exact_duplicate_sale_page_collapses_to_one_sale_but_conflicting_duplicate_blocks`; `test_apply_commits_exact_seal_and_recovers_same_commit_after_restart_and_ttl` | Duplicate/permuted inputs normalize deterministically; exact retry keeps one commit. |
| MR11 | `test_late_entry_requires_complete_financial_sale_identity_mapping` | Missing/foreign historical alias mapping stays an explicit identity blocker. |
| MR12–MR15 | `test_late_entry_matches_mr12_to_mr15_canonical_tax_and_profit_matrix` | Existing canonical TaxService; expected tax/profit deltas 12.70 / 12.70 / 10.79 / 12.70 ₽. |
| MR16 | `test_missing_financial_baseline_returns_candidate_only_without_ready_seal`; `test_late_entry_without_before_baseline_returns_candidate_cost_only_by_financial_period` | Candidate-only; comparison/tax/profit delta is unknown; no READY/APPLIED. |
| MR17 | `test_late_entry_never_treats_physical_date_as_financial_period`; `test_late_entry_impact_covers_every_financial_period_in_dependent_sale_horizon` | Physical sale date controls FIFO; each complete finance period controls profit/tax; complete horizon required. |
| MR18 | `test_late_entry_impact_keeps_non_sale_outflow_out_of_sales_units_and_cogs`; `test_fr11_history_current_cost_export_and_period_profit_use_replayed_rates` | Outflow is separate from sales COGS; opening units are not consumed twice. |
| MR19 | `test_new_stock_evidence_after_ready_preview_invalidates_confirmation_without_fifo_writes`; `test_changed_tax_stock_bridge_and_return_coverage_never_partially_apply` | Changed evidence/tax/coverage makes seal stale; no partial apply. |
| MR20 | `test_two_concurrent_confirms_apply_one_fifo_transition`; `test_apply_same_key_concurrent_services_commit_one_transition` | One durable transition; other caller receives exact idempotent result or CAS conflict. |
| MR21 | `test_unconfirmed_value_and_cross_store_callback_never_write_transition_case`; `test_switching_fifo_case_invalidates_old_physical_preview_without_closing_either_case`; `test_backup_restore_preserves_late_entry_states_ciphertext_and_single_apply` | Wrong scope, stale callback or wrong key does not apply, leak, or erase saved evidence. |
| MR22 | `test_fr27_production_workflow_requires_exact_owner_cutoff_receiving_bucket`; owner acceptance guide | Missing value blocks; explicit owner input remains separate from Ozon and opening FIFO stock. No actual historical count was provided or asserted; `OWNER_CASE_VERIFIED=false`. |

Exact test commits and Verify run URLs are listed in the current PR table above and the PR checks. Do not use the owner-specific 1,191/1,192/148 quantities as synthetic expected output.

## Follow-up review corrections — 2026-11-08

| Finding | Status | Evidence / remaining work |
|---|---|---|
| P1 — production positive path absent: factory does not provide a cutoff-bridge evidence builder or atomic apply orchestration; `assess()` still passes `cutoff_bridge=None` | **Open** | The current UI can save and inspect evidence but cannot reach a real READY/APPLIED path. Implement persisted owner-document bridge input, production assembly, and repository preview/commit wiring; exercise it through production factory. |
| P1 — same report cannot be imported then owner-confirmed for its period | **Fixed locally** | Separate immutable report-period confirmation evidence and idempotency; tests cover original report preservation and same-file confirmation. |
| P1 — any return/non-sale movement blocks transition | **Fixed locally with fail-closed limits** | Typed exact movement proof is accepted only when it matches persisted events and the originating sale; unsupported transfer, missing origin, duplicate or over-quantity movement still blocks. |
| P2 — READY cannot resume after restart | **Fixed locally** | Fresh runtime resumes as read-only summary; it never reopens the sealed case as editable. |
| P2 — later ordinary cost change fails after a late-entry replay | **Partially fixed locally** | One ordinary rate can follow a complete, source-matched replay. More than one active rate still returns `FIFO_REPLAY_RATE_TRANSITION_UNSUPPORTED`; add multi-rate segment replay and regressions before claiming FL20 complete. |
| P2 — historical finance SKU aliases are silently lost | **Fixed locally** | Exact historical aliases now require seller-confirmed mapping bound to current product/offer; missing mapping raises an explicit bridge blocker. |

Local correction verification: FIFO-focused profile **110 passed in 8.23s**; full Windows pytest in a disposable worktree **5,115 passed in 61.10s**; compileall, diff check and unchanged tracked `data/` pass after restoring the initial harness-mutated `data/tasks.json` from Git. Remote CI and current exact-head verification remain pending. Do not merge PR #730 yet.

The branch PR1 head has GitHub Verify run [42433357867](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/42433357867) with Windows verification and Linux full verification plus production Docker build/runtime smoke all successful. PR2 head run [42480102151](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/42480102151) has the same checks successful. Integration SHA `5178d50110a445e8313e7e4b2979cfc43dcfbe89` passed [42480784925](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/42480784925); this status-sync commit advances PR #730 again, so use the newest successful run shown on that PR.

## Changed-files map

The GitHub “Files changed” tab on each linked PR is the exact exhaustive inventory. This map identifies the review responsibility of each group and the principal code paths.

| PR | Area | Primary paths and responsibility |
|---|---|---|
| #728 | Typed transition/evidence contracts and additive repository | `app/services/fifo_cost_transition_contracts.py`, `fifo_cost_transition_store.py`, `fifo_cost_transition_service.py`, `fifo_cost_repository.py` — case revisions, evidence, tenant/SKU scope, CAS, idempotency, migration and durable reads |
| #728 | Supply source and acceptance | `fifo_cost_source_collection_service.py`, `fifo_cost_source_normalizer.py`, `fifo_cost_transition_supply_refresh_service.py`, `fifo_cost_supply_acceptance_reconciliation_service.py` — bounded source calls, observations, partial/cumulative acts and preserved missing evidence |
| #728 | Existing user entry point | `telegram_fifo_cost_history_service.py`, existing FIFO history/transition UI tests — access before FIFO initialization without changing legacy cost mode |
| #729 | Owner report import and parsers | `fifo_cost_report_import_service.py`, `fifo_cost_report_import_worker.py`, `fifo_cost_report_import_worker_client.py`, `fifo_cost_stock_management_import_service.py`, `telegram_fifo_cost_report_import_service.py` — allowlisted turnover/stock evidence, bounded worker, case-bound preview/import |
| #729 | Reconciliation and source proof | `fifo_cost_transition_supply_reconciliation_service.py`, `fifo_cost_transition_opening_proposal_service.py`, `fifo_cost_transition_readiness_service.py`, `fifo_cost_cutoff_bridge_service.py` — keep declared, observed, accepted and pending quantities separate; require exact physical-sale/cutoff proof |
| #729 | Reconstruction and apply | `fifo_cost_replay_service.py`, `fifo_cost_late_entry_reconstruction_service.py`, `fifo_cost_late_entry_impact_service.py`, `fifo_cost_transition_activation_proposal_service.py`, `fifo_cost_repository.py` — deterministic FIFO replay, canonical period/tax impact, preview/CAS/atomic transition |
| #730 | Wizard, navigation and cache | `telegram_fifo_cost_transition_runtime_service.py`, `telegram_fifo_cost_history_service.py`, `assistant_button_handler_service.py`, `telegram_assistant_factory.py`, Telegram adapters — durable case lifecycle, opaque callbacks, isolated refresh and invalidation |
| #730 | Economics and period calculation | `fifo_cost_period_profit_source_service.py`, `period_profit_effective_cost_sale_quantity_summary_service.py`, `period_profit_fifo_explanation_view_service.py`, `period_profit_summary_service.py`, `product_unit_economics_query_service.py` — current cost, saved plan compatibility, exact physical-to-financial sale mapping and redacted explanation/export |
| #730 | Compatibility/acceptance | `fifo_cost_repository.py`, `test_fifo_cost_backup_restore.py`, `test_fifo_cost_transition_schema_v13.py`, `test_fifo_cost_transition_atomic_apply.py`, `test_fifo_cost_period_profit_source_service.py`, `test_telegram_fifo_cost_transition_runtime_service.py`, user guide and project brain — migrations, restart, backup/restore, concurrency and owner instructions |

Each PR also changes its focused regression tests, `CHANGELOG.md`, `project_brain/CURRENT_STATE.md`, and `project_brain/TEST_MAP.md`; the final integration adds the numerical acceptance crosswalk and owner-facing guide. The full 40-case map is in the linked acceptance matrix.

## Requirement-to-implementation crosswalk

| Specification responsibility | Implementation and evidence to inspect |
|---|---|
| FL00–FL05: preserve old accounting before FIFO; typed case and evidence lifecycle | Contracts/store/repository migration and CAS; `test_fifo_cost_transition_schema_v13.py`, `test_fifo_cost_transition_store.py`, `test_fifo_cost_transition_service.py`, `test_fifo_cost_repository.py`; existing FIFO history and Period Profit remain canonical until apply |
| FL06–FL11: full cost without fabricated components; individual supply declarations and changing source observations | TOTAL_LANDED/COMPONENTS, encrypted lookup, observation/act reconciliation and shared request budget; `test_fifo_cost_transition_supply_declarations.py`, `test_fifo_cost_transition_supply_refresh_service.py`, `test_fifo_cost_transition_supply_refresh_durable_acceptance.py` |
| FL12–FL17: supported report formats, contextual import, stock/turnover bridge and missing-evidence queue | Parser/worker/import/reconciliation/readiness; `test_fifo_cost_report_import_service.py`, `test_fifo_cost_stock_management_import_service.py`, `test_fifo_cost_transition_supply_reconciliation_service.py`, `test_fifo_cost_transition_readiness_service.py` |
| FL18–FL21: physical cutoff proof, finite opening layers, stable replay, returns and non-sale movements | Exact finance identity plus documented physical date/quantity; `test_fifo_cost_cutoff_bridge_service.py`, `test_fifo_cost_replay_service.py`, `test_fifo_cost_late_entry_reconstruction_service.py`; unsupported/ambiguous records remain blockers |
| FL22–FL23: before/after period effect and positive-path atomic apply | Existing TaxService/Period Profit integration and one transaction for stream/rate/layers/allocation/mappings/case; `test_fifo_cost_late_entry_impact_service.py`, `test_fifo_cost_transition_atomic_apply.py`, `test_fifo_cost_period_profit_source_service.py` |
| FL24–FL29: menu before initialization; resumable wizard; verify/review/apply consumers; history and refresh | `test_telegram_fifo_cost_history.py`, `test_telegram_fifo_cost_transition_runtime_service.py`, `test_fifo_late_entry_current_consumers.py`, `test_fifo_cost_period_profit_source_service.py`, `test_fifo_telegram_navigation_regressions.py` |
| FL30–FL32: all independent numeric cases, security/navigation/concurrency, migration and restore | Matrix N01–N40; `test_fifo_cost_transition_atomic_apply.py` fault injection and two-client race; `test_fifo_cost_backup_restore.py`; schema migration/foreign-key/rollback tests |
| FL33–FL35: owner guide, latest-head verification and handoff | `docs/fifo-cost-history-user-guide.md`, `FIFO_COST_OWNER_ACCEPTANCE_2026-11-06.md`, this packet, stage journal, exact current GitHub Verify runs |

### Positive commit path (review closely)

The **intended** path is: context-bound wizard save → persisted owner declarations and allowlisted reports → complete readiness/source proof → exact sale/cutoff bridge → deterministic replay and independent period/tax impact → sealed READY preview → `commit_transition_case` revalidates case revision, preview fingerprint/expiry, evidence set, tax policy, stock/return bridge and current FIFO revision inside a write transaction → rate, opening layers, replay allocation, sale mappings, audit and case revision commit together. The repository commit and rollback boundaries have synthetic tests, but the production Telegram runtime does not yet assemble the bridge or invoke this commit path. Therefore those tests do **not** prove a usable production positive path; this is an open P1 review finding.

## Architecture and persistence

- This extends Decision 066 and the existing tenant-scoped `FifoCostRepository`, current-cost resolver, Period Profit and `TaxService`; it does not introduce a second profit formula or ledger.
- The tenant FIFO schema advances additively through the specified v12→v13 transition tables and v13→v14 cutoff sale mappings. Planning schema and `PRAGMA user_version` are unchanged. Inspect `test_fifo_cost_transition_schema_v13.py` and `test_fifo_cost_backup_restore.py` for migration, rollback, foreign keys, v14 restore and replay behavior.
- Writes remain append-only/revisioned; preview is read-only. Failed/stale application returns without partial FIFO writes. Backup restore preserves encrypted references; the wrong key does not relabel a declaration as absent.
- No new runtime dependency is introduced. No architectural decision supersedes Decision 066.
- Classification: **Architecture Review Required**. The combined stack adds new repository/service flows, tenant persistence schema and production Telegram/Period Profit integration; review every boundary and contract above.

## Numeric acceptance and evidence limits

The independent Decimal controls are N04 `6234+600+148=6982` (declarations, not acceptance), N14 `1182+9=1191` (FBS return is a subset), N17 `4492+0-775-5-3712=0`, N21 five-unit COGS `92.30` with 98 new units remaining, N24 profit delta `+12.70` under no tax, N25 the same delta under 6% USN income tax, N27 pre-cutoff COGS `42.00` separate from later FIFO, and N29 `21.00` non-sale withdrawal excluded from sales COGS. N01–N40 test mapping is in the numerical matrix.

The owner's real case is **not applied**. Known statements remain owner-declared facts only: 21.00 ₽ old total landed cost, 14.65 ₽ new total landed cost, dispatch on 05.11, declared new shipment total 6,982, old home/transit zero, new home quantity unknown, and 148 units temporarily absent from the available-stock API view while RECEIVING. The inspected stock report shows 1,191 while the Google Sheet shows 1,192 without a shared documented source watermark. Turnover currently covers only 04–05.11 and balances arithmetically, but does not identify exact physical sale dates/quantities or cover 06–07.11.

Therefore preserve `USER_VALIDATION_PENDING` and `SOURCE_BLOCKED`. Do not promote 6,982 to accepted inventory, infer missing quantities as zero, average the 1,191/1,192 readings, treat report filename or dispatch date as physical receipt/cutoff, or state that historical profit changed. Required evidence is itemized in the owner acceptance checklist.

## Verification and data integrity

- Local full Windows pytest on code/test SHA `4771794e4372c5443ab65cee349d2e673508118e`: **5104 passed in 75.99s**. The exact PR Verify workflow also runs full Windows and Linux suites, compile checks, production Docker build and runtime health/import smoke. Use only the latest successful run attached to each current PR head; exact run links for the final heads are in the PR descriptions and CI checks.
- `python -m compileall -q app tests`, `git diff --check`, and `git diff --exit-code -- data` passed in the implementation worktree. Full pytest ran in disposable detached worktrees; no actual owner XLSX, `data/` source file, tenant database, live Ozon/Telegram request or bot process was used.
- Temporary `.fl12-deps/` is an existing untracked local test dependency directory; it was kept out of commits. Test-only storage and SQLite live under disposable worktrees or `tmp_path`.

## Reviewer checklist

1. Confirm each PR base/head matches the stack table and check only current-head Actions results; PR #728 must precede #729, then #730.
2. Review source scope, page/attempt/time budgets, allowlists, XLSX/CSV validation, report date provenance and redaction. Confirm that missing, duplicate, lagging or conflicting evidence remains distinct from confirmed zero.
3. Inspect SQLite v12→v13→v14 migrations, append-only triggers, transaction boundaries, rollback, CAS, idempotency, two-client race and backup/restore.
4. Independently recalculate N04, N14, N17, N21, N24, N25, N27 and N29; inspect the other N01–N40 mappings.
5. Follow the successful `commit_transition_case` path from production Telegram callback through readiness, bridge, replay, impact, repository transaction and current/period consumers. Verify stale callbacks and evidence cannot apply.
6. Verify saved plans are frozen, current economics switch only after `APPLIED`, periods use physical dates only for FIFO order and financial dates for existing recognition, and TaxService remains authoritative.
7. Keep owner acceptance separate from code/CI status. No actual 05.11 case has been committed or validated against the missing source reports.


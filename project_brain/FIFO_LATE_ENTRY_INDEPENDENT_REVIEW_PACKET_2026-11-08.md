# FIFO late-entry completion — independent review packet

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
| [#731](https://github.com/dopf129-pixel/ai-business-assistant/pull/731) | FR02–FR11: temporal replay and multi-rate readers | PR #730 head `8e6b528c462c322b78b0c5e1d82fb782f4bbeab4` | Pending FR11 CI correction commit | Initial Linux run 42789021904 found one FR11 open-rate fallback regression and three FR24 production tests staged ahead of their implementation; correction submitted, exact-head rerun pending. |
| [#732](https://github.com/dopf129-pixel/ai-business-assistant/pull/732) | FR12–FR31: durable bridge, review/apply, production integration, owner cutoff evidence | PR #731 | `b7724261ac0b87dbfeddf5ac18c77753e0f03477` | Linux full verification passed in run 42789118312; Windows verification was running at packet update. |

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


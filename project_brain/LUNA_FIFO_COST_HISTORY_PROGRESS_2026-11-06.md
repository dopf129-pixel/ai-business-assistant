# FIFO cost history implementation progress

Specification: `project_brain/LUNA_FIFO_COST_HISTORY_TASK_2026-11-06.md` (PR #725).
Implementation branch: `codex/fifo-cost-implementation-20261106`.
Final integration target: `main`; this branch includes the exact specification head `b842e4a812334938e5178de8f4ae158d2b36735c` based on `main` `68aa6db09649bdbb4be406d423c6315a8961697b`.
Live Ozon/Telegram requests, bot startup, deployment, and merge are out of scope.

## Resume

- Current phase: FC06 additive tenant-local FIFO schema and isolation.
- Last completed phase: FC05 unified effective-date resolver and legacy compatibility correction.
- Last completed implementation SHA: `4decf16fbd941ab3e418ad8e9c94a66ff6584c87`.
- FC04 result: added `FifoCostAllocationService`, a pure Decimal replay core with explicit anchor/cutoff/order/completeness gates; finite old layers, rate-only unknown purchase quantity, split sales, exact restock basis, and bounded iterable inputs. It has no database, Ozon, Telegram, or Planning Workspace dependencies.
- FC05 result: single and batch writers project only the latest switch effective today; future switches do not overwrite current legacy evidence, late older switches do not roll it back, and current readers resolve the date dynamically. The card and price-scenario cache keys are date-scoped; ambiguous legacy rows shadowed by a future projection fail closed.
- Next action: proceed to FC07 atomic preview/commit APIs. The existing backup stores the SQLite database as one file, so all additive FIFO tables are within the existing backup boundary; FC31 will verify round-trip restoration with FIFO rows.
- Last full test result: Windows Python 3.12.10 / pytest 8.4.2, `python -m pytest`: **4,442 passed in 45.02s** at the spec head. This is baseline evidence, not FIFO implementation verification.
- Baseline data snapshot: 59 files / 283,840 bytes across `data/`, `.runtime-data/`, and root `ozon_assistant.db`; exact per-file SHA-256 manifest is retained locally under `%TEMP%\fifo-cost-fc00-baseline-20261106\manifest.json` (not committed). Before/after checks matched after restoring only the test-mutated `data/tasks.json` and removing a newly created lock and CPC diagnostic CSV. No user data was intentionally changed.
- The repository was clean before and after baseline restoration. Do not reset/clean unrelated paths.

## Stage status

| Stage | Status | Evidence / remaining work |
|---|---|---|
| FC00 | DONE | Branch/base verified; required docs read; 4,442-test baseline passed; local data hashes restored and matched. |
| FC01 | DONE | Source map and three confirmed temporal projection defects are recorded in `project_brain/FIFO_COST_SOURCE_AUDIT_2026-11-06.md`; isolated SQLite reproductions are captured. |
| FC02 | DONE_WITH_GAP | Official source matrix and synthetic delayed-accrual counterexample added. FBO present/reserved semantics, disjoint transit, physical exit time, and stock/finance watermark remain unproven; factual Period Profit FIFO must fail closed until owner validation establishes them. |
| FC03 | DONE | `FIFO_COST_CONTRACTS_2026-11-06.md`, Decision 066 and architecture map specify tenant SQLite ownership, immutable revisions, compatibility, bounded inputs and mandatory cutoff gate. Structure/cross-link and `git diff --check` passed; no code changed. |
| FC04 | DONE | Pure Decimal kernel in `app/services/fifo_cost_allocation_service.py`; `tests/test_fifo_cost_allocation_service.py`: 27 passing tests covering N01/N02/N03/N08/N21, fail-closed defaults, money/quantity invariants, bounded collections and a 250,000-line replay work cap; compileall and diff checks pass. |
| FC05 | DONE | `PeriodProfitEffectiveCostService` resolves `get_cost`/`get_all_costs` at the current effective date, syncs `product_costs` only from an active switch, preserves legacy provenance or returns `PERIOD_PROFIT_COST_LEGACY_PROVENANCE_AMBIGUOUS`; current-card and price-scenario cache scope changes at date boundary. Linked profile: 93 passed. |
| FC06 | DONE | `FifoCostRepository` adds 11 FIFO-owned tables, indexes, append-only triggers and independent `fifo_cost_schema` metadata in the existing tenant-local DB. Five temporary-database tests cover legacy/planning preservation, unchanged SQLite `user_version`, idempotence, append-only behavior, duplicate physical-sale identity, mid-migration rollback, future-version rejection and owner/store isolation. |
| FC07 | NOT_STARTED | Atomic preview/commit, CAS, idempotency. |
| FC08 | NOT_STARTED | Allowlisted stock/supply snapshot normalization. |
| FC09 | NOT_STARTED | Bounded source collection and diagnostics. |
| FC10 | NOT_STARTED | Explicit initial FIFO anchor/cutover. |
| FC11 | NOT_STARTED | Timely new-cost workflow. |
| FC12 | NOT_STARTED | Cost history/current FIFO UI. |
| FC13 | NOT_STARTED | Supply linking and partial acceptance. |
| FC14 | NOT_STARTED | Multiple transitions and layer reconciliation. |
| FC15 | NOT_STARTED | Stable physical-sale identity. |
| FC16 | NOT_STARTED | Replay and immutable allocation revisions. |
| FC17 | NOT_STARTED | Period Profit COGS integration. |
| FC18 | NOT_STARTED | Return allocation recovery preserving accounting gates. |
| FC19 | NOT_STARTED | Losses, waste, and other non-sale movements. |
| FC20 | NOT_STARTED | Public late-entry workflow. |
| FC21 | NOT_STARTED | Reconstruct missed cost transitions. |
| FC22 | NOT_STARTED | Correction impact preview and atomic commit. |
| FC23 | NOT_STARTED | Multiple late events and equal-date boundaries. |
| FC24 | NOT_STARTED | Current economics cost adapter/cache invalidation. |
| FC25 | NOT_STARTED | Single-price, grid, target, and sensitivity integration. |
| FC26 | NOT_STARTED | Quantity/sales-mix FIFO allocations. |
| FC27 | NOT_STARTED | Frozen plans, observations, and experiments. |
| FC28 | NOT_STARTED | Period FIFO explanation and export. |
| FC29 | NOT_STARTED | Legacy-compatible optional history import/export. |
| FC30 | NOT_STARTED | Concurrency, parent request budgets, cancellation, stale drafts. |
| FC31 | NOT_STARTED | Existing backup/restore and atomic migration coverage. |
| FC32 | NOT_STARTED | Independent N01–N24 numerical/stateful acceptance matrix. |
| FC33 | NOT_STARTED | User docs and separate live-owner acceptance instructions. |
| FC34 | NOT_STARTED | Full pytest, compileall, diff checks, exact-head CI. |
| FC35 | NOT_STARTED | Independent review handoff and ready PR; no merge/deploy/live bot. |

## Confirmed decisions

- Follow the business rules and limits in spec sections 2–7; do not turn the simplified FIFO into physical batch traceability or a home warehouse system.
- Preserve legacy effective-dated mode until an explicit owner-confirmed FIFO cutover.
- Preserve Ozon read-only behavior, finance authority, TaxService, Return COGS authorization gates, tenant isolation, saved-plan snapshots, and all local data.
- No additional business decision is currently required. Source uncertainty must be represented as incomplete or blocked evidence, not guessed.
- Decision 066 chooses a dedicated `FifoCostRepository` in the existing tenant DB, FIFO-owned migration metadata separate from Planning Workspace's `planning_schema`, append-only events/allocations, explicit per-SKU cutover, and no legacy fallback after activation when FIFO evidence is incomplete. Independent architecture review is required before merge.

## Source gaps

- FC01 confirmed the reader/writer paths and their semantic limitations. FC02 confirmed current official endpoint/version direction and documents exact gaps: current v4 stock response semantics/as-of watermark need owner validation; `/v1/analytics/stocks` has transit-status fields but overlap is unproven; crossdock `arrival_date` is officially null; the current sale evidence retains finance recognition date, not physical exit time; no shared inventory/finance watermark exists in the current adapter.
- This source gap is an implementation gate, not permission to substitute an assumption. `INVENTORY_CUTOFF_UNRECONCILED` must keep factual Period Profit COGS unavailable. A model view must be separately labeled and cannot be persisted as factual results.

## Check history

| SHA | Command/profile | Result | Data integrity |
|---|---|---|---|
| `b842e4a812334938e5178de8f4ae158d2b36735c` | Windows Python 3.12.10, pytest 8.4.2, `python -m pytest` | 4,442 passed, 0 failed, 45.02s | All 59 pre-test files matched exact SHA-256 snapshot after restoration of test-created changes. |
| `b971eedc475f6c6ed5e53ac78c250e56521885f3` | Isolated Python harness: three temporary SQLite scenarios for future single, late-old single, and future batch | All three confirmed the current-projection mismatch; no repository test file changed. | Temporary databases only; no live or owner data used. |
| FC02 source audit | Official Ozon notices + local source adapters + JSON parse/structure check for synthetic negative fixture | Completed with explicit source gaps; no unsupported FBO/current v4 semantics or sale cutoff claimed. | Synthetic fixture only; runtime code and owner data unchanged; no live calls. |
| FC03 contract/ADR check | Python required-heading and cross-link check; `git diff --check` | PASS; Decision 066 and the cutoff blocker are explicit. No implementation tests were applicable because this stage changed only architecture documents. | Documentation only; local data and runtime behavior unchanged. |
| FC04 core verification | Windows focused `python -m pytest -q tests/test_fifo_cost_allocation_service.py`; `python -m compileall -q app/services/fifo_cost_allocation_service.py tests/test_fifo_cost_allocation_service.py`; `git diff --check` | 27 passed; compilation and whitespace checks PASS. Synthetic-only pure core; no Ozon/Telegram/DB calls. | No owner data used; bounded-generator tests exercise the limit without persistent files. |
| FC05 effective-date verification | Windows linked pytest profile: current projection regressions, legacy timestamp/timeline, identity fallback, confirmation runtime, Telegram single-entry, CSV import, current unit-economics cache and price-scenario cache | 93 passed; future single, future-only, late-past, batch, date-boundary, old-projection ambiguity, historical switch lookup, single/CSV paths and both no-restart cache boundaries covered. | Each SQLite regression uses a fresh temporary DB; synthetic cache/source doubles only; no live request or owner data. |
| FC06 schema verification | Windows project Python: `python -m pytest -q tests/test_fifo_cost_repository.py tests/test_fifo_cost_allocation_service.py`; `python -m compileall -q app/services/fifo_cost_repository.py tests/test_fifo_cost_repository.py`; `git diff --check` | 32 passed; schema compatibility, repeated init, append-only source evidence, duplicate physical-sale identity, transactional rollback, future-version rejection, tenant/store isolation, and FIFO kernel regressions verified; compilation and diff checks PASS. | All DBs use pytest temporary directories; no live database or seller data used. Full compile/test/CI are deferred to FC34. |

## PR and CI

- Source specification: [PR #725](https://github.com/dopf129-pixel/ai-business-assistant/pull/725), open, exact head `b842e4a812334938e5178de8f4ae158d2b36735c`.
- Implementation PR: not created yet.
- Current implementation branch code baseline at FC04 start: `88e1b55ccf07f3f1b4dafd9f2ca43abc2fe9547d`; exact-head implementation CI is pending.
- Exact-head CI for implementation: pending; baseline spec PR CI is not implementation verification.


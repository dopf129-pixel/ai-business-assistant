# FIFO cost history implementation progress

Specification: `project_brain/LUNA_FIFO_COST_HISTORY_TASK_2026-11-06.md` (PR #725).
Implementation branch: `codex/fifo-cost-implementation-20261106`.
Final integration target: `main`; this branch includes the exact specification head `b842e4a812334938e5178de8f4ae158d2b36735c` based on `main` `68aa6db09649bdbb4be406d423c6315a8961697b`.
Live Ozon/Telegram requests, bot startup, deployment, and merge are out of scope.

## Resume

- Current phase: FC10 explicit initial FIFO anchor/cutover.
- Last completed phase: FC09 bounded source collection and diagnostics.
- Last completed implementation SHA: `a3ce84b0` (FC09); FC08 SHA is `0e4e3144`, FC07 SHA is `29eb3a6a`, and FC06 schema SHA is `5c0707b8`.
- FC04 result: added `FifoCostAllocationService`, a pure Decimal replay core with explicit anchor/cutoff/order/completeness gates; finite old layers, rate-only unknown purchase quantity, split sales, exact restock basis, and bounded iterable inputs. It has no database, Ozon, Telegram, or Planning Workspace dependencies.
- FC05 result: single and batch writers project only the latest switch effective today; future switches do not overwrite current legacy evidence, late older switches do not roll it back, and current readers resolve the date dynamically. The card and price-scenario cache keys are date-scoped; ambiguous legacy rows shadowed by a future projection fail closed.
- FC06 result: additive FIFO schema has independent `fifo_cost_schema`; FC07 upgrades it from version 1 to 2 with command/revision and event-order tables. Preview tickets are process-local, owner-scoped, latest-only, expire after ten minutes and become invalid after restart.
- FC07 result: one atomic command can append 1–100 normalized events; the boundary checks tenant/store/exact SKU identity, source fingerprint/ref stability, expected stream revision, supersession target, one-million-unit command cap, payload limits and idempotency. A same-key/same-payload retry returns the original command; key reuse with a changed payload, stale callback, source identity collision or CAS loser returns an allowlisted error without partial writes.
- FC08 result: pure `FifoCostSourceNormalizer` keeps invalid/partial/empty/confirmed-zero/conflict/unavailable distinct; normalizes exact product/SKU identity only with an explicit catalog-mapping confirmation, FBO `present` and `reserved`, validates pagination, and reconciles act SKU lines against (not in addition to) act summary totals. `present` is the FBO layer count; `reserved` remains a subset and available-for-sale is separate. Supply/act identifiers are emitted only as SHA-256 references; capture/state/act dates are not physical receipt/sale time. Current snapshots remain blocked by `INVENTORY_CUTOFF_UNRECONCILED`.
- FC09 result: `FifoCostSourceCollectionService` connects read-only stock and completed-supply/act reads to the normalizer. Existing parent deadline and shared HTTP-attempt budget survive child requests; retries are fixed at one attempt per call, every actual attempt is observed, and duplicate concurrent reads are single-flight. Supply pagination is limited to two pages/action, 100 total pages and 10,000 rows; a ten-minute, one-use, process-local continuation carries a fingerprinted checkpoint and never publishes a truncated search as complete. Linked synthetic Windows profile: **117 passed**; compileall and `git diff --check` PASS. No live Ozon/Telegram calls or bot startup. Cutoff gate remains blocked.
- Next action: FC10 adds an explicit owner-confirmed starting point and per-SKU cutover without converting the unproven physical stock/finance bridge into factual Period Profit COGS. The existing backup stores the SQLite database as one file; FC31 will verify restore with FIFO rows.
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
| FC07 | DONE | Schema v2 adds immutable command/revision and event-order tables with an atomic v1→v2 upgrade. Read-only preview and one-time latest-owner ticket feed a transaction with stream CAS, source-reference immutability, hash-bound idempotency, append-only events/layers, bounded batches, correction target validation and no partial write. 17 repository tests plus the 27-test allocation profile pass. |
| FC08 | DONE | API-independent normalizer validates `total_items`/page coverage, catalog-confirmed exact product/SKU mapping, FBO integer quantities, duplicate product/act representations and supply line/summary reconciliation. It separates `present` from reserved availability, never adds unknown/overlapping transit, omits server-as-of/physical event time, and always blocks anchor eligibility while the shared cutoff remains unproven. Synthetic profile: 25 passed; compile and diff checks PASS. |
| FC09 | DONE | Read-only `FifoCostSourceCollectionService` shares parent trace/deadline/HTTP budget, counts transport attempts, forces one client retry, supports cancellation/single-flight and bounded two-page resumable supply search with finite pages/rows, opaque single-use scope-bound checkpoint and fingerprint. Linked profile: 117 passed; compileall and diff check PASS. Current stock/supply evidence still cannot activate an anchor. |
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
| FC07 atomic command verification | Windows project Python: `python -m pytest -q tests/test_fifo_cost_repository.py tests/test_fifo_cost_allocation_service.py`; `python -m compileall -q app/services/fifo_cost_repository.py tests/test_fifo_cost_repository.py`; `git diff --check` | 44 passed; v1→v2 migration, no-write preview, same-key idempotent retry, key/payload mismatch, old SKU/store callback rejection, source-reference fingerprint immutability, atomic rollback after an invalid later event, two concurrent CAS contenders, strict amount/time/reference validation and TTL expiry verified; compile and diff checks PASS. | All SQLite databases are pytest temporary files; no live seller/API data or bot was used. Full suite and exact-head CI remain FC34. |
| FC08 source normalization | Windows project Python: `python -m pytest -q tests/test_fifo_cost_source_normalizer.py`; `python -m compileall -q app/services/fifo_cost_source_normalizer.py tests/test_fifo_cost_source_normalizer.py`; `git diff --check` | 25 passed; synthetic N04 reserve/transit arithmetic, incomplete/empty/confirmed-zero distinctions, `total_items`/page mismatch, strict quantities, duplicate stock/act dedupe, multiple accepted acts for one SKU, aggregate-vs-line reconciliation, ambiguous multi-SKU supply and unconfirmed act state verified; compile and diff checks PASS. | Pure in-memory fixtures only; no API, live bot, persistent database, or owner data used. Physical cutoff remains blocked by `INVENTORY_CUTOFF_UNRECONCILED`. |
| FC08 linked regression profile | Windows project Python: `python -m pytest -q tests/test_fifo_cost_source_normalizer.py tests/test_fifo_cost_allocation_service.py tests/test_fifo_cost_repository.py` | 69 passed in 1.25s, including the prior allocation and repository profiles. | New source normalizer uses synthetic memory fixtures; repository regressions use temporary SQLite only. No live requests or owner database. |
| FC09 bounded collection profile | Windows project Python: `python -m pytest -q tests/test_fifo_cost_client_contract.py tests/test_fifo_cost_source_collection_service.py tests/test_fifo_cost_source_normalizer.py tests/test_fifo_cost_allocation_service.py tests/test_fifo_cost_repository.py tests/test_cross_docking_supply_source.py tests/test_experimental_supply_act_diagnostic.py`; compileall for changed source/tests; `git diff --check` | **117 passed in 2.28s**; confirms bounded API options, 19 FC09-specific cases, parent deadline/request budget, measured attempts, cancellation, timeout, rate limit, repeated cursor/checkpoint, finite resume, redacted response, and existing supply/act compatibility. Compile and diff checks PASS. | All responses synthetic; DB tests use temporary SQLite. No real Ozon/Telegram calls, bot startup, or owner data. FC09 implementation commit `a3ce84b0`. |

## PR and CI

- Source specification: [PR #725](https://github.com/dopf129-pixel/ai-business-assistant/pull/725), open, exact head `b842e4a812334938e5178de8f4ae158d2b36735c`.
- Implementation PR: not created yet; FC00–FC09 implementation commits are local on the implementation branch.
- Current implementation branch code baseline at FC04 start: `88e1b55ccf07f3f1b4dafd9f2ca43abc2fe9547d`; exact-head implementation CI is pending.
- Exact-head CI for implementation: pending; baseline spec PR CI is not implementation verification.

## Resume after FC09

- FC09 exposes explicit read-only collector methods but does not activate FIFO, write observations, or wire a user-facing button; FC12/FC13 own owner-facing workflows. Never trigger a collection except from an explicit caller.
- Parent operation trace must be passed through. Keep `max_attempts=1` for each client call so the trace and transport observer report every actual HTTP attempt; never exceed 60 seconds/64 attempts per owner collection or diagnostic limits of 10 attempts/2 pages.
- Supply search may conclude `NOT_FOUND` only after terminal pagination; partial/error/rate-limited reads stay partial or unavailable and cannot be interpreted as zero. Continuations are process-local and single use; a restart safely invalidates them.
- Never convert local `captured_at`, `state_updated_date`, act `created_date`, supply slot or crossdock `arrival_date` into physical receipt/sale time. `source_as_of` remains null without a trusted validated source field.
- Never interpret missing product rows as confirmed zero. `EMPTY` is distinct from `CONFIRMED_ZERO`; `present` includes reserved units and `available_units` is only a separate convenience value.
- Continue with FC10 and preserve the global cutoff gate. No new business decision is required; unresolved source semantics remain typed blockers.


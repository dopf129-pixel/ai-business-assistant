# 2026-11-14 — FIFO automatic batch rule implementation in progress

- Implementation PR A is being developed from spec PR #733 on `codex/fifo-auto-batch-foundation-20261113`, based on its open specification branch. FB00–FB09 implementation is complete: source boundaries and typed contracts are recorded; additive SQLite v17 stores scoped rule/observation/decision/control evidence and CAS scan checkpoints; owner rule preview and confirmation use exact case/rule-head CAS and durable idempotency; a pure classifier applies proven dispatch dates to rule intervals and preserves owner membership across ordinary status/quantity refreshes while the stable binding remains unchanged; optional owner quantity controls are immutable, dated and typed; the production Telegram wizard offers automatic supply mode or a separate dated owner control and resumes old drafts without resetting their inputs. Readiness distinguishes unavailable/partial/current automatic manifests from the unchanged legacy owner-total path. Legacy cases remain in `LEGACY_OWNER_TOTAL` until an owner confirms the automatic rule.
- Rule confirmation changes only the case supply-total mode and appends owner rule evidence. It never writes FIFO rates, layers, events, allocations, or COGS. Successor confirmation atomically closes the prior local-date interval and appends the next rule. Preview tickets are bounded, process-local, and expire in 15 minutes; persisted receipts support retry after restart.
- This remains an incomplete, non-deployable feature. FB11 adds only a one-page, allowlisted, read-only supply-list skeleton with a shared 20s/10-attempt trace; it always reports PARTIAL until raw states/cursor coverage are verified and does not persist data or connect to UI. Details, bundle composition, normalization, durable checkpoint/manifest publication, production wiring and prepare/apply sealing remain outstanding. FB01's unknown-total wizard regression now passes; mixed/unknown first-day membership remains unresolved until source selection is available. FB06–FB09 do not create FIFO rates, layers, events, allocations, or COGS. Dated owner controls are not yet compared to manifests; that remains FB17. An exact current manifest can clear only the supply-list gate; R1/cutoff and physical receipt timing remain separate.
- The official-source contract marks raw bundle schema, complete state enum, and dispatch-date proof as unverified. Synthetic adapter fixtures are not raw Ozon payloads.
- FB10 local isolated Windows/Python 3.12 verification passed **5,346 tests in 95.82s** plus `compileall` on tested tree `74ffefcd`, using no project `data/` or secrets and a synthetic tax policy. Verify run [#43595401017](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/43595401017) passed Windows/Linux full suites, compile, Linux production Docker build/runtime smoke and SHA-bound report generation for PR head `0803bd0dbb0285e30b3296c7d2e7a22dda028ecb`.
- R1 inventory movement coverage remains a separate hard gate. No live API, owner data, Desktop bot, merge, or deployment has been used.

# 2026-11-13 — Next FIFO work: automatic batch membership (specification only)

- Product baseline: main 7965dcdd. Added LUNA_FIFO_AUTO_BATCH_RULE_TASK_2026-11-13.md and an unstarted progress journal for FB00–FB31.
- Owner request: subsequent shipments of the same SKU belong to the new batch until the next confirmed cost boundary; remove the continuously maintained mandatory manual total.
- The specification separates owner rule confirmation, source supply coverage and factual FIFO readiness. Automatic grouping requires proven dispatch timing or an exact grouped owner selection.
- At specification creation, implementation stages were NOT_STARTED. R1 remains open. No owner data, live API or running bot was changed by that specification-only change.

# 2026-11-13 — FIFO review fixes R18–R20

- Physical-sales owner confirmation keys now bind the exact saved case revision, so a deliberate re-selection of an identical document is a new confirmation operation; document evidence itself remains append-only and reused.
- Financial-period evidence bundles retain validated snapshot history and evidence revisions. Preview, confirm, and monthly collection choose the newest snapshot whose reconstruction and tax-policy fingerprints match current inputs. Stale months from corrected reconstructions are excluded, while a prior matching snapshot remains available when settings are restored.
- Local changed-service profile: **81 passed**. Verify run [#43414761340](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/43414761340) passed on code SHA `7b1c9aeb02dfae3958ba2134c914b0183611903a` (Windows/Linux full suites, compile, Linux production Docker build/runtime smoke, SHA-bound report). Tracked `data/` is unchanged. The separate owner-case movement-source blocker remains open; no real API request, bot launch, merge, or deployment was performed.

# 2026-11-13 — FIFO review fixes R15–R17

- The same physical-sales CSV can now be uploaded again after a preview expires or the process restarts: the service verifies and reuses the exact encrypted evidence instead of making a timestamp-only append or returning an idempotency conflict.
- When reconstruction, tax policy, or the sale-identity set changes, stale monthly snapshots stay immutable in history and are excluded from the new collection. The collector re-reads and appends a current snapshot; evidence loading selects the highest valid evidence revision per financial month.
- A transient failure while reading older confirmed CSV versions no longer leaves the Telegram session at an obsolete case revision. The retry action refreshes the session and can continue the explicit owner selection flow.
- Verification: linked FIFO workflow profile **102 passed**; `git diff --check` and tracked `data/` equality pass. Verify run [#43408293179](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/43408293179) passed on implementation SHA `6e629c9fe06d1063c999019e8d3ca81fe0d03b71` (Linux/Windows full suites, compile, Linux Docker build/runtime smoke, SHA-bound report). `.fl12-deps/` remains untouched and untracked.

# 2026-11-13 — FIFO review corrections R12–R14

- Monthly snapshot source fingerprints are independent of request chunking; they bind each daily finance-cache value by date together with monthly Period Profit totals. Pre-v2 freezes are accepted only when their legacy chunk-bound digest is reproduced exactly.
- Owner-imported physical-sales evidence keeps every confirmed CSV immutable. Replacing the active version requires an explicit confirmation that binds the full prior fingerprint set; old multi-version evidence without an owner selection fails closed.
- CSV coverage is entered as a full date interval before upload, so periods with no sale rows at the first/last day remain represented. The preview distinguishes declared coverage from dates actually present in rows.
- Verification: linked FIFO profile **116 passed**; full isolated pytest **5,288 passed in 73.96s**; compileall, diff check, and unchanged tracked `data/` passed. The disposable suite excluded owner data and used a synthetic tax policy. Implementation SHA `89a8efd68674c28a9fd7f4584a6f180b69c7f8fe` passed exact-head Verify run [#43399966702](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/43399966702) on Windows/Linux and Docker smoke. R1 remains a hard blocker; no owner case, real API, Telegram bot, merge or deployment was verified/performed.

# 2026-11-13 — FIFO review corrections R9–R11

- Impact calculation refuses to turn a monthly SKU aggregate mismatch into an invented “unaffected same-SKU cost”; it returns candidate-only until COGS for the exact affected identities is proven. The complete finance export is bound to a typed ready cutoff bridge and only exact post-cutoff identities enter monthly snapshots. The expired-preview audit marker is excluded from source-evidence fingerprinting, so a fresh prepare can reuse unchanged frozen evidence.
- Regressions cover unsafe COGS attribution, exact pre/post cutoff partition and rejection of an incomplete bridge mapping, plus repository-backed prepare/expire/reopen/prepare using the same saved summary.
- Verification: targeted profile **59 passed**; full isolated pytest **5,287 passed in 92.32s**; `compileall`, `git diff --check`, and tracked `data/` equality passed. The full-suite copy excluded owner data and used a synthetic tax policy. Hosted status is tracked on PR #732. R1 remains a hard source blocker; no owner case, live API, bot launch, merge or deployment is claimed.

# 2026-11-11 — FIFO follow-up review R6–R8 fixed locally

- Initial FIFO composition accepts a confirmed finite count of new-party units at home and creates the matching new-cost home layer. New-party transit quantity is retained separately in encrypted composition metadata, shown to the owner, and never counted as FIFO transit or stock before accepted receipt.
- A frozen Period Profit snapshot keeps full-month SKU COGS even if the FIFO reconstruction covers only some sale identities. Impact replaces only those reconstructed sales and preserves the remainder of the store COGS.
- An expired current READY seal can return to evidence review only through exact preview ID/fingerprint + revision CAS; this appends a revision and performs no FIFO write. Runtime then rechecks current evidence and creates a fresh preview. Applying remains a separate confirmation.
- Verification: **107 linked tests**, **38 cutoff/report-worker tests**, **5,285 full isolated tests**; compileall, `git diff --check`, and `git diff --exit-code -- data` passed. Full-suite copy excluded owner data and used a synthetic tax policy. Exact-head Verify run **43009830700** passed for code SHA `2ed94ed124cf4d09b604cad9d9e1200f22908ff9` on Windows/Linux and Docker build/runtime smoke, with a SHA-bound report. This follow-up records that result; no code changed after the verified code SHA.
- Full movement coverage remains blocked under R1. No owner case, live Ozon/Telegram calls, bot launch, merge, or deployment was verified or performed.

# 2026-11-11 — FIFO review regressions R2–R5 fixed locally

- Bound opening-composition save tickets to the exact draft fingerprint and clear all draft/preview state on cancellation. The new-party home count can remain explicitly unknown; it is not converted into confirmed stock and is retained as `UNKNOWN_OPEN_RATE` through encrypted evidence and owner confirmation. Optional evidence/confirmation fields preserve compatibility with earlier records.
- Period Profit collection now receives already-persisted month snapshots, re-reads and fingerprint-checks them after a collector restart, and advances the case revision only for a new month. Return allocations use one canonical sale-line key so legacy layer references cannot bypass a line's remaining return quantity.
- Linked FIFO tests: **730 passed in 43.69s**. Full isolated pytest: **5,279 passed in 81.93s**. `compileall`, `git diff --check`, and tracked `data/` equality passed. The disposable test copy excluded live data and credentials.
- R1 remains a hard blocker: no supported complete inventory-movement ledger is available. Owner-case readiness, current-SHA hosted CI, merge, deployment, live APIs and bot startup remain unverified. Changes are local and uncommitted.

# 2026-11-10 — FIFO review corrections in progress

- Fixed the reviewed FIFO return-basis and monthly-collection regressions, and added Telegram actions that expose initial opening composition, bounded finance identities, and canonical Period Profit monthly snapshots through the production workflow. Catalog refresh and daily finance collection share one 20-second/10-request root trace.
- Added regressions for omitted-old-layer labeling, no-write behavior on unavailable finance sources, Telegram action routing, production dependency wiring, and exact shared-budget accounting. The linked FIFO review profile passes **99 tests**; focused apply/production/runtime profile passes **28 tests**; full isolated pytest passes **5,275 tests**. `compileall`, `git diff --check`, and tracked `data/` equality pass.
- R1 is only partially closed: no supported complete movement-ledger source was found. Full movement coverage remains a hard blocker and is not inferred from the Returns API. Owner case and hosted current-SHA CI remain unverified; no merge or deployment was performed.

# 2026-11-10 — FIFO dependent PR delivery

- PR #731 delivers FR02–FR11 on PR #730. It fixes the single-open-rate reader edge; the isolated full suite passed **5,170 tests**. Verify run `42790983173` on head `af7d93324eea9952d60fc26553d8ed673bd8834f` passed Windows/Linux and production Docker build/runtime smoke.
- PR #732 delivers FR12–FR31 atop #731. Merge commit `0ae37298b832775c1f6431a97924420b311ec358` passed exact-head Verify run `42793814822` on Windows/Linux full suites and Docker build/runtime smoke. This status-sync is documentation-only; its exact-head Verify is linked from PR #732 Checks.
- The historical cutoff count for the owner's case remains unentered. Manual owner input is explicit, separately labelled, and never merged into accepted FIFO opening stock. No real case is claimed verified.

# 2026-11-10 — FIFO owner-confirmed cutoff receiving quantity

- The user approved a manual owner confirmation for `supplier_receiving` when the saved cutoff stock report does not expose that bucket. The Telegram flow selects an exact one-day report, accepts an explicit whole-number quantity (including explicit zero), previews the report/SKU/cutoff binding, and stores the confirmation append-only. It is labelled owner input, not Ozon fact.
- The cutoff bridge includes the owner-confirmed quantity as a separate bucket. Initial cutover rechecks the durable cutoff confirmation and confirmed opening composition; the receiving quantity cannot be folded into accepted opening FIFO layers. A missing reserved count can be resolved only through that matching opening composition.
- Focused workflow/service/bridge/atomic/runtime verification: **77 passed**; targeted positive/negative FR27 flow plus atomic apply: **21 passed**. Isolated full pytest: **5,264 passed in 89.34s**. `compileall`, `git diff --check`, tracked-data diff and the five-file FR00 SHA-256 manifest pass. Hosted current-SHA CI is still pending until the changes are published. No live API/bot, owner database, merge or deployment was used. The owner's actual historical cutoff count remains unconfirmed.

# 2026-11-10 — FIFO FR27/FR30 integration checkpoint

- The production workflow now has a regression showing that an imported Ozon stock-management report does not prove `supplier_receiving`: the bridge stays `SOURCE_BLOCKED` and does not issue a READY/apply state. The report importer now projects source sub-buckets into canonical `defective` and `seller_withdrawal` totals; missing receiving stays `None`, never zero.
- FR27 positive prepare/apply/restart E2E remains blocked by the fixed cutoff contract: stock XLSX omits a receiving bucket and current supply status/act observations do not provide a historical bucket at the confirmed cutoff. No historical receipt or cutoff was inferred.
- Fixed the production factory's missing `TaxService` import while retaining optional degraded factory construction. Updated stale late-entry/backup fixtures to provide exact full-month, reconstruction and tax-policy fingerprints.
- Linked FR27/FR28 correction profile: **67 passed**. Full pytest in an isolated disposable copy: **5,258 passed in 86.19s** with a synthetic tax configuration; `compileall`, `git diff --check`, five owner-data SHA-256 values and empty `git diff -- data` passed. No owner database, credentials, live API, bot launch, merge, or deployment was used.
- Current-head hosted CI remains unavailable because these changes are local and not committed/published. Owner case remains unverified; positive FR27 production apply and dependent FR28–FR31 closure are not claimed.

# 2026-11-10 — FIFO FR26 downstream consumer integration

- Commit `1c2e4480` carries the current FIFO stream/allocation/cutoff-mapping revisions and `complete_through` through current unit cost, history, Period Profit explanations, and exports. Mapping metadata is read only after validating the saved cutoff bridge against current physical-sale identities.
- Replayed finite residuals from closed rates now precede the current open rate. A missing persisted rate-balance row is accepted only for the first sole open rate (`sequence=1`) with no reconciliations; otherwise incomplete replay still hides current FIFO quantity/cost.
- Linked FR26 profile: **177 passed in 7.82s**, including MR18 outflow separation and saved-plan restart/copy/new-revision/export coverage; compile and preserved-data checks pass. Full suite and exact-head CI remain FR30; owner case is still unverified. No live Ozon/Telegram calls or bot launch.

# 2026-11-10 — FIFO FR25 exact preview confirmation

- Implementation commit `b86d54d0` (`Bind FIFO confirmation to exact preview`). «Проверить готовность» only reads; «Посмотреть пересчёт» now calls prepare and either shows the exact persisted READY seal or candidate/missing requirements. READY after restart reloads the saved seal; the final opaque ticket binds preview ID/fingerprint, case revision and stable idempotency key. Apply revalidates this exact binding. Expired seals remain inspectable but cannot be applied. APPLIED receipt restores commit ID and complete-through after restart.
- Linked production workflow/apply/evidence/review/Telegram/runtime/atomic-apply profile: **48 passed in 8.60s**; compile, diff check, and FR00 data manifest pass. Full pytest/current-head CI remain FR30. The real owner case remains source-blocked; no live calls, bot launch, merge or deployment.

# 2026-11-10 — FIFO FR24 shared production workflow

- Added `create_fifo_cost_transition_workflow` and switched `create_telegram_assistant` to use it. Production assembly shares one repository/history/transition, durable evidence, review, apply, impact and runtime graph; it also carries source, tax, Period Profit and report/document dependencies. The runner exposes the workflow, runtime and apply service. The compatibility transition-service factory remains unchanged.
- Implementation commit `3927f270` (`Wire shared FIFO transition production workflow`). Cache invalidation is attached to ApplyService with committed identity/revision metadata; Telegram runtime no longer performs a second broad invalidation. FR24 linked verification: **17 passed in 4.09s**; factory compile and FR00 user-data manifest pass. FR25 exact preview ticket/confirmation UI is next. Owner case remains source-blocked; full pytest/current-head CI remain FR30. No live calls, bot launch, merge or deployment.

# 2026-11-10 — FIFO FR23 apply and restart recovery

- FR23 now reads the exact persisted READY seal without recalculation and applies only that preview ID/fingerprint at its expected case revision. It revalidates the sealed basis and current evidence/tax before the atomic repository write. An exact retry after APPLIED/restart returns the same durable commit; same-key concurrent requests recover the winner's result. Cache invalidation occurs after commit and cannot duplicate FIFO writes.
- Implementation commit `9f42f143` (`Apply exact FIFO transition preview safely`). Linked FR22–FR23 profile: **34 passed in 5.80s**; concurrent same-key regression passed five consecutive runs. Python compile and `git diff --check` passed; the FR00 five-file owner-data manifest is unchanged. FR24 production assembly is next; owner case remains unverified and source-blocked. Full suite/current-head CI remain FR30; no merge/deploy/live call/bot launch.

# 2026-11-10 — FIFO FR22 prepare and READY seal

- FR22 adds `FifoCostTransitionApplyService.prepare`: readiness is independently rebuilt from durable evidence; an exact complete impact is required before the repository seals READY at revision N+1. Candidate-only stays read-only and does not change FIFO history or Period Profit. Exact idempotent retry, expiry, changed tax/evidence, and existing-initialized-stream behavior are covered by targeted tests.
- Verification: 31 linked tests passed in 5.24s; one focused existing-stream review regression passed; changed modules compile; the FR00 five-file owner-data manifest matches. No live API or bot was used. Next: FR23 persisted preview read, apply, and restart safety.

# 2026-11-10 — FIFO review-blocker execution FR00–FR21

- FR21 canonical impact now accepts only complete calendar-month Period Profit snapshots bound to the exact public FIFO reconstruction and current normalized tax policy. Missing, stale or mismatched evidence stays candidate-only, with no profit/tax deltas. TaxService and Period Profit formulas are unchanged.
- Exact MR12–MR15 numeric regressions, dependent-month/other-SKU preservation, separate outflow handling, and a public reconstruction-to-impact integration path are covered. Linked synthetic checks and remaining limitations are in the progress journal; full suite/current-head CI remain FR30. Production assembly/action remain FR24–FR25. The owner's case is still unverified.

# 2026-11-10 — FIFO review-blocker execution FR00–FR20

- FR20 freezes whole-store financial amounts from the existing Period Profit chain per financial recognition month and binds them to exact reconstruction COGS, sale-identity digests, daily finance data, and the tax-policy fingerprint. Collection is resumable, capped at four days per call, 20 seconds and 10 shared HTTP attempts; a partial month is never persisted. Retry after a failed snapshot write resumes from before the final chunk, avoiding double counting.
- Finance identity snapshots now preserve each sale's financial month. Mismatched store/product scope, missing month, incomplete source, or missing historical before-cost blocks the freeze. Other-SKU cost and whole-store amounts remain unchanged. Collection does not run in prepare/confirm. Linked profile: **88 passed in 3.96s**; changed Python modules compile. FR24–FR25 remain responsible for production assembly and the explicit user action. No real owner case, live API, bot, or deployment was used. Next: FR21 canonical impact.

# 2026-11-09 — FIFO review-blocker execution FR00–FR19

- Executing [FR00–FR31 task](LUNA_FIFO_REVIEW_BLOCKERS_COMPLETION_TASK_2026-11-08.md), with Resume in [progress journal](LUNA_FIFO_REVIEW_BLOCKERS_COMPLETION_PROGRESS_2026-11-08.md). FR00–FR19 are complete. FR13 provides the strict owner-imported physical-sales CSV parser; FR14 stores and separately confirms its exact encrypted source; FR15 routes selected physical-sales CSV through Telegram; FR16 adds bounded finance identity and return-status snapshots without treating status changes as physical movement.
- FR17 adds durable cutoff and opening-composition owner confirmations. FR18 restores those confirmations with finance, physical-sales and movement evidence and rebuilds the actual cutoff bridge. FR19 adds public read-only baseline/candidate reconstruction through the same repository replay used by prepare; it returns exact identity, revisions, lineage, COGS and coverage while rolling back staged opening state, including on exceptions. FR19 linked profile: **372 passed in 25.57s**; `py_compile`, `git diff --check`, and `git diff --exit-code -- data` pass. Schema v16 and owner data are unchanged. Full suite/current-head CI remain for FR30. The owner's real case remains `SOURCE_BLOCKED`; no live API was used. Next: FR20 frozen financial-period baselines.

# 2026-11-08 — FIFO review corrections in progress

- Applied local corrections for report period confirmation, exact linked return bridge validation, restart-safe READY review, seller-confirmed historical finance SKU aliases, the first ordinary rate change after a verified late-entry replay, and deterministic repository clocks in the lifecycle regression. Schema v15 stores owner period confirmation separately and append-only from the source report. The FIFO-focused regression profile passes **110 tests**; isolated full Windows pytest passes **5,115 tests in 61.10s**; compileall and data-preservation checks pass.
- Independent review found two remaining implementation gaps: (1) production factory/runtime never builds and supplies the cutoff bridge or atomic apply service, so the user-facing path cannot reach READY/APPLIED; (2) deterministic replay still rejects more than one active rate, so successive ordinary rate changes after late entry are not supported. The current branch must not be merged until these are addressed or explicitly removed from the promised scope with review approval.
- The first isolated attempts exposed setup issues: a local worker dependency directory was absent from the disposable copy, then PowerShell was still in the source checkout and a test changed `data/tasks.json`. That file was restored from Git per the owner's earlier choice and `git diff --exit-code -- data` was rerun. The final full test ran with the temporary copy as its actual working directory and passed. No owner-provided business records, live Ozon/Telegram calls, bot process, merge, or deployment was used. Exact-head CI has not run on these local corrections; `IMPLEMENTATION_VERIFIED=false`, `OWNER_CASE_VERIFIED=false`.

# 2026-11-08 — FIFO FL34–FL35: local verification green, final packet CI pending

- Full isolated Windows pytest passed **5,104 tests in 75.99s** on implementation SHA `4771794e4372c5443ab65cee349d2e673508118e`; `compileall`, `git diff --check` and tracked `data/` diff passed. Remote Verify runs 42433357867 (PR #728), 42480102151 (PR #729), and 42480112108 (the earlier PR #730 head) passed Windows/Linux and production Docker smoke.
- At the time of that earlier check, PRs #728–#730 were marked ready; that status was superseded by the review correction entry above. PR #728 and #729 exact heads were green; PR #730 SHA `5178d50110a445e8313e7e4b2979cfc43dcfbe89` passed exact-head run 42480784925, which does not cover the current local corrections.
- No runtime behavior changed in the verification/review-packet/status commits. Owner validation/source evidence remain pending; no merge, deployment, live API call or bot launch occurred.

# 2026-11-08 — FIFO FL33: owner instructions separate knowns from missing evidence

- The owner guide now describes the actual late-entry review flow, `TOTAL_LANDED` for a single known full unit cost, exact SKU/case binding, report preview, supply refresh and read-only readiness/recalculation actions.
- The acceptance checklist records the 05.11 case: costs 21/14.65 ₽, 6,982 owner-declared units, old home/transit zero, new-home unknown and one 148-unit RECEIVING declaration. It separately identifies 1,191 from the inspected stock report and 1,192 from the owner's Google Sheet; neither is promoted to cutoff stock.
- Explicit missing evidence is listed: actual per-supply IDs/quantities and acceptance acts; post-05.11 turnover and complete dated stock buckets; exact physical-sale/return/non-sale bridge and confirmed cutoff. Decision 066 remains strict: `USER_VALIDATION_PENDING`, `SOURCE_BLOCKED`.

# 2026-11-08 — FIFO FL32: backup/restore preserves late-entry state

- A normal backup/restore round-trip now has regression coverage for separate `DRAFT`, `AWAITING_EVIDENCE`, and `APPLIED` cases, a tenant-encrypted supply lookup, the current v14 schema, and a saved planning snapshot.
- Restored case state and ciphertext remain readable. Supplying a wrong Fernet key fails to decrypt the token but does not delete the declaration or report “no supply”. Replaying the already committed confirmation returns the existing commit; all FIFO table counts remain unchanged.
- Existing migrations v12→v13 and v13→v14 pass. All stateful fixtures remain in `tmp_path`; `data/` is unchanged. `IMPLEMENTATION_VERIFIED=false`, `OWNER_CASE_VERIFIED=false`.

# 2026-11-08 — FIFO FL31: concurrent confirmation is regression-covered

- FL31 audit found that atomic apply already uses a transaction and revision check, but its positive-path tests only exercised sequential retries. Added a synchronized competing-confirm test with two repository instances and distinct idempotency keys.
- Exactly one request moves the case to `APPLIED`; the other receives `FIFO_TRANSITION_REVISION_CONFLICT`. The resulting database has one transition commit, one rate change, one allocation, two initial cost layers, two sale mappings, and only the expected three events (two opening layers plus one post-cutoff sale).
- Existing security/import/navigation tests cover the remaining FL31 matrix; no product code change or architectural decision was needed. FL31 implementation verification is synthetic only; `OWNER_CASE_VERIFIED=false`.

# 2026-11-08 — FIFO FL30: acceptance evidence survives refresh and restart

- `FifoCostTransitionSupplyRefreshService` now passes complete act evidence into the existing append-only transition observation. The case stores only allowlisted per-act digests and quantities; raw act/supply IDs remain transient and are not persisted in the transition payload.
- Code commit: `2dec7566` (`Persist FIFO transition acceptance act evidence`).
- Review reconstructs the source act snapshots and reruns cumulative acceptance reconciliation after a fresh repository/service instance. Explicit zero is confirmed only when a complete accepted act contains zero; no act evidence stays unknown. Acceptance remains documentary evidence and never writes an inventory movement or activates FIFO.
- Numeric crosswalk N01–N40: linked profile **1094 passed in 44.41s**; acceptance refresh/restart and linked reconciliation tests **39 passed in 2.04s**; compileall, diff-check, and tracked `data/` diff passed. Aggregate current `data/` manifest SHA-256: `4e540517654f0ab646dd704b8fb4f0cd7fdce93132b866ff961eae26414f8e07` (six files; content not printed). Synthetic only.
- This change extends the transition observation contract and public review assembly; classify as **Architecture Review Required**. `IMPLEMENTATION_VERIFIED=false`, `OWNER_CASE_VERIFIED=false`; FL31 remains next.

# 2026-11-08 — FIFO FL29: история переходов, отмена и refresh

- Код FL29: 0bcb13d8cfd4704429a08999e7a014a2c4275e8a; требуется независимый архитектурный review публичного history path и Telegram export integration.
- История transition cases читается постранично из append-only revisions в точной области owner/store/SKU. Telegram показывает все пять статусов, включая APPLIED и CANCELLED, и может снова открыть историю после перезапуска процесса.
- CSV истории FIFO объединяет allowlisted редакции переходов с прежними слоями/ставками, ограничен 10 000 строк и 1 МБ, не содержит case ID, raw/encrypted lookup references или evidence IDs. APPLIED нельзя исправить UPDATE; коррекция создаётся отдельным случаем, связанным через `supersedes_case_id`.
- Новое доказательство переводит READY в AWAITING_EVIDENCE и не меняет сохранённый preview. При отстающем времени источника `updated_at` дела не откатывается.
- FL29 focused tests: **69 passed in 6.40s**; linked FIFO/Telegram/Period Profit profile: **1086 passed in 44.07s**; compileall, diff-check, `data/` unchanged PASS. Synthetic-only. `IMPLEMENTATION_VERIFIED=false`, `OWNER_CASE_VERIFIED=false`; далее FL30 — вся числовая матрица.

# 2026-11-08 — FIFO FL28: factual Period Profit cutoff partition

- `FifoCostRepository` schema v14 persists append-only mapping revisions between exact finance sale identities and physical cutoff dates, in the existing tenant FIFO database. Transition apply stores the mapping atomically with its rate, allocation and case commit.
- Period Profit now joins pre-cutoff dated legacy cost and post-cutoff FIFO allocation by sale identity, not by financial period date. A touching-cutoff period fails closed without complete bridge coverage. Explanation and sanitized export retain the same stream/allocation/mapping revisions.
- FL28 focused checks **60 passed**; linked FIFO/Telegram/Period Profit **1085 passed in 44.01s**; compileall, diff-check and `data/` unchanged passed. Synthetic data only; `IMPLEMENTATION_VERIFIED=false`, `OWNER_CASE_VERIFIED=false`; PR CI pending.

# 2026-11-08 — FIFO FL27: current unit economics and plans

- Черновик/READY перехода не меняет текущую себестоимость: до атомарного применения продолжается legacy effective-dated значение. После `APPLIED` общий FIFO adapter получает новую точную history revision, а query cache текущей экономики сразу перестраивается по cost revision.
- Telegram snapshot расшифровки хранит точные store/product/offer/SKU, cost revision и allocation revision. После apply invalidator удаляет только устаревший snapshot этой identity; каждый callback дополнительно сверяет обе revision и закрывается при изменении или недоступном источнике. Новые owner/API запросы при этом не делаются.
- Сохранённые планы остаются историческими immutable revisions; свежий расчёт получает новый FIFO basis. `TOTAL_LANDED` остаётся одной суммой без созданной ботом разбивки компонентов.
- FL27 code `81266ad3`; focused **72 passed**, linked profile **617 passed in 27.93s**, compileall/diff-check/`data/` unchanged PASS. Только временные synthetic SQLite; `IMPLEMENTATION_VERIFIED=false`, `OWNER_CASE_VERIFIED=false`. Production apply orchestration и financial Period Profit integration продолжаются в FL28.

# 2026-11-08 — FIFO FL26: раздельные действия, readiness и preview

- Добавлен read-only reconstruction сохранённых declarations/observations/reports и readiness для точного owner/store/SKU дела. Preview различает owner-ввод, source as-of/period provenance, подтверждённые FIFO-слои, TOTAL_LANDED/COMPONENTS и не выдаёт разницу себестоимости за прибыль.
- Обновление поставок выбирается постранично и только после owner-повторного ввода точного ID, сверяемого с encrypted declaration до вызова источника. Callback-ы opaque и не содержат ID.
- Неподтверждённый preview не меняет FIFO, цену, прибыль, кэш или планы; apply UI закрыт без READY/service и отдельно проверяет server state/revision. Production apply orchestration не подключён и должен быть реализован downstream.
- FL26 code SHA `1e9ccb95d06974ebacf9b00186341dd399d40cfb`; целевые тесты **57 passed**, linked FIFO/Telegram/Period Profit **545 passed**; compileall/diff-check/data unchanged PASS. READY review остаётся read-only и не активирует apply. Synthetic-only. `IMPLEMENTATION_VERIFIED=false`, `OWNER_CASE_VERIFIED=false`.

# 2026-11-08 — FIFO FL24: переход к поздней партии до настройки очереди

- Карточка SKU без FIFO теперь показывает «Новая партия уже отправлена» и «Незавершённые изменения», сохраняя доступ к прежнему начальному срезу и нулевому старту. Поздний сценарий не блокируется отсутствием очереди.
- Список читает только активные cases точного store/SKU/offer/product scope и выдаёт временный owner-bound opaque resume callback. Незавершённый переход блокирует нулевой старт; при сбое чтения проверка закрывается безопасно. Ни FIFO, ни себестоимость отчётов/прибыль этим экраном не меняются.
- FL24 code SHA `ee98230286354e21e1f2cf5ca307391c97d6171f`; связанный FIFO/Telegram/Period Profit профиль **533 passed in 22.87s**; compileall, `git diff --check`, `git diff --exit-code -- data` PASS. Только временная synthetic SQLite; owner DB, live API и bot не использовались. Следом FL25 — durable resumable wizard.

# 2026-11-08 — FIFO FL23: атомарное применение позднего перехода

- Добавлен транзакционный `commit_transition_case`: повторная проверка case/FIFO/allocation revisions, bridge, tax/evidence fingerprints, sealed preview, replay и idempotency; ставка, полная allocation/projection, commit audit и `APPLIED` фиксируются одним `BEGIN IMMEDIATE`.
- Для FIFO без начальной очереди preview допускает только сохранённый initial cutoff с подтверждёнными остатками. Начальный срез остаётся read-only до подтверждения; себестоимость слоёв ограничена старой/новой ценой и FIFO-порядком. Базовое сравнение N21 проверяет 105,00 ₽ до и 92,30 ₽ после, конечный подтверждённый остаток — 98 новых единиц.
- Дословный повтор commit возвращает исходный результат после TTL и смены текущей налоговой политики; изменённый payload возвращает idempotency conflict. Сбой до/после каждого DML write откатывает все затронутые FIFO и transition таблицы.
- FL23 code SHA `462c413b17a55b58d1c7fc629cd6aad287ca2fab`; dedicated tests **10 passed**, linked FIFO/Telegram/Period Profit profile **531 passed**, `compileall -q app tests`, `git diff --check` и `git diff --exit-code -- data` PASS. Только synthetic temporary databases; реальный case и источники магазина не подтверждены. `IMPLEMENTATION_VERIFIED=false`, `OWNER_CASE_VERIFIED=false`. Далее FL24 — кнопки для поздней партии и незавершённых изменений до настройки FIFO.

# 2026-11-08 — FIFO FL22: финансовые периоды и влияние на прибыль

- Impact preview теперь отделяет физическую дату FIFO-порядка от финансового периода признания. Полное сопоставление sale identity digest ↔ период обязательно и входит в отпечаток preview/confirmation; периодный охват должен включать весь зависимый горизонт продаж.
- При недоступной исходной базе/сводке показывается только кандидатная себестоимость без дельт налога и прибыли. Полный путь продолжает считать налог через canonical `TaxService`; сервис остаётся read-only до FL23.
- FL22 code SHA `4290c961c60326e21d65559da18757466675a02f`; focused profile **37 passed**, linked FIFO/Telegram/Period Profit **521 passed**, compileall/diff-check/неизменность `data/` PASS. Только synthetic tests; `IMPLEMENTATION_VERIFIED=false`, `OWNER_CASE_VERIFIED=false`. Далее FL23 — атомарное применение.

# 2026-11-08 — FIFO FL21: связанные возвраты и выбытия

- Поздний replay учитывает только точные возвраты с подтверждённым saleable-restock lineage и прочие движения, прошедшие существующие append-only validators. Возврат восстанавливает сохранённые исходные слои; неизвестный источник блокирует replay.
- Несбытовые выбытия отдельны от продаж, их количества и COGS; Return COGS authorization не меняется. Продажи до новой ставки не могут получить новую стоимость; same-date transition проверяется фактическим replay и FL20-инвариантностью.
- FL21 code SHA `5ccf00a53c06ca32983106fd1a894c925d2a9630`; 82 focused и 515 linked FIFO/Telegram/Period Profit тестов passed. Синтетическая реализация; owner-case cutoff и реальные доказательства остаются не подтверждены. Далее FL22 — финансовые периоды и расчёт налогового эффекта.

# 2026-11-08 — FIFO deterministic replay FL20

- `FifoCostReplayService` assesses ambiguous same-date/equal-instant event orders using the existing allocation kernel. It allows a tie only when bounded valid permutations preserve every per-event layer/cost allocation and inventory totals; order-sensitive ties return `EVENT_ORDER_UNRESOLVED` without allocations. Oversized analysis fails closed with `FIFO_REPLAY_ORDER_ANALYSIS_LIMIT`; a large simple group is accepted only when one FIFO layer provably covers it.
- Replay output and preview fingerprint remain stable under report input-row reordering. Coverage includes date-only/timed constraints, cross-layer order sensitivity, equal instants, and large groups. No inventory write, FIFO activation, profit, tax, or bot workflow changed.
- FL20 code SHA `be6e7959`; replay tests **21 passed**, linked FIFO/Telegram/Period Profit profile **506 passed in 20.84s**, `compileall`, `git diff --check`, and `git diff --exit-code -- data` PASS. Synthetic fixtures only; `IMPLEMENTATION_VERIFIED=false`, `OWNER_CASE_VERIFIED=false`.
- Next: FL21, support linked returns and non-sale movements while preserving original return cost and existing Return COGS authorization.

# 2026-11-08 — FIFO safe initial activation proposal FL19

- Добавлен `FifoCostTransitionActivationProposalService`, подключённый через production `FifoCostTransitionService.build_activation_proposal`. Он объединяет case rate, opening evidence и proof-bound cutoff bridge только для review и не пишет ставку/слой/аллокацию.
- Новая ставка 14,65 ₽ и прежняя 21 ₽ доступны как owner-entered candidate; TOTAL_LANDED остаётся без выдуманной разбивки компонентов. Неизвестный new-home quantity остаётся `None`. Owner-declared 6 982 сохраняется отдельно; accepted supply units не прибавляются второй раз поверх подтверждённого cutoff snapshot. Buckets не суммируются в физический FIFO opening.
- Proposal проверяет case/store/SKU/revision, cutoff, stock fingerprint и preview-only условия. Несовпавший магазин получает пустые source buckets и без cutoff/watermark. При любых gaps proposal остаётся non-applicable; `fifo_opening_units=None`, `fifo_initialized` не изменяется, `ready_to_apply=False`.
- FL19 code SHA `a9a20e00627c0644b0a6b1d5b21592a37fd53df4`; dedicated tests **6 passed**, focused bridge/transition **29 passed**, linked FIFO/Telegram/Period Profit **502 passed**; compileall/diff-check/data-preservation PASS. Тестовые данные synthetic; owner case не верифицирован.
- Следующий этап FL20 — deterministic replay для предсказуемого FIFO порядка, без общей записи до FL23.

# 2026-11-08 — FIFO physical-sale cutoff bridge FL18

- FL18 добавляет отдельный read-only proof-bound bridge. Полный список identities из `/v1/finance/realization/posting` сопоставляется с точными строками физической даты/количества из owner-documented файла и отдельным подтверждением владельца семантики `PHYSICAL_OUTFLOW` для `Europe/Moscow`.
- Bridge проверяет scope/case/revision, cutoff и stock snapshot, полный период, pagination/source proof, уникальность identity, returns/non-sale coverage и unknown stock buckets. Дата финансовой строки не трактуется как физическое выбытие; повторные финансовые строки не создают повторную продажу.
- Выход остаётся preview-only, не пишет FIFO, налог или Period Profit. FL18 code SHA `2b216dc6eeda57144c2ae0183e423e39b8a32afd`; focused **36 passed**, linked FIFO/Telegram profile **496 passed**; compileall/diff-check/data-preservation PASS. `IMPLEMENTATION_VERIFIED` и `OWNER_CASE_VERIFIED` остаются false до завершения последующих этапов и проверки данных владельца.
- Следующий этап — FL19: безопасный opening proposal и ставка без прежнего manual anchor, пока без применения FIFO.

# 2026-11-08 — FIFO late-entry completion FL17

- FL00–FL17 реализованы на уровне кода и синтетических проверок; end-to-end мост продаж, атомарное применение, полная production-приёмка и реальный owner case ещё не завершены.
- `FifoCostTransitionReadinessService` формирует стабильную очередь требований с точным документом/действием, полями, периодом и безопасными locator-ами уже сохранённых evidence. Для owner-case список 6 982 остаётся неполным: 148 привязано к RECEIVING, 6 834 показано только как нераспределённый остаток. Неизвестное количество не считается новой поставкой.
- Подтверждённый оборотный отчёт, заканчивающийся 05.11, даёт явный missing period 06–07.11. Если период файла только candidate, сервис просит подтверждение периода и не объявляет интервал фактически отсутствующим. `complete_through=None` всегда; никакие readiness/preview оценки не изменяют case state или FIFO.
- Неизвестный reserved/пересечение FBS-возврата не сводится с available; точный sale/cutoff bridge остаётся обязательным. Конфликт акта выводится отдельным блокером с сохранённым fingerprint/source_as_of, если конфликтный locator доступен; синхронный source watermark не объявляется заданным SLA.
- Reconciliation результат теперь case-bound, чтобы нельзя было повторно использовать evidence с тем же store/SKU из другого case. FL17 code SHA `df7c095b20d556c1b333f0157c6b6d6448fd1329`; focused **34 passed**, linked FIFO/Telegram **477 passed in 20.53s**; compileall, diff-check, data-preservation PASS. Следующий этап — FL18: proof-bound sales/cutoff bridge.

- `FifoCostTransitionOpeningProposalService` строит read-only owner review: отдельно показывает подтверждённые stock buckets, supply declaration/status/acceptance, оборотные totals и buyer delivery/returns, не превращая 1 191/3 712/4 492 в FIFO opening. `fifo_opening_units=None`, `ready_to_apply=False`, `preview_only=True`, `is_atomic_snapshot=False`; запуск ничего не меняет.
- Отчётное доступное количество 1 191 сохраняет FBS return 9 как подмножество; planned 600 и transit 6 234 остаются разными buckets; owner-linked 148 RECEIVING показывается отдельно, accepted остаётся неизвестным. Ведомость 4 492 + 0 − 780 − 3 712 = 0 сохраняет redeemed 775 и non-sale 5, closing buyer delivery 1 646/return transit 70. Имя файла остаётся candidate; полный период после 05.11 не подтверждён.
- Owner facts old-home=0 и old-transit=0 показаны независимо, new-home остаётся unknown. Неизвестный cutoff, source gaps, unknown reserved/overlap и необходимость sale bridge перечислены в requirements; их детерминированная очередь реализована на FL17.
- FL16 code SHA `a33a0792bf3142924af280c39d32df2fd7ea0b9d`; focused linked profile **83 passed**, полный FIFO/Telegram профиль **458 passed**; compileall, diff-check, data-preservation PASS.
- `FifoCostTransitionSupplyReconciliationService` строит раздельные declared, observed, accepted, pending и discrepancy; сохраняет capture/source-as-of, report period/provenance/fingerprint и всегда возвращает `is_atomic_snapshot=False`. MISSING/unknown не превращается в ноль или подтверждённую приёмку.
- Контроль 6 982; owner-linked RECEIVING 148; XLSX `supplier_planned=600`, `supplier_transit=6 234`: проверен синтетически. Известный остаток owner total 6 834 — только арифметически нераспределённое количество, а принятие остаётся неизвестным.
- FL15 focused reconciliation + supply/acceptance/stock/report parser profile: **74 passed in 3.39s**; linked FIFO/Telegram profile: **449 passed in 20.34s**. `compileall`, `git diff --check`, `git diff --exit-code -- data` PASS; данные не менялись. Следующий FL16 — proposal начального среза только для owner review, без изменения FIFO.
- Новый `TelegramFifoCostReportImportService` принимает XLSX только для явно выбранного редактируемого дела. До отдельного подтверждения persistent evidence и case revision не меняются. Подтверждение привязано к tenant/store/SKU/case revision, повтор callback идемпотентен, дата имени файла остаётся `FILENAME_CANDIDATE`.
- `FifoCostReportImportWorkerClient` запускает allowlisted parser в собственном subprocess с timeout 15 секунд и глобальным пределом 3 workers; payload evidence проверяется против 262,144-byte storage cap. XLSX-маршрут отделён от прежнего CSV-потока; oversized XLSX отклоняется до скачивания при известном Telegram-размере.
- FL14 code SHA `58ba757b52d0d92708e8d2aaa6bb88adb666f77a`; focused **47 passed**, linked FIFO/Telegram/seller-cost/return profile **462 passed**. `compileall`, `git diff --check`, `git diff --exit-code -- data` PASS. `data/` не менялась.
- `IMPLEMENTATION_VERIFIED: нет` для всего продукта; `OWNER_CASE_VERIFIED: нет`. Реальные файлы, БД владельца, Telegram/Ozon API и запуск бота не использовались.

# 2026-11-08 — FIFO late-entry completion FL11

- FL00–FL11 VERIFIED в коде исполнения, но не в production и не на owner case. `FifoCostTransitionSupplyRefreshService` выполняет active status + accepted acts под общим bounded budget до 20s/10 HTTP attempts; status observations сохраняются только после завершённого чтения.
- Partial pagination/timeout сохраняют checkpoint progress, связанный с owner/store/SKU/case/declaration/reference/revision. Найденная до последней страницы поставка продолжается, а межстраничный duplicate ID конфликтует. Restart и scope mismatch безопасно блокируют старый continuation; reference digest остаётся скрытым в public manifest.
- FL11 commit `66d05d38`; focused wrapper/source/declaration **40 passed**; полный FIFO/Telegram FIFO профиль **388 passed in 16.26s** на SHA `66d05d381b3981c767fcd2fd4c4d057c7b1bd50a`. `compileall`, `git diff --check` и `git diff --exit-code -- data` PASS; следующий FL12 — parser оборотной ведомости.

# 2026-11-08 — FIFO late-entry completion FL10

- FL00–FL10 VERIFIED на `codex/fifo-late-entry-foundation-20261107`. FL10 добавил `FifoCostSupplyAcceptanceReconciliationService`: кумулятивные accepted totals выбираются как latest (40→70→100 остаётся 100), повтор акта/снимка не удваивает результат, а два разных акта остаются в digest refs раздельно.
- Более свежий PARTIAL не обнуляет последний complete accepted count, но возвращает PARTIAL и блокирует финальную discrepancy. Снижение 100→90 требует документальной коррекции; final accepted ниже declared показывает unaccepted quantity и action code без автоматического inventory/FIFO движения. Отмена status observation не удаляет declaration.
- FL10 commit `9445d8cc`; focused 46 passed; весь FIFO/Telegram FIFO профиль 379 passed; compileall/diff-check/data unchanged PASS. Следующий FL11: общий бюджет чтения, checkpoints и безопасное resume.

# 2026-11-08 — FIFO late-entry completion FL09

- FL00–FL09 VERIFIED. `FifoCostSourceCollectionService.observe_active_supply_by_id` наблюдает активные статусы отдельно от старого COMPLETED-only lookup, пишет append-only PRESENT/MISSING observations и возвращает continuation при PARTIAL. Только полная пагинация подтверждает MISSING; отсутствующая строка не становится нулём и не стирает декларацию/частичную приёмку.
- Неизвестный статус сохраняется как безопасный raw token и нормализуется в UNKNOWN. FL09 code commit `f2e2239a`; focused 51 passed; full `pytest -q` 4907 passed; compileall/diff-check/data restored PASS.

# 2026-11-08 — FIFO late-entry completion FL08

- FL00–FL08 VERIFIED on `codex/fifo-late-entry-foundation-20261107`. `FifoCostTransitionService` now persists exact typed ORDER/SUPPLY declarations; existing `FifoCostRepository` enforces same-store reference uniqueness, SKU consistency, and the case-level owner quantity inside the write transaction.
- Lookup IDs are never returned by the service: persistence contains only a scope/type-separated digest and optional existing Fernet ciphertext. Missing key preserves owner quantities and marks lookup unavailable. The owner total minus known declared supplies is reported as `undistributed_units`; there is no synthetic supply ID.
- FL08 code commit: `363cc5e899f7d01c682e7f4dc8a62a03977b708c`. Verification: focused **38 passed**, all FIFO/Telegram FIFO **358 passed**, compileall/diff-check/data-preservation checks PASS. Next FL09: active-supply observations and explicit MISSING status. `IMPLEMENTATION_VERIFIED` and `OWNER_CASE_VERIFIED` remain false.

# 2026-11-08 — FIFO late-entry completion FL07

- FL00–FL07 VERIFIED on `codex/fifo-late-entry-foundation-20261107`. New `FifoCostTransitionService` coordinates typed case create/update/cancel/read/list through existing `FifoCostRepository`. Every update or cancellation writes an append-only case revision; exact retries are idempotent.
- Active case uniqueness is enforced atomically by tenant/store/SKU inside the repository transaction. Read/list APIs remain tenant/store/SKU scoped. Dispatch date is stored as a date-only owner fact and does not initialize FIFO, cutoff, allocation, or profit mode.
- FL07 code commit: `5254efafe05e197564a4913c5123373ca0db13c2`. Verification: focused **25 passed**, complete FIFO/Telegram FIFO **352 passed**, compileall/diff-check PASS; `data/` unchanged. Next FL08: declarations for concrete supplies and encrypted lookup references. `IMPLEMENTATION_VERIFIED` and `OWNER_CASE_VERIFIED` remain false.

# 2026-11-08 — FIFO late-entry completion FL06

- FL00–FL06 VERIFIED on `codex/fifo-late-entry-foundation-20261107`. Rate entry supports `COMPONENTS` and `TOTAL_LANDED` through one monetary amount contract. The validated pair `10.00 + 3.00 + 1.65` / `14.65` yields equal `14.65 ₽/unit`; total-only records persist null component amounts.
- Rate history and CSV identify `TOTAL_LANDED` and do not render `14.65` as purchase cost or missing parts as zero. Schema migration tests retain historical rate mode as `COMPONENTS`. Existing FIFO calculations continue to consume the canonical `unit_cost_rub`.
- FL06 code commit: `08472f865dedabcda3edf2c4b2e68bfc9ab2465d`. Verification: focused **59 passed**, full FIFO/Telegram FIFO **348 passed**, compileall/diff-check PASS; `data/` unchanged. Next FL07: durable case application service. `IMPLEMENTATION_VERIFIED` and `OWNER_CASE_VERIFIED` remain false.

# 2026-11-07 — FIFO late-entry completion FL05 fault boundaries

- FL00–FL05 VERIFIED на `codex/fifo-late-entry-foundation-20261107`. FL05 добавляет сбойные границы для create/update case и всех evidence append: каждый injected SQL fault после частичной записи оставляет количество строк и case revision прежними.
- Сохранение pending case до FIFO проверено через настоящий `FifoCostRepository`, `FifoCostPeriodProfitSourceService` и canonical Period Profit summary на synthetic finance/cost sources: cost mode остаётся LEGACY, FIFO history не создаётся, себестоимость 21 ₽ и прибыль 53 ₽ совпадают до/после.
- FL05 targeted profile — 69 passed; связанный FIFO/Telegram/Period Profit профиль — 370 passed; compileall/diff-check PASS; пять `data/` файлов (3,168 bytes) не менялись.
- Следующий этап: FL06 — `TOTAL_LANDED` / `COMPONENTS` единый amount contract и сохранение полной себестоимости без ложной компонентной разбивки.

# 2026-11-07 — FIFO late-entry completion FL04 repository commands

- FL00–FL04 VERIFIED на `codex/fifo-late-entry-foundation-20261107`. FL04 добавляет scoped append/read/CAS/idempotency для cases и evidence на существующем `FifoCostRepository`; append-only evidence и case revisions выполняются одной repository-транзакцией.
- Проверены restart чтения, очередь ещё не создана, replay/conflict, параллельный CAS, tenant isolation, safe ciphertext read и квоты 20/100/2000 с сохранением последней committed state. 63 focused tests и 357 связанных FIFO/Telegram tests прошли; compileall и diff-check PASS.
- `data/` не менялась (`git status --short -- data` пусто). Никакая реальная owner DB или Ozon/Telegram API не использовалась. `IMPLEMENTATION_VERIFIED` и `OWNER_CASE_VERIFIED` ещё false.
- Следующий этап: FL05 — fault injection каждой записи и доказательство, что pending case до FIFO не меняет legacy/history/actual profit.

# 2026-11-07 — FIFO late-entry completion FL00–FL02

- Исполнительная ветка `codex/fifo-late-entry-foundation-20261107` ответвлена от точного PR #727 head `aef1f1348fca4e7728215b73ddd32004a0540e20`; PR спецификации открыт на `main` `d8d4ba00c85acf14ba9a960f56a755fbe30b555c`.
- FL00 VERIFIED: исходный FIFO regression профиль **307 passed**; FL01 VERIFIED: карта integration seams, 27 code/test paths. FL02 VERIFIED: typed transition contracts, **13 new tests** и combined FIFO profile **320 passed**; compileall/diff-check PASS. Пять файлов `data/` побайтно/по manifest совпадают с исходной точкой.
- Начата runtime реализация только валидации DTO; repository/migration/UI/финансовая интеграция ещё не изменялись. Следующий этап FL03 — schema v13 и общий cipher provider. `IMPLEMENTATION_VERIFIED` и `OWNER_CASE_VERIFIED` пока false; реальные ID поставок и cutoff не подтверждены.

# 2026-11-07 — FIFO late-entry FL03 schema v13

- `FifoCostRepository` теперь владеет семью transition evidence таблицами в существующей tenant-local SQLite базе; FIFO schema version — 13. Миграция 12→13 сохраняет прежние rate values, индексы, триггеры и child FK edges; прежние ставки читаются как `COMPONENTS`. Для `TOTAL_LANDED` компоненты остаются `NULL`.
- Общий `tenant_cipher_provider` использует только существующий Fernet key contract `OZON_CREDENTIAL_MASTER_KEY`; `OzonAccountRepository` делегирует ему создание cipher без смены формата и контракта credentials.
- FL03 VERIFIED: новый migration/cipher profile вместе с существующими repository/backup/credential tests — 41 passed; partial-DDL rollback, future schema refusal и tenant scope проверены на временных SQLite. `data/` и live DB не читались/не изменялись. Следующий этап FL04 — repository commands для case/evidence. IMPLEMENTATION_VERIFIED и OWNER_CASE_VERIFIED остаются false.

# 2026-11-07 — подготовлено ТЗ завершения позднего ввода FIFO

- PR #726 слит в main d8d4ba00; владелец обновил локального бота. Реальный случай новой партии в пути выявил незавершённый путь: поздний мастер требует принятую поставку и сохраняет только черновик.
- Подготовлено LUNA_FIFO_LATE_ENTRY_COMPLETION_TASK_2026-11-07.md: 36 этапов FL00–FL35, фиксированные контракты, durable case до начальной FIFO, TOTAL_LANDED стоимость, учёт исчезающих при приёмке наблюдений, импорт отчётов, cutoff bridge и атомарное применение.
- Журнал LUNA_FIFO_LATE_ENTRY_COMPLETION_PROGRESS_2026-11-07.md: все этапы NOT_STARTED. Числовая матрица N01–N40 в FIFO_LATE_ENTRY_CASE_AND_ACCEPTANCE_2026-11-07.md. Implementation и owner-case readiness разделены; фактический source gate не снимается спецификацией.
- Это документационная подготовка. Runtime, реальные FIFO-записи, прибыль, Ozon/Telegram и данные владельца не изменены. План сдачи — три зависимых PR, независимый review; без merge/deploy/реального запуска при исполнении.

# 2026-11-07 — исправлены две FIFO-навигации по результатам review PR #726

- После успешного CSV preview старые FIFO rate/late/anchor черновики закрываются; CSV черновик остаётся активным для проверки и подтверждения. Невалидный CSV не очищает текущий FIFO ввод.
- После проверки действительного одноразового `seller_cost_resume_unit` callback FIFO черновики закрываются до пересчёта карточки целевого SKU. Stale callback оставляет текущий ввод без изменений.
- Новый связанный профиль регрессий: **44 passed**; полный Windows `pytest -q`: **4,851 passed in 51.12s**. До/после manifest пяти файлов `data/` совпал, два новых тестовых файла удалены. Exact-head CI run [42370751926](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/42370751926) passed на implementation SHA `7896289a14a127eb097800225f28fbf0915a46da`: Windows/Linux full verification и production Docker build/runtime smoke.

# 2026-11-07 — исправлены три перехода FIFO review (PR #726)

- Валидная кнопка возврата к себестоимости другого SKU очищает старые seller-cost/FIFO мастера только после успешной проверки одноразового callback. Устаревший callback не меняет ввод.
- Принятый FIFO-переход и успешная команда `/start` закрывают конкурирующие произвольные текстовые формы. `/start` завершает FIFO, seller-cost и return-inventory черновики; отказ допуска профиля сохраняет FIFO-состояние.
- End-to-end профиль Telegram: **69 passed in 1.77s**; полный Windows `pytest -q` с `PYTHONPATH=app`: **4,848 passed in 50.31s**. `compileall -q app tests` и `git diff --check` PASS. До/после снимок `data/`: исходный `tasks.json` восстановлен побайтно, два новых тестовых файла удалены, остальные четыре исходных файла не изменились.
- Кодовый SHA `899da6f7c510ec10f54254eea98a9b14916b9973` опубликован в PR #726; exact-head GitHub Actions run [42366323896](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/42366323896) прошёл: Windows/Linux full verification и production Docker build/runtime smoke. Документирующий follow-up commit запускает повторный CI на новой голове. Слияние, deployment, live Ozon/Telegram запросы и запуск бота не выполнялись.

# 2026-11-07 — FIFO review fixes R1–R3 (PR #726)

- Поток FIFO определяется на уровне активного store/SKU: изменение или обогащение product/offer identity не отключает существующий FIFO и не создаёт вторую историю. Неоднозначность возвращает `FIFO_IDENTITY_CONFLICT` в repository/Period Profit; автоматическое объединение запрещено.
- Возвратная Telegram-навигация очищает legacy seller-cost и FIFO rate/late/anchor drafts. FIFO callback обрабатывается до очистки возвратного черновика; его завершает только успешная FIFO history-навигация, а stale/invalid callbacks сохраняют черновик.
- Регрессии добавлены в `tests/test_fifo_current_unit_cost_adapter.py` и `tests/test_telegram_fifo_cost_history.py`. Связанный профиль: **85 passed in 2.38s**; полный Windows pytest: **4,844 passed in 50.66s**; compileall/diff-check прошли. Полный прогон изменил один и создал два тестовых файла в `data/`; они восстановлены/удалены, итоговый manifest совпал с исходным. Exact-head run [42363101157](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/42363101157) прошёл на code SHA `23d3a3420a7390684a9f4e972f6b1c5f6eeb4dce` (Windows/Linux и production Docker smoke).
- PR #726 остаётся незлитым; deployment, live Ozon/Telegram запросы и запуск бота не выполнялись.

# 2026-11-07 — FIFO review R1–R3 исправлены в PR #726

- Исторический финансовый SKU с подтверждённой датированной себестоимостью сопоставляется с текущим каталогом только по уникальному точному product ID или offer ID. Канонический SKU позволяет проверить FIFO-режим: при неактивном потоке расчёт продолжает legacy-путь, при неоднозначной связи остаётся fail-closed.
- Подтверждённая связь продавца допускает изменившийся product ID при точном совпадении offer ID; конфликт обоих признаков отклоняется. Устаревшие FIFO-кнопки сохраняют активный сценарий цены; действительный переход в историю очищает сценарий только после проверки тикета.
- Добавлены регрессии для exact-ID/offer recovery, конфликтных идентичностей и сохранения/очистки сценария калькулятора.
- Проверки: целевой Windows-профиль **97 passed**; полный `pytest -q` **4,839 passed in 50.57s**; `compileall` и `git diff --check` прошли. Пять файлов `data/` восстановлены, before/after SHA-256 manifest совпал (`48465375f82c196c8e20388fa9d7f3b1752d33a6407630ac23f682ec016650cd`). Exact-head GitHub Actions run [42360261757](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/42360261757) прошёл для implementation SHA `ccb3d4101308e225448da4965957aa3912338d3b`: Windows/Linux full verification, production Docker build и runtime smoke.

# 2026-11-07 — FIFO review R1–R3 исправлены в рабочей копии PR #726

- Финансовые SKU-алиасы, подтверждённые для одного точного FIFO-потока, сверяются совместно: ожидаемые продажи всех алиасов сравниваются с полной аллокацией потока, после чего COGS и единицы выделяются по digest каждой продажи исходному финансовому SKU. Неизвестные, пропущенные и лишние идентичности не принимаются; stream-wide разборка по слоям не показывается как разборка отдельного алиаса.
- После сохранения начального FIFO-якоря, новой ставки и позднего черновика новые сообщения больше не перехватываются старым мастером. Повторные кнопки подтверждения/отмены возвращают сохранённый результат и сохраняют идемпотентность.
- Тесты на финальном коде: целевой профиль **48 passed in 1.62s**; полный Windows `pytest -q` **4 829 passed in 50.63s**; `git diff --check` и `python -m compileall -q app tests` прошли. Полный прогон восстановил все 5 исходных файлов `data/` побайтно (совпадающий SHA-256 manifest).
- Изменения ещё не закоммичены и не опубликованы; PR #726 exact-head CI ожидает нового SHA. Слияние, deployment, live API и запуск бота не выполнялись.

# 2026-11-07 — FIFO review: исправлены следующие R1–R3 на PR #726

- `FifoCostPeriodProfitSourceService` использует текущий SKU каталога только при `historical_sku_identity_recovered=true` и известном подтверждённом источнике. SKU начисления остаётся ключом продажи и финансового digest; неодобренное расхождение блокируется до проверки режима, чтобы нельзя было незаметно уйти в legacy COGS.
- Повторный callback «Отмена» после подтверждённой записи начального остатка или новой ставки теперь возвращает сохранённый результат.
- Telegram-мастер начального остатка ограничивает число слоёв реальной ёмкостью хранилища, проверяет по каждой зоне предел 100 000, общий остаток и совокупные пределы событий/нулевых ссылок с учётом ещё не введённых слоёв. Исправление ошибочной текущей партии сохраняет предыдущие данные черновика.
- Связанные FIFO/Period Profit/Telegram/anchor tests: **61 passed**; полный Windows pytest: **4,826 passed in 50.90s**. Полный прогон восстановил все **5/5** исходных файлов `data/` с точными SHA-256; `compileall` и `git diff --check` PASS. Живые Ozon/Telegram запросы и запуск бота не выполнялись.

# 2026-11-07 — повторный FIFO review: R1–R3 исправлены

- StorePeriodProfitService в Telegram production wiring проверяет точный SKU и даты до чтения legacy-текущей себестоимости. Активный FIFO или диапазон через cutoff не получает legacy COGS; ошибку проверки режима также нельзя обойти. Периоды полностью до cutoff продолжают использовать прежний путь.
- Нормализатор стоков считает ответ неполным, если в точной строке товара нет числовой строки FBO, включая пустой список и FBS-only. CONFIRMED_ZERO остаётся только для явной строки FBO с нулевыми количествами.
- Владелец вводит FIFO-слои от самой старой партии к новой, отдельно подтверждает порядок и видит в финальном preview номер слоя, общее количество и цену слоя.
- Полный Windows pytest -q: 4,822 passed in 50.54s. Связанные тесты: 81 passed. compileall и git diff --check прошли; пять исходных файлов data/ восстановлены по точным SHA-256. Живые Ozon/Telegram запросы и запуск бота не выполнялись.
- Остающееся ограничение: фактический FIFO COGS по-прежнему закрыт до проверки общего cutoff остатков и физических продаж.

# 2026-11-07 — повторные review-исправления FIFO R1–R4 (PR #726)

- Исправлена проверка старого остатка при первой новой ставке; противоречивое количество сверх подтверждённого конечного слоя теперь отклоняется до записи.
- Полностью replay-подтверждённая себестоимость теперь проходит allowlist планирования, кэширования и отображения с сохранением запрета на фактический Period Profit.
- FIFO-доступ разделён с настройкой legacy-себестоимости: список всех SKU разбит на страницы по 20, переходы обработаны Telegram-адаптером.
- Округление цены партии задано явно как `ROUND_HALF_UP`.
- Проверки: связанные тесты **74 passed in 3.45s**; полный Windows `pytest -q` **4,812 passed in 50.98s**; `compileall -q app tests` и `git diff --check` PASS. Все 5 файлов `data/` восстановлены с совпавшими SHA-256; два созданных тестами файла удалены после проверки, что они находятся только внутри `data/`.
- Кодовый коммит `0511922d8073e9d5a915e95d7693260f0a0a0b4e` запушен в ветку PR #726; exact-head CI run [42312193535](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/42312193535) прошёл на Windows/Linux и с production Docker build/runtime smoke. Документационный коммит `1e004ee38697eb9e0748ebf862c97bad338f31de` также прошёл exact-head CI run [42312664968](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/42312664968). PR не слит; развёртывание, живые запросы и запуск бота не выполнялись.

# 2026-11-07 — FIFO review fixes для PR #726

- Исправлены восемь замечаний ревью и добавлен отдельный безопасный путь для SKU с нулевым остатком: полная точная выборка Ozon плюс подтверждение владельца по дому/транзиту; первая ставка сохраняет cutoff и доступна только как плановая открытая ставка.
- Целевой профиль: **113 passed in 3.49s**; полный набор: **4,807 passed in 50.16s**. `compileall` и `git diff --check` проходят. Изменения тестов в `data/` удалены/восстановлены по точной предтестовой копии. Изменения не запушены, слияние/deploy/запуск бота не выполнялись.
- Фактический FIFO COGS остаётся заблокированным до подтверждения общего физического cutover. Начальные партии и нулевой старт не меняют фактическую прибыль; owner acceptance и production source semantics остаются pending.

# 2026-11-06 — FIFO FC35: draft PR и пакет review

- PR реализации #726 открыт на `main` как draft. Независимому проверяющему подготовлен `FIFO_COST_REVIEW_HANDOFF_2026-11-06.md` с архитектурой, миграцией schema v11, числовой матрицей, тестами и ограничениями.
- FC34 локально зелёный (4,792 passed; целостность data подтверждена). Полноценность сдачи зависит от GitHub Actions Windows/Linux и Ubuntu Docker smoke на текущем SHA PR; слияние, запуск бота и реальная приёмка не выполнялись.
- Сохраняются продуктовые gates: Telegram начального FIFO-якоря отсутствует; поздний ввод не реконструирует replay; фактический COGS заблокирован до подтверждения физической даты продаж и общего cutoff; owner acceptance pending.

# 2026-11-06 — FIFO FC34: локальный прогон зелёный, CI ожидается

- После согласования существующего меню с новым экспортом истории актуализировано ожидание одного теста; функциональное поведение не менялось.
- Windows/Python 3.12.10, pytest 8.4.2: полный набор **4,792 passed in 50.14s**; `compileall -q app tests` и `git diff --check` PASS.
- Снимок до/после подтверждает неизменность всех 6 файлов `data/` по длине и SHA-256; созданных незапланированных файлов нет. GitHub Actions run 42279830501 прошёл Windows/Linux и production Docker build/runtime smoke на exact SHA `18ee4e6e459d2aa6a324ae0ef7d5a40e6828baa5`. PR #726 открыт к независимому review, не слит. Финальный статусный коммит запускает такой же workflow на актуальном PR head.
- Известные ограничения FIFO остаются: Telegram-ввода начального якоря нет; поздний ввод пока документирует evidence draft, а фактический FIFO COGS закрыт `SOURCE_BLOCKED` до подтверждения единой даты/cutoff запасов и финансовых продаж. Реальная приёмка владельцем не выполнялась (`USER_VALIDATION_PENDING`).

# 2026-11-06 — FIFO FC33: руководство готово, живая приёмка ожидает владельца

- Добавлены [руководство владельца](../docs/fifo-cost-history-user-guide.md) и [план безопасной приёмки](FIFO_COST_OWNER_ACCEPTANCE_2026-11-06.md). Они объясняют ввод ставки и поздней поставки, нулевой домашний остаток, транзит, продажи у границы, возвраты, третью ставку, коррекцию и снимок сохранённого плана.
- Проверено production wiring: карточка FIFO, история, новая ставка и поздний черновик подключены; начальный якорь не имеет Telegram-ввода. Неинициализированный SKU поэтому нельзя настроить владельцем целиком через бот. Фактический FIFO COGS остаётся `SOURCE_BLOCKED`; проверка реального магазина — `USER_VALIDATION_PENDING`.
- Документированы legacy/FIFO/planning/supply режимы и ограничения каждого. ADR 066 принят; архитектурное решение не менялось. Живые Ozon/Telegram вызовы и запуск бота не выполнялись.

# 2026-11-06 — FIFO FC32: числовые и последовательностные проверки пройдены

- N01–N24 проверены существующими независимыми тестами этапов: точные суммы и остатки, источник/полнота/отсечка, продажи и повторы начислений, возвраты и движения, поздние исправления, текущая себестоимость, плановый объём с налоговыми режимами, выгрузка, бюджеты API, backup и миграции.
- Новая проверка перебирает все 6 порядков входа для трёх датированных продаж через слои `2×10 ₽ + 3×20 ₽ + 4×30 ₽`: COGS всегда `170.00 ₽`, распределение по слоям одинаково, списано ровно 8 единиц и остаётся 1. Проверка периодных чтений подтверждает, что повторные запросы дней/диапазона не меняют allocation revision и дают прежние суммы.
- FC32 профиль: **406 passed in 12.25s**; compileall и `git diff --check` PASS; 6/6 файлов в `data/` совпали по длине и SHA-256. Только синтетические данные и временные SQLite.
- Ограничение сохраняется: корректный отказ при недоказанной отсечке — проверка безопасности, но не подтверждение реального FIFO COGS. До доказанного cutoff фактический расчёт FIFO остаётся `SOURCE_BLOCKED`.

# 2026-11-06 — FIFO FC31: backup/restore и атомарные миграции проверены

- Через штатный backup сервис FIFO history/rates, источники и ссылки поставок, allocation revision, late-correction audit и saved plan восстановлены в новый storage root; после открытия новыми репозиториями history/current-cost/export сохранили данные, а replay вернул те же `14.00 ₽` COGS для тестового распределения.
- `.env`, runtime cache и временные Telegram/FIFO подтверждения не переносятся; старый callback после восстановления не принимается. Проверены additive migration, сохранность legacy/planning данных и откат неудачной миграции без частичной схемы.
- FC31: **103 passed in 5.77s**, compileall и `git diff --check` PASS; 6/6 файлов в `data/` совпали по размеру и SHA-256. Только временные корни и синтетические фикстуры.

# 2026-11-06 — FIFO FC30: конкурентность сбора источников

- Регрессии подтверждают: одинаковый owner/store/SKU запрос объединяется в single-flight, а одновременные запросы для другого магазина и другого точного SKU не блокируют друг друга. Неполное подтверждение остатков остаётся `PARTIAL`; проверка параллелизма не повышает доказательность источника.
- FC30 связанный профиль: **116 passed in 4.55s**, compileall и `git diff --check` PASS. Только synthetic-клиенты и временная SQLite; без реальных API и запуска бота.

# 2026-11-06 — FIFO FC29: импорт с проверкой версии и выгрузки истории

- Существующий шаблон legacy-себестоимости остался совместимым. Валидация ограничивает UTF-8 CSV размером 1 МБ/1000 строк/4096 знаков ячейки, отклоняет неоднозначный SKU, лишние/повторные строки и повторные даты. Несколько дат по одному legacy SKU подтверждаются одним пакетом.
- Preview фиксирует ссылку файла и ревизию каталога/истории; подтверждение повторно сверяет их и атомарно проверяет revision CAS до вставки. Ссылка и ревизия остаются в provenance записи и видны в CSV-выгрузке истории.
- FIFO SKU нельзя импортировать через legacy-путь. FIFO выгрузка revision-bound, read-only, formula-safe и явно помечает неизвестное количество открытой ставки. Пакетный импорт FIFO-партий не реализован: количество и граница требуют существующего отдельного подтверждения владельца.
- FC29: **80 passed in 2.16s**, compileall/diff-check PASS. Only temporary SQLite/synthetic fixtures; production cutoff remains unchanged.

# 2026-11-06 — FIFO FC28: объяснение себестоимости по слоям

- Отчёт периода показывает разбиение FIFO COGS/единиц по слоям с датой действия, происхождением, подтверждением, режимом, cutoff, полнотой и ревизией коррекции. Предыдущий и новый результаты сопоставляются по COGS, налогу и прибыли, старая версия остаётся в append-only истории.
- Telegram и выгрузка используют общую allowlisted проекцию и одинаковые суммы/ref. Длинное сообщение делится существующим Telegram splitter; выгрузка не отбрасывает слои молча при лимите сериализатора. Идентификаторы БД и исходные digest не раскрываются.
- FC28 профиль: **49 passed in 2.05s**; compileall/diff-check PASS. Источники синтетические, cutoff фактического COGS остаётся заблокированным до отдельного подтверждения.

# 2026-11-06 — FIFO FC27: frozen основа в сохранённых планах

- Подтверждённая проекция объёма продаж теперь сохраняет версионированный allowlisted FIFO snapshot в той же ревизии плана: SHA-256 basis ref, FIFO revision/method, Q, точные строки распределения и явный статус частичности/неполноты. Snapshot остаётся модельным и не становится фактическим COGS.
- Копирование, чтение после перезапуска и экспорт сохраняют исходную основу; новый объём требует нового снимка, а устаревший снимок не проходит проверку. Сравнение планов и ранжирование наблюдений не приравнивают неизвестные или различные FIFO-основы.
- FC27: **96 passed**, `compileall -q app tests`, `git diff --check`; контрольный набор данных **59/59** совпадает. Кодовый коммит: `8d905567`.

# 2026-11-06 — FIFO FC26: sales mix по точным слоям

- `FifoPlanningQuantityAllocationService` строит read-only allocation заданного количества по конечным слоям FIFO и текущей открытой ставке. Точная сумма COGS становится входом существующего агрегатного расчёта `SalesMixPlanningService`/`TaxService`; округлённое среднее не используется как вычислительное значение.
- Frozen plan сохраняет только allowlisted cost basis/revision/as-of/cutoff/слои. Ручная себестоимость остаётся отдельным допущением. Если остатка и ставки не хватает, SKU исключается из итогового расчёта; подтверждённая часть показана как partial и явно не включена в прибыль.
- Планирование остаётся модельным; Factual Period Profit, налоговые цепочки и cutoff gate не менялись. Проверка текущего FC26 SHA: **256 passed**, compileall/diff-check PASS; baseline data **59/59** точно совпал.

# 2026-11-06 — FIFO FC25: единый basis для одиночного планирования цены

- Все цены в сетке/сравнении и поиск целевой цены используют один замороженный снимок себестоимости следующей успешной единицы; повторный вызов расчёта не расходует и не перечитывает FIFO-очередь.
- Если владелец вводит ручную себестоимость, она применяется только в текущем сценарии, а FIFO остаётся справочной основой. Результат сообщает остаток слоя и предупреждает, что оценка одной единицы не описывает больший объём.
- Комиссия остаётся кандидатной: тариф пересчитывается по каждой цене, включая копейки вокруг границы. Для чувствительности подтверждено, что фиксированная FIFO-себестоимость сохраняется, а неизвестная реклама не превращается в ноль.
- FC25 profile: **80 passed in 1.27s**, `compileall` и `git diff --check` PASS; данные не изменены. Code commit `1a22f081`. Продолжение: FC26 — точное распределение объёма продаж по FIFO-слоям.

# 2026-11-06 — FIFO FC24: общий current cost adapter

- Текущая юнит-экономика и источник сценария цены используют один read-only `FifoCurrentUnitCostAdapter`. Незаведённая FIFO-история сохраняет legacy effective-date режим; существующая, но требующая replay/неполная история не заменяется legacy-ценой.
- Текущая оценка показывает метод, срез/отсечку, себестоимость следующей единицы, конечный остаток слоя, следующую ставку и полноту. FIFO остаётся planning-only; cutoff gate фактического Period Profit не изменён.
- Cache identity включает owner/store/exact product+offer+SKU, дату и fingerprint полной обезличенной FIFO-истории. Targeted profile: **393 passed in 7.28s**, compileall и `git diff --check` PASS; локальные данные неизменны. Следующий этап: FC25 — согласованная себестоимость во всех одиночных/сеточных/целевых сценариях цены.

# 2026-11-06 — FIFO FC23: безопасные границы ставок и отмена будущего плана

- FIFO schema v10→v11 добавляет append-only журнал отмены неиспользованной будущей ставки. Оригинальная ставка и порядок истории сохраняются; history показывает её как отменённую. Подтверждение ограничено владельцем/магазином/SKU, ревизией и неизменившимся источником; событие на границе, allocation или reconciliation запрещают отмену.
- Равные date-only границы между новой ставкой и предыдущей ставкой/конечным слоем отклоняются как неоднозначные. Снимок остатков с датой позже даты текущего запроса не подтверждает переход. Поздняя реконструкция с уже активной multi-rate историей по-прежнему fail-closed; production cutoff, возвраты и несбытовые движения остаются нерешёнными.
- Telegram показывает отмену только для запланированной ставки, требует отдельного подтверждения, сохраняет короткий opaque callback и сразу обновляет журнал; устаревшая кнопка после изменения данных ничего не записывает.
- Связанный FC23 профиль: **89 passed in 4.00s**; compileall и `git diff --check` PASS. Только синтетические данные и временная SQLite; реальные Ozon/Telegram запросы, бот и deploy не выполнялись. Next: FC24 current-economics cost adapter/cache invalidation.

# 2026-11-06 — FIFO late-entry reconstruction, FC21

- `FifoCostLateEntryReconstructionService` now creates a read-only exact-SKU replay preview bound to the saved late-entry draft, accepted-supply evidence fingerprint, stream revision, allocation revision and source-set fingerprint. A complete synthetic path applies one hypothetical rate only after its owner-confirmed historical boundary; the act's accepted quantity remains documentary and contributes zero inventory.
- Missing/reconciled-cutoff evidence, incomplete/unsupported movement history, stale drafts, untrusted sales, unresolved same-day ordering, and unsupported existing rate transitions fail closed. The Telegram reply requests the required evidence and explicitly says current stock was not used as historical stock. No event, rate, layer, allocation, tax, or Period Profit is changed.
- Linked profile: **261 passed in 8.81s**; `compileall -q app tests` and `git diff --check` PASS. Code commit: `b1e6a0fe`. Synthetic fixtures and temporary SQLite only; no live API/Telegram request or bot startup. `DONE_WITH_GAP`: production historical cutoff is still unreconciled. Next: FC22 impact preview and append-only correction commit.

# 2026-11-06 — статус реализации FIFO себестоимости

- FC20 `DONE_WITH_GAP`: добавлен owner-confirmed Telegram-сценарий позднего ввода уже отправленной партии. Черновик содержит стоимость/расходы, остаток старой партии дома, дату фактического перехода, количество из принятого односоставного акта Ozon и ревизию FIFO; IDs остаются только в памяти запроса, в хранилище идут digest-ссылки. Запись не меняет FIFO-слои/остатки, Period Profit, налог или прибыль. Целевой профиль: **269 passed in 8.25s**, после cleanup — **36 passed in 1.47s**; compileall и `git diff --check` PASS. Реконструкция и preview ожидаются в FC21–22; production cutoff остаётся заблокированным.

# 2026-11-06 — статус реализации FIFO себестоимости

- FC19 завершён как `DONE_WITH_GAP`: schema v8 добавляет append-only оценочные строки несбытового выбытия. Недостача дома, утилизация Ozon, возврат поставщику и списание вводятся раздельно; replay уменьшает конечные FIFO-слои и хранит их оценку отдельно от COGS продаж/денежной прибыли. Открытая ставка и нехватка известного слоя блокируют оценку. Недоприёмка показывает declared−accepted как расхождение без списания, перемещение HOME/TRANSIT/OZON не меняет агрегатный пул. Связанный профиль — **111 passed in 3.49s**; полный pytest — **4,676 passed in 46.45s**. Данные восстановлены и проверены по 59 исходным hashes. Public Telegram flow и cutoff/source validation остаются незавершёнными.
- FC18 завершён как `DONE_WITH_GAP`: подтверждённый пригодный возврат связывается со стабильным digest исходной продажи и фиксирует стоимость по точным строкам её последней полной allocation revision. Полный возврат восстановления split sale распределяет по каждому слою; частичный возврат многослойной продажи и open-rate basis блокируются без угадывания. Схема FIFO v6→v7 добавляет append-only таблицу basis; повтор события идемпотентен, replay сверяет provenance, cutoff, исходную allocation и стоимость. Профиль — **131 passed**, compileall и `git diff --check` PASS. Денежные Return COGS gates не менялись; production FIFO по-прежнему ограничен неподтверждённым cutoff.
- FC17 завершён как `DONE_WITH_GAP`, code commit `69f043f8`: production Period Profit подключён к FIFO-источнику только после точного store/SKU cutover, полной актуальной allocation revision, совпадения digest физической продажи и количества. При активном FIFO любая неполнота закрывает расчёт без подмены current cost; остальные SKU сохраняют legacy dated-cost путь. Финансовые начисления Ozon и TaxService не менялись. Связанный профиль — **906 passed in 25.87s**, compileall и `git diff --check` PASS. Физическая дата/общий cutoff и возвратные/несбытовые движения остаются неподтверждёнными; реальные FIFO COGS в отчёте пока недоступны.
- FC16 завершён как `DONE_WITH_GAP`: добавлены чистый хронологический replay и append-only распределения в schema v6. Перед фиксацией репозиторий повторно строит ожидаемый FIFO из сохранённых источников и сравнивает все строки, суммы, cutoff и revisions в атомарной транзакции; source-set/stream/allocation CAS и идемпотентность защищают от устаревшего или переподписанного preview. Связанный профиль: **175 passed in 5.18s**, compileall и `git diff --check` PASS; commit `f6af16d7`. Только synthetic fixtures/временная SQLite. FC02/FC15 дата продажи и общий cutoff всё ещё требуют проверки владельцем; возвраты и несбытовые движения поддерживаются fail-closed и остаются в FC18/FC19.
- FC15 остаётся `DONE_WITH_GAP`: `FifoCostSaleEvidenceNormalizer` формирует стабильный redacted digest по store/posting/подтверждённой offer или product identity и не меняет его при переписанном catalog SKU. FC17 подключил этот ключ к Period Profit, но финансовые даты остаются отдельными; физические продажи не допускаются до подтверждения временных семантик и cutoff-моста.
- FC14 завершён с ограничением источника: schema v4→v5 добавляет append-only сверки количества между ставками; третья и четвёртая ставки проходят без изменения старых конечных слоёв, а противоречия/неполные снимки и неразобранные движения закрываются fail-closed. Связанный профиль: **84 passed in 2.62s**. Production collector пока не доказывает семантику v4 и общий cutoff, поэтому подтверждение новых партий через него остаётся недоступно; факт-отчёт себестоимостью FIFO не обогащается.
- Работа начата в ветке `codex/fifo-cost-implementation-20261106` от точной головы спецификации PR #725 (`b842e4a812334938e5178de8f4ae158d2b36735c`, base `main` `68aa6db09649bdbb4be406d423c6315a8961697b`). Реализационный PR ещё не создан.
- FC00 завершён: обязательные документы прочитаны; исходный полный набор на Windows Python 3.12.10 прошёл **4,442 теста** за 45.02 с. До/после проверки подтвердили побайтовое сохранение 59 файлов локальных данных после возврата тестовых побочных изменений.
- FC01 завершён: карта writer/reader и три подтверждённых рассогласования датированной истории с current-проекцией описаны в `project_brain/FIFO_COST_SOURCE_AUDIT_2026-11-06.md`; изолированные SQLite-пробы воспроизвели их. Runtime-поведение ещё не изменено.
- FC02 завершён с ограничением источника: текущие адаптеры не доказывают общий watermark снимка остатков и физической продажи; официальный Ozon указывает `arrival_date=null` для кросс-докинга. Добавлены матрица доказательств и синтетический сценарий позднего начисления. Пока мост не подтверждён, FIFO-себестоимость в фактическом отчёте должна оставаться недоступной, а не подменяться моделью.
- FC03 завершён: `FIFO_COST_CONTRACTS_2026-11-06.md` и Decision 066 определяют отдельный владелец FIFO-себестоимости в существующей tenant-local SQLite, append-only события/распределения, legacy cutover и fail-closed cutoff. Planning Workspace, финансы, налоги и Return COGS остаются без изменений.
- FC04 завершён: чистый Decimal-аллокатор FIFO обрабатывает конечные старые слои и цену следующей единицы при неизвестном объёме закупки; разбиение продаж, точный базис восстановления возврата и ограничения коллекций покрыты синтетическими регрессиями. Неизвестный cutoff и неполные источники блокируют денежный итог.
- FC05 завершён: current cost и пакетная/одиночная запись выбирают последнюю effective-date версию на текущий день; future switch и поздняя старая запись не подменяют текущую проекцию. Текущая карточка и калькулятор переключают кэш на границе даты без рестарта. Сомнительная legacy provenance блокирует стоимость вместо угадывания.
- FC06 завершён: `FifoCostRepository` создаёт отдельные FIFO-owned таблицы и migration metadata в существующей tenant-local SQLite. Legacy costs, `planning_schema.version` и SQLite `PRAGMA user_version` сохраняются; старые записи не переносятся в FIFO. Повторный запуск, атомарный отказ, append-only guards и owner/store isolation покрыты временными БД.
- FC07 завершён: preview не создаёт событий или стоимости; подтверждение пишет команду/события/слои в одной транзакции с CAS по ревизии и idempotency key. Старые билеты другого SKU или магазина, несовпадающие source fingerprint и конкурентный loser отклоняются без частичной записи. FIFO schema v1 атомарно обновляется до v2.
- FC08 завершён: чистый нормализатор остатков и актов отличает неполные/пустые/нулевые/конфликтующие данные; требует подтверждённое соответствие catalog product→SKU, сверяет SKU-строки с агрегатом акта, не складывает представления одной поставки, учитывает резерв как часть FBO `present` и не назначает дату фактической приёмки по capture/act/status полям. Синтетический профиль: 25 passed. Фактический cutoff по-прежнему заблокирован до подтверждения источников.
- FC09 завершён: добавлен явный read-only сбор остатков и конечный поиск поставки через существующий Ozon client. Общие parent deadline/request budget, фактические попытки, cancellation, single-flight, повторяемый только в пределах TTL checkpoint и fingerprint проверены синтетически; **117 связанных тестов прошли**. Сборщик не активирует FIFO-точку и не снимает `INVENTORY_CUTOFF_UNRECONCILED`.
- FC10 завершён: добавлены read-only preview и atomic commit начальной FIFO-точки из owner-confirmed старых cost layers, explicit FIFO order, раздельных Ozon/transit/home количеств и cutoff. Явный ноль дома сохраняется как обезличенная source reference; транзит и Ozon present включая reserved требуют подтверждений. Идентификаторы и cutoff строго валидируются без частичного fallback; projection получает `FIFO_READY`, но Period Profit cutoff остаётся `INVENTORY_CUTOFF_UNRECONCILED`. Связанный профиль: **113 passed**.
- FC11 завершён: добавлены schema v3 и append-only история новых ставок; подтверждённая себестоимость включает закупку, доставку до владельца и упаковку. Preview не добавляет неизвестное количество новой партии, сохраняет старые конечные FIFO-слои, а остаток старой партии дома хранит только как сверочное owner evidence. Подтверждение ограничено ревизией/владельцем/магазином/SKU и идемпотентно; частичная очередь и незакрытый фактический cutoff остаются явными. Разрешённый нулевой старт требует полного подтверждённого нулевого среза FBO/reserved/transit и ручного нуля дома; фиктивные события/слои не создаются. Ретро-дата до последнего конечного FIFO-слоя или ставки отклоняется. Связанный профиль: **127 passed in 2.79s**; compileall и `git diff --check` PASS. Реальные запросы и бот не запускались.
- FC12 завершён в commit `c75717ad`: добавлен read-only экран FIFO истории и новая ставка по точному SKU в существующем меню себестоимости. Тикеты ограничены пользователем, tenant/store, SKU, ревизией и TTL; ввод ставки валидирует закупку/доставку/упаковку/остаток старой партии, а подтверждение сохраняет ставку атомарно, не добавляя неизвестный объём и не меняя фактическую прибыль. Кнопки позднего ввода и исправления пока сообщают о недоступности без изменений данных. Связанный профиль: **108 passed in 2.91s**; compileall и `git diff --check` PASS.
- FC13 завершён в commit `27cd5798`: schema v4 добавляет append-only evidence актов по точному магазину/SKU с отдельными хешами order/supply/act и раздельными `declared_quantity`, `approved_quantity`, `fact_quantity`. Обновление акта сохраняет новую последовательную версию, повтор того же fingerprint идемпотентен. Документальная дата создания и локальное время сбора не становятся физической датой прихода; evidence не создаёт слой, событие и не меняет FIFO-остаток/ревизию. Связанный профиль: **188 passed in 3.63s**; compileall и `git diff --check` PASS. Следующий этап — FC14; factual cutoff остаётся `INVENTORY_CUTOFF_UNRECONCILED`.
- Реализационный PR ещё не создан; точная code-only контрольная точка FC13 `27cd5798`; полного CI ещё нет. Реальные Ozon/Telegram-запросы, запуск бота, CI и слияние не выполнялись.
- Подробный Resume, таблица FC00–FC35, проверочные SHA и блокеры ведутся в `project_brain/LUNA_FIFO_COST_HISTORY_PROGRESS_2026-11-06.md`.

# 2026-11-06 — следующее задание: FIFO себестоимости

- База: main 68aa6db09649bdbb4be406d423c6315a8961697b после PR #721–#724.
- Подготовлено project_brain/LUNA_FIFO_COST_HISTORY_TASK_2026-11-06.md, статус SPEC_READY: упрощённый FIFO по общему остатку SKU, старая партия отправляется первой, стоимость включает закупку/доставку до владельца/упаковку.
- FC00 завершён (baseline и журнал); FC01–FC35 ещё не завершены. Включены своевременный переход, позднее сообщение с привязкой к поставке, audit/correction revisions, текущая экономика, планы, возвраты и backup/restore.
- FC01 подтвердил и описал несогласованность будущих/ретроспективных записей с mutable current-cost projection; FC05 должен исправить их до включения FIFO. FC02 должен доказать stock/reserve/transit semantics и inventory/finance cutoff. Реализация FIFO и реальная приёмка не заявлены выполненными.

# 2026-11-05 — исправлены замечания повторного review PR #724

- Ценовая сетка сообщает фактические отсутствующие входы для базового сценария и указывает на неподтверждённую комиссию только при соответствующем статусе.
- Подтверждённые дополнительные расходы с нулевым округлённым значением на единицу сохраняют прозрачную расшифровку источника, периода и количества. Неизвестные или неподтверждённые данные по-прежнему не выдаются за учтённые расходы.
- Связанный профиль: **50 passed**; полный Windows pytest: **4,442 passed in 48.14s**; `compileall app tests` и `git diff --check` — PASS. Состояние файлов `data/` после проверки совпало с контрольными SHA-256.

# 2026-11-03 — исправления review PR #724

- Исправлено наследование frozen дополнительных расходов во всех трёх путях сравнения цены. Проверка при применении и строки сравнения теперь используют одни и те же расходы; подтверждённый saved-plan regression проходит сетку без рекламы и применение кандидата.
- Расшифровка смешанных известных/неизвестных расходов использует безопасный общий ярлык. Подтверждённая pre-ad база/период остаётся видимой при `extended_calculation=UNAVAILABLE`, если pre-ad ledger доказывает включение суммы.
- Предупреждение сетки больше не обозначает хранение и эффекты возвратов как безусловно исключённые. Подробности показывают подписанное диагностическое расхождение налогового моста при копеечном округлении.
- Проверки локально: полный Windows pytest **4,440 passed in 45.83s**; `compileall app tests` и `git diff --check` PASS. Все файлы `data/` после полного pytest восстановлены к байтам снимка до запуска. GitHub Actions run [41650041563](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/41650041563) для SHA `336c890cca98e547d869d0a52869b65ba21a90c7` прошёл: Windows/Linux full verification, production Docker build и smoke — success.

# 2026-11-03 — PR #724: уточнены категории распределённых расходов и округление

- Краткий и подробный сценарии теперь раскрывают тип подтверждённых дополнительных расходов, числитель, период и основание распределения (`заказанные`, `проданные` или `сохранённые единицы когорты`). Для сохранённого источника хранения выводится категория хранения вместо общих «прочих расходов».
- Форматтер денег планового калькулятора приведён к каноническому `ROUND_HALF_UP`; копеечная корректировка имеет явный знак, поэтому введённая себестоимость и сумма строк расходов читаются согласованно.
- Связанный профиль: **128 passed in 3.33s**; полный локальный Windows pytest: **4,437 passed in 45.27s**; `compileall app tests`, `git diff --check` PASS. В финальном тестовом прогоне содержимое `data/tasks.json` и исходное состояние lock восстановлены байт-в-байт к снимку непосредственно перед этим прогоном. Code SHA `a5f34dec102b4d3894138fc223f6cda92a7841b7` прошёл exact-head Verify run `41636324358`: Windows/Linux full verification, Docker build и smoke — success; artifact `13230647048` (`sha256:b12f3f804260e83e1c8339ba6f5280bffbc918e885c40edbe6c0a11a98af8b31`).

# 2026-11-03 — PR #724: согласованы детализация расходов и проценты

- Исправлены два новых review замечания: результат плановой цены перечисляет дополнительные расходы, фактически включённые в pre-ad прибыль, и динамически показывает неизвестные/исключённые категории из frozen scope; строгие возвратные потери больше не попадают под общую фразу «возвраты не включены».
- Дублирующая строка прибыли в карточке SKU не выводит `-0.0%`, если отрицательная сумма округляется до нулевого процента; знак суммы прибыли сохраняется.
- Регрессии в saved-plan Telegram flow, сценарном runtime и current economics. Полный локальный Windows pytest: **4,436 passed in 46.06s**; `compileall app tests`, `git diff --check` PASS. Code SHA `e1ac109f79368a9d71945b5c88ccbfa84f49ee9e` прошёл exact-head Verify run `41609310492`: оба job success, Linux/full verification и Docker build/smoke PASS; artifact `13218262009` (`sha256:6f316a6ff1560144cce87df32dd5259f38a6cd6e7e47a6aafa12f6f7a27bef73`). Владелец данных после тестов восстановлен к SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; lock отсутствует.

# 2026-11-03 — PR #724: результат callback и проценты маржи

- После ошибки отправки начального progress-сообщения callback-результат проходит общий Telegram splitter; длинное подтверждение больше не теряется из-за лимита одного сообщения.
- Отрицательная прибыль до рекламы меньше 0.005 ₽ по модулю отображается с её денежным знаком, а округлённый до нуля процент показывается как `0.00%`. Ненулевые отрицательные проценты сохраняют знак.
- Регрессии проверяют Telegram callback без progress handle и current/historical проекции. Полный локальный Windows pytest: **4,436 passed in 46.73s**; компиляция и whitespace-проверка PASS. Кодовый SHA `0d426b9c35e3ef728168ee3b6ca913d6e7a0f239` прошёл exact-head GitHub Actions Verify `41599892104`: Windows **4,436 passed in 131.20s**, Linux **4,436 passed in 27.06s**, Docker build/smoke PASS; artifact `13213338415` (`sha256:0caf20fb6ceea592c56bfbcea9541119c0e742b400170377dd044499bd825575`). `data/tasks.json` восстановлен к baseline SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`, lock отсутствует.

# 2026-11-02 — PR #724: устранены два замечания повторного review

- Большой предпросмотр sales mix больше не теряет финансовую сводку из-за лимита 3 800 символов: сводка и scope-предупреждения выводятся раньше детализации, полное сообщение разбивается общим Telegram-механизмом.
- В процентах маржи округлённый отрицательный ноль отображается как `0.00%`; фактическая прибыль `-0.01 ₽` остаётся отрицательной.
- Полный локальный Windows pytest: **4,433 passed in 46.77s**; компиляция и `git diff --check` проходят. Тестовые изменения `data/tasks.json` восстановлены: SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; lock удалён. Кодовый SHA `2557d68a5a9160d6f6c51d330b35d231cd7dc2b6` прошёл exact-head Verify `41455445557`: Windows **4,433 passed in 139.83s**, full-verification и Docker build/smoke PASS; artifact `13145429548`, digest `sha256:fffbf5ecd5441d75d796b209991c623ea45b3ea7cb51e478473421f15de9eb01`.

# 2026-11-02 — PR #724: категории фиксированных расходов видны в сравнении планов

- Сравнение сохранённых планов агрегирует расходы по паре «название + категория». Перенос одинаковой суммы между `OTHER` и `ADVERTISING` отражается двумя направленными строками; Telegram показывает русское название категории, JSON/CSV сохраняют её в `expense_changes`.
- Расходы старых планов без категории трактуются как `UNCLASSIFIED`, чтобы прежние frozen-снимки сохраняли прежний смысл.
- Связанный профиль из пяти модулей: **98 passed in 3.42s**; полный локальный Windows pytest: **4,431 passed in 45.75s**. Exact-head Verify run `41448897286` на code SHA `cc7c6e7cbf6c36bc025a2f400e6c65bc10c523d3` прошёл: Windows/Linux по **4,431 passed**, Docker build/smoke PASS; artifact `13143113848`, digest `sha256:16956bbb86da648049eacefd4c718bc72382cb27dd4e9dd8bd71dfd69807922b`. Тестовые побочные изменения восстановлены: `data/tasks.json` SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`, lock отсутствует. Новый документальный commit требует exact-head CI.

# 2026-11-02 — PR #724: исправлено сохранение категорий периодных расходов

- Репозиторий планов принимает типизированные расходы `ADVERTISING`, `OTHER`, `UNCLASSIFIED`, сохраняя строгий allowlist. Старые расходы без категории сохраняют прежний формат.
- Новый Telegram regression проходит preview, подтверждение, revision 2, повторное чтение, перерасчёт и JSON export; отдельный repository test проверяет round-trip и отклонение неразрешённых значений.
- Связанные тесты: **97 passed in 3.38s**; полный Windows pytest: **4,430 passed in 46.42s**. После теста `data/tasks.json` восстановлен к baseline SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`, lock отсутствует. Code SHA `f7a0207129746278365365a8f28a9dcf909e1fd6` прошёл exact-head run `41442747525`: Windows/Linux по **4,430 passed**, Docker build/smoke PASS; artifact `13139189114`, digest `sha256:d27d89f22acb2a56df735541e7662a4656c466e9a903cae95ebe24e5c6a864a5`.

# 2026-11-02 — PR #724: два новых P2 review замечания исправлены локально

- В sales mix введена явная категория дополнительных расходов. Категория «Реклама» вычитается из after-ad итога, но не из pre-ad; «Прочее» учитывается и в pre-ad; старые вводы без категории сохраняют after-ad поведение и делают pre-ad расходную полноту частичной.
- Результат сравнения цен разбит на страницы по 4 варианта; кнопки выбора ограничены видимыми строками. Для сетки цен оставлено прежнее отображение 10 точек на страницу.
- Добавлены service-level и Telegram end-to-end регрессии. Связанные модули: **349 passed in 8.53s**; полный локальный Windows suite: **4,429 passed in 44.13s**; `compileall` и `git diff --check` PASS. Тестовые побочные изменения `data/tasks.json` восстановлены к SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; lock отсутствует. Кодовый SHA `b393c1765b26294293c9c22a87b1657260027ce5` прошёл run `41437642412`: Windows/Linux по **4,429 passed**, Docker build и smoke PASS; artifact `13137521134`, digest `sha256:f7903c823ac8861d4452e96646ec291ebdb75f2ac6600a3bfc59d3ae8ae0340d`.

# 2026-11-02 — PR #724: исправлены два P2 замечания review

- В сравнении вариантов цены и строке базовой цены сохраняются прибыль и маржа до рекламы, когда неизвестна реклама. After-ad остаётся недоступной, варианты не ранжируются, реклама не подменяется нулём; известная комиссия не объявляется неподтверждённой.
- Строгая подтверждённая потеря возвратной когорты не отражается одновременно включённой и исключённой. Неизвестный статус и конфликт mapped-алиасов сохраняют частичную полноту.
- Связанный профиль: **304 passed in 6.29s**; полный Windows pytest: **4,426 passed in 46.21s**. `compileall app tests` и `git diff --check` PASS. Контрольная сумма пользовательских данных совпадает с baseline `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`, lock отсутствует. Exact-head run `41431891843` на SHA `f248237f646a39f141b993d4dc498d3eec039278` прошёл: Windows/Linux по **4,426 passed**, Docker build/smoke PASS; artifact `13133939194` (`sha256:66889d7a950792c334004978dae7380f8b1db7246159a9e13fa2311e15b755a4`).

# 2026-11-02 — PR #724: устранено противоречие статусов базовых расходов

- Статусы `EXCLUDED`/`UNKNOWN` из расширенного источника не перекрывают категорию, уже содержащую известную базовую сумму модели. Ранее логистика одновременно оставалась известной и попадала в исключённые/неизвестные; в sales mix сумма вычиталась, но подписывалась как неизвестная.
- Новые регрессии покрывают `calculate`, `calculate_components_only` и sales mix. Связанный профиль: **165 passed**; полный Windows pytest: **4,424 passed**; `compileall` и `git diff --check` PASS.
- Пользовательские данные не изменены: SHA-1 `data/tasks.json` совпадает с исходным `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`, lock отсутствует. Exact-head GitHub Actions run `41416052784` на кодовом SHA `372e921c3b4a6c07504754702abd49699efdcf3a` завершился success: Windows **4,424 passed in 146.47s**, Linux **4,424 passed in 29.42s**, Docker build и smoke — PASS. Проверяемый merge ref `3ab500ee038e0d9d1c51d95edf4d86e992bfc558`; artifact `13127109252`, digest `sha256:3dfef7873205c793ca47fcdb7afc8ee54f2663ef843d69a9ae52227958acc2f8`.

# 2026-11-01 — PR #724: граница сохранённой детализации расходов

- Валидатор frozen `pre_ad_margin.expense_scope` учитывает, что проекция дополняет до 64 source components базовыми и производными ключами. Производные списки и причины ограничены 72 элементами; проверки структуры, идентификаторов и дубликатов сохранены.
- Новый end-to-end тест сохраняет и повторно читает планы с 60/64 включёнными компонентами и 64 исключёнными типами; проверено отклонение 73-го ключа.
- Linked profile: **163 passed in 4.43s**. Full Windows pytest: **4,422 passed in 47.55s**. `compileall app tests` и `git diff --check` PASS. `data/tasks.json` вернулся к SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; `data/tasks.json.lock` отсутствует.
- Кодовый SHA `7de3598cdc0d07fd41bfce738fc3e7ef3edf466d` прошёл exact-head run `41343413057`: Windows и Linux по **4,422 passed**, Docker build/smoke — PASS; artifact `13098127220` (`sha256:ba829ba86632fcf8fe644ab7068e9e4f467ca88b4fd0f0f2f67e99b288ff05f9`).

# 2026-11-01 — PR #724: устранены три повторные review-находки

- Сверена детализация `pre_ad_margin`: округлённые строки расходов с отдельной подписанной корректировкой теперь точно сходятся с канонической прибылью, в том числе при умножении на объём продаж. Основная формула прибыли не менялась.
- Ноль STORAGE/PLACEMENT подтверждается только суммой всей категории после свёртки алиасов; смесь положительного и нулевого алиаса не маркируется как нулевая.
- В sales mix категория, явно исключённая для одного SKU и включённая для другого, обозначается как частично покрытая, без глобального статуса «исключена».
- Добавлены регрессии на scenario/component paths, микс и пользовательскую расшифровку. Linked profile на финальном коде: **158 passed in 4.21s**; full Windows pytest: **4,420 passed in 46.19s**; `compileall app tests` и `git diff --check` PASS. `data/tasks.json` SHA-1 восстановлен к `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; lock отсутствует.
- Коммит `18ba381b663370aa6a78264bba012c24c8c073ad` опубликован в PR #724 и прошёл exact-head run `41338557148`: Windows/Linux full suites и Docker build/smoke — success. Artifact `13096362251`, digest `sha256:1a82c63bb909d4bfe71151142526811db5037b1eaf6c6ce2bcf0468511a942f5`. Независимый повторный review ещё предстоит; слияние, развёртывание и запуск бота не выполнялись.

# 2026-11-01 — PR #724: следующий проход review

- Исправлены дополнительные review-находки: SKU/состояние калькулятора переживают переход из деталей; frozen before-ad/tax projections остаются в сохранённых single/batch планах и JSON-экспорте; sales mix сохраняет известный subtotal при UNKNOWN рекламе и не поднимает локальный confirmed-zero в общий ноль.
- OrderedDict-кэши деталей и одноразовых действий защищены общей блокировкой от конкурентной очистки, вставки и вытеснения.
- Связанный профиль: **290 passed**; полный Windows pytest: **4,416 passed in 46.01s**; `compileall app tests` и `git diff --check` PASS. Тестовый побочный эффект в `data/tasks.json` восстановлен, SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`, lock отсутствует.
- Коммит опубликован в PR #724. SHA `fe7cb4e15dd14aaef2348c34e84c2268f8cef507` прошёл exact-head GitHub Actions run `41332959642`: Windows и Linux/Docker — success; artifact `13093764467`, digest `sha256:8bc42ef332a4c3e45bc93d8959378af2edf9e5694778bdc18576e8d2fccbd0c2`. Нужен повторный независимый review. Слияние/развёртывание/запуск бота не выполнялись.

# 2026-11-01 — PR #724: исправления review R1–R5

- Исправлены пять замечаний review: одноразовая кнопка себестоимости связана с теми же пользователем/магазином/SKU; возврат после записи себестоимости принудительно перечитывает юнит-экономику; явный refresh обходит кэш запроса.
- Чувствительность, пакетный расчёт и sales mix показывают доступную маржу до рекламы при неизвестной рекламе. При неизвестных прочих расходах результат обозначен как частичный, суммы не считаются нулевыми; агрегат и выгрузка сохраняют scope расходов.
- Детали ценового сценария показывают налог без рекламы T0, налог после рекламы T1 и разницу, если оба расчёта доступны. Неизвестный T1 подписан как «не рассчитан».
- Связанный профиль **208 passed**; локальный полный Windows pytest **4,411 passed in 45.99s**; `compileall app tests` и `git diff --check` прошли. После локальной проверки `data/tasks.json` восстановлен к исходному SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`, lock удалён.
- PR #724 code head `2e82355d1b0353be0ea3eeb4ed722bba0ac9e498` прошёл GitHub Actions run `41328828173`: Windows **4,411 passed**, Linux **4,411 passed**, Docker build и runtime smoke — PASS. Проверенный merge ref: `142e97a80ce08caf047a1b52701bf1c5333ea1d9`; SHA-bound artifact ID `13092810821`, digest `sha256:e9d661a1f64b050fef668e91e7eb61d821c46adc1d64cc4b7e610a17a68df184`. Слияние, развёртывание и запуск бота не выполнялись.

# 2026-10-31 — Реализация: маржа товара до рекламы (MA00–MA29; review remediation complete)

- Реализация этапов MA00–MA28 завершена локально. Основной показатель: после налога и подтверждённых расходов, ₽/успешную единицу и %, denominator — цена продавца до баллов. Добавлены before/after для сценариев, current projection и строгая historical reconciliation; неподтверждённые расходы остаются неизвестными, старые результаты не меняются.
- MA27 полный Windows pytest: **4,404 passed in 46.19s**; `compileall app tests` и `git diff --check` PASS на `eb14db29`. MA28 обновил инструкцию с точными меню, налоговыми основаниями и N01 числовым примером. Проверка владельцем на live-данных помечена `USER_VALIDATION_PENDING`.
- MA29: открыт stacked PR #724 на ветку ТЗ PR #723; independent review packet приложен. Run `41240191495` прошёл обе проверки Windows и full-verification (Linux + Docker) на SHA `fd4d79ed`; создан SHA-bound отчёт. Любой последующий head нуждается в своей exact-head проверке. Merge/deploy/live Ozon/Telegram запросы и запуск бота не выполняются.

- Владелец подтвердил основной показатель после налога и прочих учитываемых расходов, от выручки продавца до вычета баллов. ТЗ `LUNA_PRE_AD_MARGIN_TASK_2026-10-31.md` включает 30 этапов MA00–MA29; MA00–MA06 завершены, MA07 VERIFIED_EXISTING, MA08–MA10 DONE, MA11 VERIFIED_EXISTING.
- Добавлены canonical no-ad ветка и T0/T1 bridge; current provider/query предоставляют аддитивную `pre_ad_margin` v1, используя существующие текущие сумму прибыли и налога без повторного вызова налогового расчёта. Состав неполных расходов, неизвестная реклама и разные периоды указаны явно; legacy поля и guards сохранены.
- MA11 подтверждён в существующем плановом сценарии: точный кандидат получает свой тариф, тариф прежней цены не переносится за границу неизвестного диапазона; ручная ставка явно остаётся допущением. Новые регрессии проверяют проекцию и сохранение цены/себестоимости/рекламы после ручной комиссии. Связанный Windows профиль MA11: **61 passed in 1.53s**.
- MA19 прошёл публичную offline-приёмку: текущая карточка → подробности → сценарий новой цены → ручная комиссия → реклама → before/after → сохранение плана. Исправлены потеря токена при открытии локальных подробностей и сериализация decimal-comma. Linked Windows profile: **121 passed in 3.60s**; implementation commit `d8532f9a`.
- MA20 подтверждён на существующем frozen-plan/schema поведении: старые планы открываются без source reload, тарифные изменения после явного refresh сохраняются новой revision, future/corrupt схемы fail-closed. Новая регрессия подтверждает отсутствие изменений документа/revision/payload при чтении. Linked Windows profile: **51 passed in 2.35s**; test commit `2423742b`.
- MA21 verified existing CSV/JSON export path: the exported sensitivity row carries the same before-ad projection, revenue/tax basis, expense completeness, source periods, advertising/tax fields and one-successful-unit basis as the displayed snapshot. Export remains source-read-free. Linked Windows profile: **48 passed in 1.54s**; regression commit `7c4f6595`.
- MA22 verified existing owner/store/revision guards: equal SKU values across stores do not share callbacks; stale price/apply callbacks fail closed after store/SKU/source changes; saved tariff revisions remain frozen until explicit refresh; simultaneous revision-CAS writes have one winner. Linked Windows profile: **130 passed in 4.05s**; no production change.
- MA23 verified local-only details/export, tenant-scoped query cache and in-flight dedup, shared time/HTTP attempt budgets with cooperative cancellation, and honest unavailable/partial results. Linked Windows profile: **141 passed in 4.50s**; no production change.
- MA24 extended isolated backup/restore acceptance: old/new saved-plan revisions, observation history and exports survive archive verification, dry-run and restore to a fresh root/repository; another store stays isolated and rejected raw payload is absent. Linked Windows profile: **26 passed in 3.36s**; test commit `6b06eb43`.
- MA25 added fixed numeric regressions for absolute advertising, no-tax mode, exact TaxService invocation bases and corrected SKU cross-docking (560 ₽ / 280 accepted = 2 ₽/unit). Existing tests map all N01–N20 accounting, ownership, completeness, tariff, history, persistence and tenant cases. Linked Windows profile: **388 passed in 6.73s across 14 modules** at test commit `fcec0254`; no production/schema changes.
- MA26 linked offline profile spans the current/historical card, price planning, tariffs, saved plans, returns/expenses/cross-docking, observations/experiments, exports and restore: **981 passed in 28.81s across 70 modules** at test commit `8cdb62c1`. Corrected one obsolete formatting assertion to match the current provenance contract; no production change.
- MA12 добавил отдельный historical projection service с add-back только exact-SKU финансовой рекламы, уже учтённой в net, при точном совпадении владельца, магазина, SKU и периода. Налог берётся из результата существующего исторического запроса без повторного пересчёта; provenance отмечен отдельно. CPC Performance, cohort attribution, account/window allocation, неполные категории и net credit не подставляются.
- В текущем production historical source такого полного evidence пока нет: новая historical проекция возвращает `UNAVAILABLE` с конкретной причиной. Это не меняет существующие поля или current/model path. Resolver дополнен exact-SKU coverage flag.
- Связанный MA12 Windows профиль: **156 passed in 2.83s** на 9 модулях; `data/tasks.json` SHA-1 совпадает до/после. `py_compile`/полный pytest и exact-head CI ещё предстоят; merge, deploy, live API и запуск бота не выполнялись.
- MA13 расширил существующие price options/grid аддитивными `pre_ad_margin` и `after_ad` per candidate. Стандартный ranking остаётся по after-ad прибыли ₽/успешную единицу; для сетки добавлен отдельный no-ad режим с отдельным basis, который при выборе цены сохраняет существующий ad override. Tax/revenue/denominator bases фиксируются для сравнения; неполные non-ad расходы остаются помеченными.
- Linked Windows profile MA13: **255 passed in 5.89s** на 9 модулях. `data/tasks.json` SHA-1 до/после: `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; lock absent. Полный pytest и exact-head CI остаются MA27; no merge/deploy/live calls/bot launch.
- MA14 exposes the same candidate `pre_ad_margin` in target, sensitivity, batch, and their exports without extra source reads or solver evaluations. Sales mix now computes the exact no-ad tax at aggregate level in the same single public TaxService call, keeps the existing after-ad mix unchanged, and uses total pre-ad after-tax profit divided by total seller revenue. Unknown/incomplete mixes fail closed; zero revenue has no percentage.
- Linked Windows MA14 profile: **261 passed in 5.34s** on 9 modules; `py_compile`/`git diff --check` pass; `data/tasks.json` hash remains `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`, lock absent. Full pytest and exact-head CI remain MA27. No merge/deploy/live calls/bot launch.
- MA15 обновил основной current/historical formatter: маржа до рекламы после налога стоит перед прежней детализацией; рядом выводятся налоговое основание, completeness, статус рекламы и безопасные source periods. После-рекламная прибыль выводится только для exact-SKU рекламы, доказанной как уже включённая в тот же historical net. При unknown ad значение остаётся недоступным; legacy after-ad fields не заменены и не пересчитаны.
- Linked Windows MA15 profile: **42 passed in 1.07s** на 4 модулях; `py_compile`/`git diff --check` PASS; `data/tasks.json` hash сохранён, lock отсутствует. Exact-head CI и полный pytest предусмотрены MA27; merge/deploy/live API и запуск бота не выполнялись.
- MA16 добавил кнопку «Из чего складывается» к основной карточке. Она открывает ограниченный по времени user-scoped снимок точного результата, не повторяя Ozon query. Ledger показывает текущие расходы на одну успешную единицу или исторические totals и denominator, источник/период, налог и полноту; кросс-докинг помечен как вложенная детализация. Current bridge проверяется до копейки; historical other-expense balance явно остаётся расчётным, ad bridge independently сверяется с after-ad result.
- Linked Windows MA16 profile: **44 passed in 1.12s** на 4 модулях; `py_compile`/`git diff --check` PASS; `data/tasks.json` SHA-1 совпадает, lock absent. Профиль включал исправление тестом найденного string-to-money formatting дефекта crossdock breakdown. Exact-head CI и полный pytest остаются MA27; merge/deploy/live calls/bot launch не выполнялись.
- MA17 добавил отдельные действия только там, где есть поддерживаемый путь: заполнение себестоимости конкретного SKU, плановая цена для ручного тарифа/рекламного допущения и явный повтор расчёта. После себестоимости возврат к тому же SKU одноразовый, привязан к пользователю и магазину; повторный query происходит лишь после нажатия. Неподдерживаемые расходы названы по категориям и остаются unknown, не нулём.
- Linked Windows MA17 profile: **98 passed in 1.95s** на 6 связанных модулях. `py_compile` и `git diff --check` PASS; `data/tasks.json` SHA-1 остаётся `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`, lock отсутствует. Полный pytest и exact-head CI остаются MA27; merge/deploy/live requests/bot launch не выполнялись.

# MA18: сохранённые результаты экспериментов явно помечают окно/срез и число связанных snapshot-ссылок, скрывая их ID; если tax basis результата не сохранён, он остаётся unknown. Frozen-план показывает сохранённый режим/ставку и отсутствие сохранённого происхождения настройки. Новая маржа до рекламы не подменяет старые оценки; ranking, схема хранения и W42–W44 guards не менялись. Связанный профиль: 113 passed in 4.23s; `py_compile`/`git diff --check` PASS; owner data unchanged.

# 2026-10-31 — W44: исключение устаревших цен из рейтинга

- При построении общего рейтинга runtime теперь повторно сверяет свежесть каждого сохранённого сравнения с последними коллекциями, состояниями фаз и control-event revisions. Любая неподтверждённая актуальность исключает вариант из ранжирования; карточка отдельно сообщает количество таких вариантов.
- Regression на двух кандидатах подтверждает, что устаревший кандидат с большей прибылью не определяет максимум. Профиль **118 passed in 6.96s**, полный Windows pytest **4,353 passed in 44.54s**; `compileall` и `git diff --check` прошли. Тестовые данные восстановлены.
- Исправление опубликовано в PR #722 кодовым коммитом `dbb81964`; exact-head Windows и full-verification CI прошли в runs `41208206231` и `41208202051`.

# 2026-10-31 — W43: повторно открытые устаревшие сравнения

- Telegram result view проверяет актуальность phase-state revisions и event revisions обеих фаз, а также latest collection IDs. Старая запись из истории после нового CONTROL_UPDATE помечается устаревшей и не предлагает KEEP/SELECT.
- Регрессия проходит через обычные кнопки `phase_results` → `result`; старая owner-decision кнопка также отклоняется.
- Профиль экспериментов и Telegram: **117 passed in 7.28s**; полный Windows pytest: **4,352 passed in 43.81s**; `compileall` и `git diff --check` прошли. Exact-head Windows и full-verification CI прошли на кодовом коммите `48cc6709342e689b950dc0ba461b177963e7b4c9` (run `41200852297`). `data/tasks.json` восстановлен, созданный lock удалён.

# 2026-10-31 — W42: исправления повторного review PR #722

- Устаревшая кнопка выбора цены больше не принимает решение после изменения контрольных условий. Telegram callback содержит expected experiment revision; репозиторий в одной транзакции проверяет latest result, phase state revisions, control-event revisions и latest collection hashes.
- Порог успешных продаж синхронизирован: зрелость не возвращает READY до достижения 30 проданных единиц, а сравнение использует ту же константу. При меньшей выборке сравнение/завершение не допускаются.
- Добавлены регрессии в Telegram lifecycle, owner-decision repository и phase readiness.
- Связанный Windows профиль: **117 passed in 7.15s**; полный Windows `pytest`: **4,352 passed in 46.30s**; `compileall` и `git diff --check` PASS. `data/tasks.json` восстановлен, созданный `data/tasks.json.lock` удалён.
- Изменения локальные на ветке PR #722; публикация и exact-head CI ещё не выполнены. Классификация: **Architecture Review Required** из-за усиления атомарного repository guard.
- Подробности: `UNIT_ECONOMICS_W42_REVIEW_REMEDIATION_2026-10-31.md`.

# 2026-10-30 — W41: исправления повторного review PR #722

- Зрелость модели привязана к `collected_at` локальной дате evidence; неизменённый старый снимок не становится зрелым от ожидания. Для учёта поздних фактов требуется новая коллекция.
- У незапущенной фазы доступны восстановление явного подтверждения после перезапуска и двухшаговая отмена. Старая кнопка Finish не может завершить фазу по более новой ревизии результата.
- Завершённая фаза принимает ограниченную append-only коллекцию поздних начислений/возвратов. Состояние фазы сохраняется FINISHED, экспериментная ревизия повышается, прежние comparison/owner decisions отклоняются как устаревшие до нового сравнения.
- Окно с хотя бы одним неполным днём больше не объявляет отдельный компонент COMPLETE и не применяет его частичную ставку.
- Связанный Windows профиль: **113 passed**; полный `pytest`: **4,351 passed in 44.59s**. `data/tasks.json` восстановлен после ожидаемого побочного эффекта legacy-тестов; `data/` чистый. Exact-head Windows/full-verification CI на `b0ad8f392630bd39ab40e75d5bbaae8969db417d` прошёл (runs `41063476652`, `41063468992`; Docker build/smoke включены). Независимое повторное review ожидается; merge/deploy/live Ozon/Telegram не выполнялись.
- Детали: `UNIT_ECONOMICS_W41_REVIEW_REMEDIATION_2026-10-30.md`.

# 2026-10-30 — Review-remediation для W39

- Исправлены пять подтверждённых замечаний независимого review PR #722: полный source coverage обязателен для COMPLETE; история контрольных событий читается постранично по 10 с общим пределом; результат сохраняет режим абсолютной рекламы; первый запуск умеет запросить 56-дневный reference snapshot; Telegram предоставляет пользовательские действия для всего цикла фаз и решения.
- Windows linked profile: **127 passed in 6.60s**. Полный Windows `pytest`: **4,346 passed in 42.30s**. `git diff --check` PASS; `git diff -- data` пустой после очистки временного test lock.
- Исправления опубликованы в PR #722 коммитом `3dd56343ac29339e83d5fbcb4f8d563010876384`. Exact-head CI успешен: Windows и full verification (включая Docker build/smoke) в runs `41051047996` и `41051054590`. Независимое повторное review и реальная приёмка владельцем остаются pending; merge/deploy/live Ozon/API/bot не выполнялись.

# 2026-10-30 — W39: review handoff и зелёный CI

- PR #722 открыт поверх спецификации PR #721; пакет независимого архитектурного review: `UNIT_ECONOMICS_W39_INDEPENDENT_REVIEW_HANDOFF_2026-10-30.md`. Exact HEAD `b1b81592199348df40cdb6133b464f59fbe0768e` прошёл Windows/Linux/Docker Verify: [run 40956765471](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/40956765471). Текущую голову PR и Checks проверять live в GitHub.
- W38: disposable Windows full pytest **4,335 passed in 50.37s** на кодовом SHA `428e80cb9a3ada56af1b9aa21280f52d3dec3d64`; `compileall` PASS. Legacy `data/tasks.json` diff/lock остались только во временной копии, checkout владельца не затронут.
- W31 source-collection и candidate-phase инженерные блокеры закрыты в W40; оба пути покрыты синтетической сквозной проверкой. Реальная owner validation pending.
- Architecture Review Required (127 files; +26,257/−247). Merge, deploy, live Ozon requests and real bot launch were not performed.

- Disposable Windows full pytest: **4,335 passed in 50.37s** на `428e80cb9a3ada56af1b9aa21280f52d3dec3d64`; `compileall` PASS. Финальный запуск использовал CI-переменные и IANA timezone database, без storage-root override.
- Legacy suite изменила `data/tasks.json` и lock только внутри временного checkout; основной checkout остался чистым, `data/` не изменился. Exact-head GitHub Verify документирован в W39 handoff.
- W31 source acquisition и candidate-phase UX остаются открытыми ограничениями; synthetic acceptance не считается live owner validation.

# 2026-10-29 — W37: backup/restore acceptance

- A new synthetic test restores plan/cost inputs, expense snapshot, tariff, experiment, phase, collection/result and event history into a new root, then reopens them with a new repository instance. Restore schema version is current; another store sees none of the restored records.
- Corrupt/future experiment and phase payload versions fail closed. Linked backup/migration profile: **46 passed in 2.94s**. Backup/restore implementation and real `data/` were untouched. Evidence: `UNIT_ECONOMICS_W37_BACKUP_RESTORE_ACCEPTANCE_2026-10-29.md`.
- W31 first-run reference snapshot acquisition and Telegram candidate-phase setup remain owner-visible blockers.

# 2026-10-29 — W36: конкурентность и ограниченные ресурсы

- W36 added four deterministic regressions: competing baseline confirmation, competing phase collection, draft edit vs archive, and a 64-event fixed-seed finite soak. Exactly one concurrent writer wins each CAS; append-only history stays consistent and paginates within the 10-row limit.
- Linked W36 profile: **64 passed in 4.36s**; isolated concurrency/soak tests: **4 passed in 0.99s**. Existing linked cases cover cancellation, rollback, shared request/time budgets, quotas, privacy and oversized responses. No production code or `data/` changed. Evidence: `UNIT_ECONOMICS_W36_CONCURRENCY_RESOURCE_ACCEPTANCE_2026-10-29.md`.
- W31 first-run reference snapshot acquisition and Telegram candidate-phase setup remain owner-visible blockers; synthetic tests do not claim full live readiness.

# 2026-10-29 — W35: числовая приёмка сквозных маршрутов

- W35 linked Windows profile: **667 passed in 16.53s** across 47 test modules, covering N01–N18, price/expense consumers, experiment revisions, migrations, exports and public Telegram routes.
- New assertions confirm modeled profit 36.00 ₽ at price 100 ₽ and 33.60 ₽ at price 95 ₽ in the synthetic Q30 route; these are estimates from frozen assumptions, not observed store profit. Incomplete returns recover in a new READY revision, prior finance result remains immutable, one posting with 3 units stays `posting_count=1/units=3`, and a failed collection transaction writes no partial history.
- Two old repository tests expected schema version 10 although the current migration version is 12; assertions now use the repository’s declared version. Production behavior was not changed by W35.
- W31 first-run source snapshot acquisition and Telegram candidate-phase setup remain owner-visible blockers; no live API/bot was used. Evidence: `UNIT_ECONOMICS_W35_CROSS_ROUTE_NUMERICAL_ACCEPTANCE_2026-10-29.md`.

# 2026-10-29 — W34: инструкция владельца и офлайн-приёмка

- Добавлено руководство с точными существующими Telegram кнопками, поведением при missing/partial/corrected source и воспроизводимым offline synthetic test. Оно честно показывает, что реальный первый запуск блокируют отсутствие автоматического 56-дневного источника и отсутствие Telegram шага candidate-фазы.
- Offline one-SKU case: **3 passed in 0.45s**. В изолированной Windows среде потребовалось явно указать уже установленную IANA timezone database; реальная Ozon/Telegram приёмка и передача ключей не нужны. См. `UNIT_ECONOMICS_W34_OWNER_GUIDE_ACCEPTANCE_2026-10-29.md`.

# 2026-10-29 — W33: экспорт истории ценового эксперимента

- Telegram карточка сохранённого эксперимента теперь предлагает JSON/CSV со всеми имеющимися в квотах версиями, фазами, сбором, результатами/сравнениями и решениями. Экспорт tenant/store scoped, не раскрывает прямые идентификаторы, сохраняет content hashes/revisions, не читает Ozon и не пересчитывает экономику.
- Изолированный профиль: **113 passed in 4.47s**; общий export/document профиль: **17 passed in 0.96s**; `py_compile` и `git diff --check` PASS, `git diff -- data` пусто. См. `UNIT_ECONOMICS_W33_TELEGRAM_HISTORY_EXPORT_2026-10-29.md`.
- W31 остаётся заблокирован для первого пользовательского запуска до подключения приложения к сбору полного 56-дневного reference snapshot.

# 2026-10-29 — W32: история и результаты экспериментов в Telegram

- В меню экспериментов доступны сохранённые записи; карточки показывают phase/result revisions и дают открыть точный frozen-plan/snapshot view без загрузки источников. Истории ограничены пагинацией по 10 записей.
- Экран результата использует существующий recommendation service: объясняет исход и причины quality gates, не заявляет причинность и не меняет цену. Из активной фазы можно перейти к уже созданному наблюдению цены; повторное чтение карточки показывает поздние локальные результаты.
- После перезапуска меню восстанавливает историю из Planning Workspace; старые memory-only callbacks безопасно отклоняются. Windows isolated W32 profile: **24 passed**; linked W31/W32 profile: **111 passed in 4.43s**; `py_compile`/diff-check pass, data diff empty. См. `UNIT_ECONOMICS_W32_TELEGRAM_EXPERIMENT_HISTORY_2026-10-29.md`.
- W31 остаётся BLOCKED для обычного первого запуска: приложение ещё не создаёт полный 56-дневный reference snapshot через пользовательский flow. Эксперименты не создаются с неизвестными источниками. Следующий независимый этап — W33, связать сохранённые снимки/результаты с экспортом.

# 2026-10-29 — W31: мастер ценового эксперимента в Telegram (условная готовность)

- Новый experiment Telegram runtime подключён к текущему unit-economics меню и общему tenant-scoped Planning Workspace. При наличии точного полного 56-дневного снимка можно пройти пользовательское подтверждение baseline до BASELINE_ACTIVE; цены вводятся обычным текстом, история цены Ozon не заявляется.
- Проверки: 96 passed in 3.72s, py_compile PASS, git diff --check PASS, git diff -- data пустой; synthetic data only.
- Блокер полноценного W31: приложение не создаёт такой reference snapshot из доступных API внутри Telegram. Для обычного пользователя flow пока остановится с явным REFERENCE_SNAPSHOT_REQUIRED. Неполнота не маскируется нулём/полнотой. См. UNIT_ECONOMICS_W31_GUIDED_EXPERIMENT_WIZARD_2026-10-29.md.
- Независимо доступная следующая работа: W32 — история/детали сохранённых экспериментальных записей. Полный пользовательский launch остаётся закрыт до подтверждённой интеграции источников.

# 2026-10-29 — W30: понятные режимы экономики в Telegram

- Базовый экран описывает доступную текущую/историческую экономику, а неизвестные расходы явно остаются неизвестными. Плановая экономика отдельно обозначена как модельный сценарий «что если», который не меняет данные Ozon.
- В деталях SKU добавлено объяснение базового режима и действие для планирования цены/ручных допущений; добавление доступно только если сам runtime калькулятора подключён.
- Проверен пользовательский маршрут ручного тарифа: после подтверждения открывается тот же SKU и scenario ID, неизменны плановая цена и себестоимость, комиссия получает происхождение ручного подтверждения.
- Изолированный W30 profile: **69 passed in 2.11s**. Synthetic tests only; no live API/bot. Evidence: `UNIT_ECONOMICS_W30_TELEGRAM_GUIDED_ENTRY_2026-10-29.md`.
- Следующий этап — W31: guided experiment wizard от SKU до активной baseline/candidate фазы.

# 2026-10-29 — W29: рекомендации и решения владельца

- Добавлен детерминированный разбор всех шести исходов W28 с понятным следующим шагом. Максимум выбирается только среди последних оценённых candidate revisions, прошедших совместимость с одной и той же базовой коллекцией/себестоимостью/налогом; несопоставимые и устаревшие данные не ранжируются.
- Planning Workspace мигрирует v11→v12 аддитивно и сохраняет append-only журнал решений владельца с точной ссылкой на текущий результат candidate-фазы. Допустимы: оставить baseline, выбрать оценённого кандидата, продолжить тест или остановиться без изменения цены. Завершение требует актуального финального решения; продолжение не переводит эксперимент в COMPLETED.
- Решение и расчёты остаются локальными: запись не меняет цену на Ozon. Данные решения ограничены allowlist и не содержат свободного текста.
- Linked W26–W29 profile: **98 passed in 4.42s**; synthetic temporary storage, compile and `git diff --check` PASS; `git diff -- data` empty. Evidence: `UNIT_ECONOMICS_W29_RECOMMENDATION_DECISIONS_2026-10-29.md`.
- Следующий этап — W30: guided экран unit economics и маршрут ручного тарифа.

# 2026-10-29 — W28: сопоставление зрелых ценовых фаз

- Добавлен сервис сравнения baseline/candidate для совместимого режима распределения расходов по окну. Он требует одинаковых замороженных допущений, полного источникового покрытия, стабильных условий и зрелых фаз; strict retained cohort остаётся несопоставимым без доказанного распределения возвратов.
- Прибыль на единицу считается как чистые начисления Ozon минус сохранённая себестоимость и налог через канонический TaxService. Отдельные комиссии, реклама и Performance CPC показываются для сверки и повторно не вычитаются. Возвращаются ₽/unit, абсолютная дельта и ограниченная рекомендация; проценты не показываются при нулевой/отрицательной базе, статистическая уверенность и причинность не заявляются.
- Результат schema v2 проверяет арифметику и совместимость; репозиторий атомарно проверяет baseline/candidate revisions и контрольные события перед append. Старые schema-v1 результаты остаются читаемыми.
- Linked W26–W28 profile: **50 passed in 3.41s**; synthetic temporary storage, `py_compile` and `git diff --check` PASS; `git diff -- data` empty. Evidence: `UNIT_ECONOMICS_W28_PHASE_COMPARISON_2026-10-29.md`.
- Следующий этап — W29: объяснимая рекомендация и запись решения владельца без изменения цены Ozon.

# 2026-10-29 — W27: зрелость результата и gates качества данных

- Добавлены pure maturity gates и revisioned readiness service для завершённых фаз. Оценка использует строго latest immutable collection; finance/returns/CPC coverage, finite collection budget, семь полных локальных дней, минимум 30 eligible units и denominator проверяются отдельно.
- Исправлена обработка нулевого/неизвестного количества: missing sold units имеют статус UNKNOWN, подтверждённый ноль блокирует расчёт на единицу; знаменатель всегда `SOLD_UNITS_WINDOW` при наличии положительного числа выкупленных единиц. Profit пока остаётся null — сравнение относится к W28.
- Late collection append создаёт отдельную result revision, сохраняет прежние ссылки/хеши и не переписывает историю; повторный idempotency key не создаёт новую ревизию. Mixed prices и price history явно помечаются как неподтверждаемые из доступного источника.
- Linked W25–W27 profile: **148 passed in 5.15s**; `py_compile`, staged `git diff --check` PASS; `git diff -- data` пустой. Acceptance: `UNIT_ECONOMICS_W27_MATURITY_GATES_2026-10-29.md`.
- Следующий этап — W28: сравнение совместимых фаз и расчёт delta ₽/unit с guard-ами против ложной причинности.

# 2026-10-29 — W26: сбор фактов завершённой фазы эксперимента

- Добавлен сервис сбора точного завершённого окна через существующий reader с общим PeriodProfitOperationTrace. Проверяются owner/store/SKU/схема/цена, timezone и точная owner-confirmed отметка effective_from; поздний ответ после паузы/CAS conflict не сохраняется.
- Аддитивная миграция v10→v11 добавила immutable phase collection snapshot и атомарную запись вместе с provisional WAITING_FOR_DATA result. Прибыль остаётся null до maturity/quantity/compatibility gates. Новый retry loop и фоновые запросы не вводились.
- Изолированный linked profile: 64 passed in 3.21s; py_compile и git diff --check PASS; git diff -- data пустой. Реальные Ozon API и бот не запускались. Acceptance: UNIT_ECONOMICS_W26_PHASE_COLLECTION_2026-10-29.md.
- Следующий этап — W27: maturity/quantity/source gates и отдельные result revisions по поздним фактам.

# 2026-10-29 — W25: контрольные условия и pause/resume эксперимента

- Добавлен чистый `UnitEconomicsExperimentControlService` с allowlist owner-reported флагов advertising/card/cost/inventory/promotion/tariff. Изменение и UNKNOWN формируют явные reason codes; доказательства и конфигурации прежней фазы не перезаписываются.
- `PlanningWorkspaceRepository` атомарно записывает контрольные события, останавливает фазу и связанное observation, освобождает общий active-SKU guard, готовит новый сегмент и принимает только свежее подтверждение, согласованное с сохранённым baseline/candidate target.
- Planning Workspace schema v9→v10 — аддитивная миграция с bounded append-only journal, content hash, CAS/idempotency и разрешением только первого baseline segment; cancel/archive корректно очищают resume target. Связанный профиль: **106 passed in 3.38s**; `py_compile`, `git diff --check` прошли; `git diff -- data` пуст. Code: `5c609de8`; acceptance: `UNIT_ECONOMICS_W25_PHASE_CONTROLS_2026-10-29.md`.
- Следующий этап — W26: сбор окна завершённой фазы из существующих collectors и нового cost evidence с общим trace budget.

# 2026-10-29 — W24: owner-confirm цены и времени эксперимента

- W24 добавил read-only preview с revision tokens и атомарное подтверждение точной цены фазы вместе с owner-declared observation, phase/experiment revisions и общим SKU guard. Валидация включает timezone/future/full-local-day, exact plan/SKU link, existing observation quota, stale CAS и idempotency. Подтверждение владельца не трактуется как проверенная Ozon price history.
- Planning Workspace v8→v9 миграция добавляет nullable phase link/evidence; legacy phases остаются без подтверждения. Связанный тестовый профиль: **96 passed in 2.84s**; `py_compile`, `git diff --check` прошли; `git diff -- data` пуст. Code: `e39bb48e`; acceptance: `UNIT_ECONOMICS_W24_PHASE_CONFIRMATION_2026-10-29.md`.
- Следующий этап — W25: control flags и pause/resume фазы без изменения записанного evidence.

# 2026-10-29 — расширенная экономика SKU и эксперименты, W00–W25

- W23 добавил pure сервис выбора 2–10 цен в границах владельца, с копеечными точками tariff boundary, существующим canonical расчётом и учётом tie. Неизвестный тариф/комиссия и переполнение лимита закрывают ранжирование; без замороженного тарифа комиссия явно является ручным допущением. 87 связанных тестов, compile, `git diff --check` прошли; `git diff -- data` пуст. Evidence: `UNIT_ECONOMICS_W23_CANDIDATE_PRICES_2026-10-29.md`.
- W24 закрепил owner-confirm цены/времени и точную observation binding; W25 добавил контрольные флаги и раздельные pause/resume сегменты. Следующий этап — W26: сбор результата завершённого окна.

- W22 (code commits `247ad97c0854`, `9993bad6b3d7`) добавил планирование максимальной прибыли ₽/шт: price bounds, 3–28 дней, default 7, threshold ≥0.01 ₽ и maturity gate 7 дней/30 единиц. Неполный draft сохраняется, но READY запрещён до валидных bounds и 2–10 уникальных candidate prices; после READY revision config заморожен. Incomplete draft history сохраняется при cancel/archive. Planning Workspace v8 migration не переписывает существующие записи. Linked W21/W22/snapshot/export profile: **156 passed in 6.76s**. Evidence: `UNIT_ECONOMICS_W22_PLAN_READINESS_2026-10-29.md`.
- Следующий этап — W23: выбрать candidate prices существующими tariff-aware solvers и проверить canonical forward calculation.

- W21 (code commit `788c6c8abcd9`) добавил pure state machine эксперимента, аддитивную DB schema v7 и общий атомарный active-SKU guard для observation/experiment с безопасным backfill конфликтов старых активных записей. На этом этапе application mutation покрывает отмену и архивирование; phase-confirmation workflow зависит от W24–W27. Linked profile: **130 passed in 5.74s**. Evidence: `UNIT_ECONOMICS_W21_STATE_MACHINE_ACTIVE_GUARD_2026-10-29.md`.
- Следующий этап — W23: tariff-aware candidate price selection.

- W20 добавил единый bounded, privacy-safe read model для сохранённой экономики эксперимента, coverage и точных revisions; JSON/CSV экспорт использует ту же проекцию без source reload и повторного расчёта. Фактический Telegram detail UI ожидает W32. Связанный изолированный профиль: **50 passed in 3.49s**. Evidence: `UNIT_ECONOMICS_W20_SNAPSHOT_VIEW_EXPORT_2026-10-29.md`.

- W19 (code commit `d1e1fbac`) протянул frozen window/strict-cohort cost basis через observation result, quality и ranking: signatures связывают режим, scope, source refs, assumptions и per-unit amount. Несовпадающие модели и incomplete basis не сравниваются; `OWNER_COST` отмечается как `MANUAL_ASSUMPTION`. Узкая нормализация `scheme` → `sale_schema` для строгого расчёта не ослабляет exact identity gate. Старые observation/comparison records остаются читаемыми. Linked profile: **136 passed in 9.48s**; `py_compile`, `git diff --check` PASS; `git diff -- data` пустой. Evidence: `UNIT_ECONOMICS_W19_COST_BASIS_COMPARABILITY_2026-10-29.md`.
- Следующий этап — W22: durable experiment plan and readiness bounds.

- W18 (commit `731be723`) добавил read-only reopen API для exact plan/calculation revision, expense content-hash snapshot, тарифного профиля и quantity observation result. Явное обновление плана, тарифа, observation и снимка не меняет ссылки старого эксперимента; correction сохраняется append-only result revision, а копия расширенного плана открывается без повторного source I/O. Связанный профиль: **79 passed in 5.77s**. Evidence: `UNIT_ECONOMICS_W18_FROZEN_SNAPSHOT_2026-10-29.md`.
- W17 добавил аддитивную схему Planning Workspace v6 для content-addressed снимков расходов и append-only экспериментов/фаз/результатов с exact-scope ссылками, CAS/idempotency и квотами. Старые планы и payload schema 1–4 сохранены; связанный профиль: **89 passed**, полный isolated `pytest`: **4,166 passed in 36.99s**. Evidence: `UNIT_ECONOMICS_W17_EXPERIMENT_REPOSITORY_2026-10-29.md`.

- W16 протянул один canonical extended expense/strict-cohort contract через sensitivity, batch, sales mix, сохранение/восстановление планов и сравнение. Расширенные суммы попадают в projection до налога; sales mix сохраняет один aggregate tax call. Новый payload schema 4 совместим со схемами 1–3; database schema не менялся. Linked profile: **319 passed**; полный isolated repository `pytest`: **4,158 passed in 47.62s**. Acceptance: `UNIT_ECONOMICS_W16_CONSUMER_PARITY_2026-10-29.md`.
- W15 поиск цены и bounded tariff guard остаются подтверждены: **168 passed in 1.86s**, `UNIT_ECONOMICS_W15_SOLVER_GUARDS_2026-10-29.md`.

- W00–W02: baseline/inventory, lineage audit и Ozon source contract audit завершены.
- W03 закрепил архитектуру Decision 064. W04 зафиксировал synthetic numeric oracles N01–N18; baseline профиль — **334 passed**. W05 добавил pure нормализацию подписанных расходов, dedup/conflict, ownership ledger и coverage. W06 добавил resolver финансовой рекламы и reconciliation-only Performance CPC; связанный профиль — **90 passed**.
- W07 добавил pure return/non-buyout resolver, exact delivered/returned/retained cohort gate и отдельный inventory loss/recovery/compensation evidence. Optional opaque cohort binding проходит через нормализатор; отсутствие связи даёт структурированный incomplete result и закрывает strict расчёт. Связанный профиль W07/W06/W05 и legacy returns: **115 passed in 1.89s**.
- W08 добавил pure resolver хранения/размещения и дополнительных услуг с disjoint mapping, confirmed-zero/missing gate, base overlap, account residual, one-off credits и delegation существующего кросс-докинга. Связанный W08/W07/W06/W05 profile: **89 passed in 1.23s**. Он не вычисляет per-unit rate и не подтверждает полноту всего магазина.
- W09 добавил `UnitEconomicsWindowSnapshotService`: bounded последовательный сбор нормализованных evidence в общем дочернем operation trace, exact 56 completed local dates, отдельное окно фазы, точные requested/observed bounds и weighted `sum(expense)/sum(units)`. Короткая история, incomplete source/pages, 429, исчерпание parent/child бюджета, смешанные denominator kinds и нулевые единицы не превращаются в полную ставку; общий лимит 128 учитывает уже использованные попытки user operation. Совокупный normalized evidence ограничен 64 KiB; snapshots получают безопасные fingerprints. Связанный изолированный профиль W05–W09 и operation trace: **116 passed in 1.80s**; `py_compile`, `git diff --check` PASS, `git diff -- data` empty. Реальные источники пока не подключены, сборщик принимает только нормализованные evidence readers.
- W10 добавил чистую `UnitEconomicsReadinessViewService`: готовые snapshots проецируются в `INCLUDED` / `EXCLUDED` / `UNKNOWN` с allowlisted source, observed и applied суммы/единицами и bounded reason codes. Подтверждённый ноль не становится unknown; отсутствующие metadata и zero denominator блокируют применение к ставке. Reference и phase остаются раздельными; пересекающиеся окна несравнимы. Объединённый изолированный W05–W10 профиль: **131 passed in 2.00s**.
- W11 расширил canonical `UnitPriceScenarioService` версионированным дополнительным контрактом расходов. Полный оконный расход вычитается до существующего `TaxService`, legacy path сохраняется; неполнота, повтор ownership, неверные входы, неполная базовая экономика и смешение знаменателя кросс-докинга закрывают расчёт. `calculate_components_only` и `compare` следуют той же формуле. Strict retained cohort намеренно unavailable до W12. W05–W11 isolated profile: **175 passed in 2.71s**. Acceptance: `UNIT_ECONOMICS_W11_CANONICAL_FORWARD_2026-10-29.md`.
- W12 включил strict return loss из W07 resolver в тот же canonical forward. Перед расчётом сверяются exact identity, cohort statuses, доставленные/возвращённые/оставшиеся единицы, disposition quantity, все суммы и формула loss pool; incomplete evidence, Q0, mismatched cohort, pending inventory и net credits fail closed. Window allocation отдельно, режимы не смешиваются. W05–W12 isolated profile: **184 passed in 2.75s**. Acceptance: `UNIT_ECONOMICS_W12_STRICT_RETAINED_CANONICAL_GATE_2026-10-29.md`.
- W13 добавил налоговые regressions на расширенном сценарии: `NONE`, `USN_INCOME` с нулевыми и ненулевыми баллами, `USN_INCOME_MINUS_EXPENSES`, minimum-tax dominance и один налоговый вызов на grouped sales mix. Extra expense учитывается до существующего TaxService и не вычитается повторно после налога. Runtime policy не менялась. Адресный профиль: **44 passed in 1.42s**; combined W05–W13: **186 passed in 3.06s**. Acceptance: `UNIT_ECONOMICS_W13_TAX_POLICY_PARITY_2026-10-29.md`.
- W14 added an explicit fixed-advertising-cost input in ₽ per successful sale alongside the existing percent mode. The absolute amount may exceed the seller price and is retained through repricing/comparison; changing mode clears the other representation, saved plans validate and preserve the exact mode, and percentage compensation thresholds are not synthesized for fixed-cost scenarios. Focused W14 profile: **201 passed in 3.10s**; linked consumers profile: **136 passed in 2.62s**. Acceptance: `UNIT_ECONOMICS_W14_ADVERTISING_MODES_2026-10-29.md`.
- Evidence: `UNIT_ECONOMICS_W03_CONTRACTS_ARCHITECTURE_2026-10-28.md`, `UNIT_ECONOMICS_W04_NUMERIC_ORACLES_2026-10-28.md`, `UNIT_ECONOMICS_W05_NORMALIZER_2026-10-28.md`, `UNIT_ECONOMICS_W06_ADVERTISING_RECONCILIATION_2026-10-28.md`, `UNIT_ECONOMICS_W07_RETURN_COHORTS_2026-10-28.md`, `UNIT_ECONOMICS_W08_STORAGE_ADDITIONAL_EXPENSES_2026-10-28.md`, `UNIT_ECONOMICS_W09_WINDOW_SNAPSHOTS_2026-10-28.md`, `UNIT_ECONOMICS_W10_READINESS_VIEW_2026-10-29.md`, `UNIT_ECONOMICS_W11_CANONICAL_FORWARD_2026-10-29.md`, `UNIT_ECONOMICS_W12_STRICT_RETAINED_CANONICAL_GATE_2026-10-29.md`, `UNIT_ECONOMICS_W13_TAX_POLICY_PARITY_2026-10-29.md`, `UNIT_ECONOMICS_W14_ADVERTISING_MODES_2026-10-29.md`, `UNIT_ECONOMICS_W15_SOLVER_GUARDS_2026-10-29.md`, `UNIT_ECONOMICS_W16_CONSUMER_PARITY_2026-10-29.md`, `UNIT_ECONOMICS_W17_EXPERIMENT_REPOSITORY_2026-10-29.md`, `UNIT_ECONOMICS_W18_FROZEN_SNAPSHOT_2026-10-29.md`, `UNIT_ECONOMICS_W19_COST_BASIS_COMPARABILITY_2026-10-29.md`, `UNIT_ECONOMICS_W21_STATE_MACHINE_ACTIVE_GUARD_2026-10-29.md`, `UNIT_ECONOMICS_W22_PLAN_READINESS_2026-10-29.md`. Provider-specific source adapters and product user flow remain pending; durable experiment storage and exact frozen input reopen are implemented, program IN_PROGRESS, next W23.

# 2026-10-28 — расширенная экономика SKU и эксперименты, W00–W02

- Создана реализационная ветка от exact spec PR #721; сохранность tracked/ignored owner data подтверждена baseline manifest. Код расчёта и data files не менялись.
- W01 зафиксировал lineage текущих источников; W02 отделил подтверждённые официальными материалами Ozon endpoint families от точных параметров, которые пока подтверждаются только реализацией/примером. Для Analytics no-Premium отсутствующие `cancellations`/`returns`/`delivered_units` считаются недоступными, не нулевыми.
- W02 audit: `UNIT_ECONOMICS_W02_OZON_API_CONTRACT_AUDIT_2026-10-28.md`. Программа W03–W39 остаётся IN_PROGRESS; этот этап не означает production readiness или реальную проверку API.

# 2026-10-28 — W01 завершён: lineage источников и потребителей

- Read-only карта W01: `UNIT_ECONOMICS_W01_DATA_LINEAGE_AUDIT_2026-10-28.md`. Отмечены актуальные vs accrual/report/event даты, точный SKU/store scope, знаменатель и completeness для всех существующих затрат и наблюдений.
- Подтверждено: `FinanceService.sales_count` считает положительные строки товара в posting, а не quantity; `get_daily_finance(..., sku=...)` может включить полный `total_amount` совпавшей multi-product операции, несмотря на SKU-фильтр. Оба поля требуют осторожного использования для нового strict SKU P&L.
- W00–W01 завершены на implementation branch от spec PR #721; runtime код и тесты не менялись, owner data не читались/не трогались. Следующий этап W02 — официальная сверка API contracts.

# 2026-10-28 — исполнение W00–W39 начато

- W00 завершён: PR #721 проверен на exact HEAD `f76d2dd90e4298113c037278666532715974e4a8`; `main` на старте — `9315046cf29c9e8c68da1cab027cb2568040f142`. Implementation branch создана от exact spec HEAD; baseline owner-data inventory без чтения содержимого сохранён в `UNIT_ECONOMICS_W00_BASELINE_2026-10-28.md`.
- Рабочее дерево при старте было чистым; `data/`, ignored tenant storage, `.env` и базы не менялись. Исполняемый код не менялся; следующий этап W01 — подтверждение lineage источников и потребителей.

# 2026-10-28 — новая программа: экономика SKU и управляемые эксперименты

- PR #719 и #720 слиты в main по авторизации владельца: merge SHA 6bf89cc8 и 9315046c. Последний reviewed implementation HEAD 28e6ae77 прошёл Verify 40667273360 на Windows/Linux; исторические записи ниже о незавершённом merge относятся к прежним checkpoint.
- Владелец выбрал следующие направления: более полный учёт расходов SKU и пошаговый ценовой эксперимент. Подготовлены LUNA_FULL_UNIT_ECONOMICS_AND_PRICE_EXPERIMENTS_TASK_2026-10-28.md, исходный audit и журнал.
- 40 этапов W00–W39, 18 acceptance groups; старт реализации — W00. Все стадии NOT_STARTED. Runtime, owner data и реальный бот при подготовке не изменяются.
- Проверки пакета: dependency graph/task-journal consistency, 58 existing paths и Decimal/canonical numerical oracles — PASS; это подготовка задания, не приёмка новой реализации.
- Новая программа должна закончиться готовыми PR и CI актуального HEAD; merge/deploy/live bot в неё не входят. Подтверждённые расходы, window allocation и retained cohort получают раздельные основания; источник без доказательства не превращается в нулевую стоимость.

# 2026-10-28 — PR #720: повторный review R8

- Смена целевой маржи повторно запускает bounded solver для строк с сохранённым снимком, даже если их предыдущий поиск исчерпал бюджет. Неполные строки без снимка, неподдерживаемые схемы и недоступный источник не затрагиваются; ограничения solver остаются прежними.
- Добавлена регрессия для двух SKU: цель 50% исчерпывает лимит в 128 вычислений на строку; смена цели на 0% заново находит результат за 6 вычислений на строку. Связанный профиль Windows/Python 3.12: **165 passed in 4.14s**; полный pytest в отдельной временной worktree на коде `2f03edcd`: **3,997 passed in 48.17s**. Exact-head Verify [40666814742](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/40666814742) успешно завершился на `442e5dff`; основной checkout и его `data/` чистые.

# 2026-10-28 — PR #720: исправления повторного review (R6–R7)

- Повторные расчёты единичной строки и массовые расчёты целевой маржи/рекламы теперь ограничены на входе в solver: не более `TARGET_CALCULATION_LIMIT` на SKU и в пределах оставшегося `BATCH_CALCULATION_LIMIT`. Исчерпание возвращается как `BUDGET_EXHAUSTED`, а не как обычное отсутствие результата.
- Тариф из подтверждённого источника допускается quality gate в модельном сравнении; неизвестный тариф остаётся блокирующим. Результат не повышается до подтверждённого факта.
- Связанный профиль Windows/Python 3.12: **164 passed in 4.53s**; полный pytest в отдельной временной worktree на `b2f01fb3`: **3,996 passed in 47.43s**. `compileall` и `git diff --check` прошли; исходный checkout и `data/` остались без изменений. Кодовый коммит `dbd87c7d` опубликован в PR #720 и прошёл exact-head Verify [40664676434](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/40664676434) (Windows + full verification). Следующий коммит содержит только этот результат в документации; merge/deploy/live bot не выполнялись.

# 2026-10-28 — review corrections калькулятора цены по прибыли/шт.

- Исправлены пять подтверждённых замечаний независимого review PR #720: комиссия наблюдения привязывается к наблюдаемой цене и provenance; окно Returns передаётся в точных UTC-моментах; сессионный тариф различается от конфликтующих постоянных профилей; минимальная целевая цена проверяется с учётом округления; общий лимит batch-вычислений передаётся до solver-вызова.
- Новый связанный Windows/Python 3.12 профиль: **149 passed** на восьми модулях; полный изолированный `pytest`: **3,990 passed in 49.21s**. `compileall`, `git diff --check` прошли; `data/` в основном checkout остался чистым.
- PR #720 остаётся stacked на PR #719. Опубликованный code/documentation head `40a23315d74958cb7b7e427b785f730ea886ac79` прошёл Verify `40654624761` (Windows/Linux). Слияние, развёртывание и запуск бота не выполнялись.

# 2026-10-27 — калькулятор прибыли с единицы: Q30 buyout estimate

- По решению владельца наблюдаемый процент выкупа SKU вычисляется из завершённых FBO postings и Returns API, а не принимается как ручное число. Неполные выборки и неоднозначные отмены блокируют модель; delivered/(delivered + подтверждённые невыкупы покупателя) показывается с размером выборки.
- Сквозной Telegram flow показывает проценты/доставленные/возвращённые единицы, рассчитывает явно модельную прибыль и сравнивает 100 ₽ с 95 ₽. Возвратные расходы явно исключены из модели; CPC и FBO используют разные основания дат. Live Ozon/API не запускался.
- Q30 focused profile: **56 passed in 2.60s across six changed UI/evidence modules**; Q31 linked profile: **1,374 passed in 39.94s на 175 модулях**, plus bounded soak/evaluation **3 passed in 3.12s**; Q33 full suite: **3,983 passed in 53.74s** in a disposable isolated worktree. Q35 exact implementation-head Verify `40573748055` passed on `0154f857`; documentation-only PR head `483cd4d1` also passed Verify `40574423459` (Windows, Linux, Docker). Compileall and diff checks pass; tracked owner data in the implementation worktree is clean. Independent review package is attached to PR #720; independent reviewer feedback is still pending. Детали/resume: `LUNA_PRICE_PROFIT_PER_UNIT_PROGRESS_2026-10-26.md`, Q30–Q35 acceptance and `UNIT_PRICE_PROFIT_PER_UNIT_USER_GUIDE_2026-10-27.md`.

# 2026-10-27 — Q29: сохранность калькулятора цены при backup/restore

- Q29 завершён: синтетические тариф, план, наблюдение и две версии результата восстановлены через существующий backup в новый storage root; scope и privacy guards подтверждены.
- Проверки: новый backup/restore тест + адресные старые schema migrations — **5 passed in 0.95s**. Полный pytest и exact-head CI остаются Q33–Q35.
- Acceptance: `UNIT_PRICE_PERSISTENCE_PRIVACY_RESTORE_Q29_2026-10-27.md`; журнал: `LUNA_PRICE_PROFIT_PER_UNIT_PROGRESS_2026-10-26.md`.

# 2026-10-26 — следующая программа: выбор цены по прибыли с единицы

- PR #718 слит в main: `07a84b5d7a9ffa7d0007947e0d8d4e9032052e01`; reviewed head `8c1408d55d31e111761bdee708a2792ab1dafa33`, Verify #40348020402 успешен на Windows/Linux и Docker. Записи ниже о незавершённом merge относятся к предыдущим checkpoint.
- По решению владельца подготовлено `LUNA_PRICE_PROFIT_PER_UNIT_TASK_2026-10-26.md`: 8 модулей A–H, этапы Q00–Q35. Цель — прибыль в рублях с одной проданной единицы, с тарифными диапазонами, ручными комиссиями, рекламными сценариями и проверкой по наблюдениям.
- Журнал: `LUNA_PRICE_PROFIT_PER_UNIT_PROGRESS_2026-10-26.md`. Q00–Q34 пройдены 27.10.2026: полный изолированный pytest — 3,983 passed; Q33/Q34 acceptance находятся в `UNIT_PRICE_FINAL_VERIFICATION_Q33_2026-10-27.md` и `UNIT_PRICE_SELF_REVIEW_Q34_2026-10-27.md`. Exact-head CI и PR review package — Q35. Acceptance Q29: `UNIT_PRICE_PERSISTENCE_PRIVACY_RESTORE_Q29_2026-10-27.md`.
- ТЗ требует расширять существующие calculator/TaxService/planning/finance adapters, сохранять старые планы и данные, закончить на PR с зелёным exact-head CI и независимым review package. Merge/deploy/real bot запуск в новую программу не входят.

# 2026-10-26 — историческая программа: завершение существующего функционала

- Исправлены два review замечания PR #718: legacy fast-forward защищает ignored-файлы через `git merge --no-overwrite-ignore`, а подписанное начисление кросс-докинга по SKU выводится даже при отсутствии поставок без создания ставки за единицу. Windows/Python 3.12: адресный профиль **35 passed in 15.43s**, полный `pytest` **3747 passed in 42.67s**, `compileall` успешен. Verify #40346807627 зелёный на fix SHA `a2f203daa4ac3dcfd4573f93ddd6f9d2b53a8b88`, Verify #40347424289 зелёный на PR SHA `5eff674cbdc4d63bcc7ca602bdfa07ae0705bb98`; Windows, Linux/Python 3.11, Docker build/runtime прошли. PR остаётся открытым, merge/deploy/live start не выполнялись.

- Z07 в ветке `codex/existing-functionality-completion`: cross-docking evidence теперь показывает signed начисления и корректировки, независимый completeness финансов/поставок и стабильное время снимка; сохранённые планы переносят optional поля через reopen/recapture. Адресный изолированный профиль — 194 passed. Реальный полный 56-дневный снимок владельца остаётся неполученным и не подменяется тестовыми данными.
- Z08 подтверждён без новых изменений: 64 изолированных регрессии покрывают multi-SKU attribution/store estimate, positive corrections, dedup/conflicts, accepted `fact_quantity`, частичный приём и отказ от ставки при неоднозначных/неполных supply facts. Отдельный реальный multi-SKU акт владельца всё ещё ожидается; внешняя семантика не расширялась.
- Z09 подтвердил существующий путь: cross-docking применяется ровно один раз, сохраняются налоговые режимы и v1 legacy; v2 открывает frozen evidence без чтения Ozon, explicit refresh создаёт новую revision, batch/mix использует заданный Q, plan/fact не присваивает плановый расход факту. 238 изолированных проверок passed.
- Z10 закрыт: противоречивое предупреждение об исключённом кросс-докинге исправлено на target/comparison, advertising-cap и sensitivity экранах; состояние ставки и legacy v1 раскрывается явно. Публичный профиль — 48 passed; формулы не менялись.
- Z11 подтверждён как VERIFIED_EXISTING: target цены и лимит рекламы повторно сверяются прямым калькулятором; границы копеек, search budget, невозможные цели, tax regimes/minimum tax и сохранение ручных допущений при refresh имеют регрессии. Связанный профиль — 110 passed; код и политика не менялись.
- Z12 подтверждён как VERIFIED_EXISTING: saved plans проходят create/open/local continue/preview/revision/copy/reopen; версии защищены CAS, старые кнопки не применяют устаревшее действие, scope магазина и идентичность SKU сохраняются. Связанный storage/Telegram профиль — 44 passed; код не менялся.
- Z13 подтверждён как VERIFIED_EXISTING: three-SKU batch/mix, readiness, plan/fact и export связаны и сохраняют unknown/zero/completeness semantics; общий налог считается один раз, сравнение требует совместимые scope/period/SKU. Изолированный профиль — 108 passed; код не менялся.
- Z14 подтверждён как VERIFIED_EXISTING: 416 offline public-route тестов прошли для меню, onboarding, справки, legacy разделов, отчётов, себестоимости, экспериментальных сценариев, product decisions, товаров и возвратов. Подтверждённого недостижимого handler не найдено; код не менялся.
- Z15 подтверждён как VERIFIED_EXISTING: 160 изолированных проверок прошли на stale scope/callbacks, deduplication, atomic cache eviction/concurrent reads и общем Ozon Performance attempt/time budget. Источник не вызывается на cache read; код не менялся.
- Z16 подтверждён как VERIFIED_EXISTING: 171 проверка прошла на доли/числа, короткие и подробные отчёты, UTF-16 split длинных Telegram ответов и безопасную передачу allowlisted diagnostics. Подтверждённого дефекта не выявлено; код не менялся.
- Z17 завершён: runbook объясняет первый переход со старой установки без `update_bot.ps1`, read-only проверки ветки/изменений, безопасный fast-forward при чистом main и остановку при dirty/untracked файлах. Локальный tracked diff/untracked список сохраняются вне checkout, sensitive материалы не отправляются. Профиль runbook/preflight — 24 passed; production bot не трогали.

- Исполнение LUNA_EXISTING_FUNCTIONALITY_COMPLETION_TASK_2026-10-26.md начато в отдельной ветке codex/existing-functionality-completion, база e879e6d7881a097f040e56d9962223525840917c. GitHub подтвердил, что main после PR #717 имеет merge SHA 89eb9224c3e9ec2126f58dc4d38794b33c2a2cc0; выбранное дерево совпадает.
- PR #702–#704 закрывают продуктовый аудит A–G; прежние stacked #698–#701 закрыты без отдельного merge и их рассмотренная работа вошла в #702. PR #705–#708 закрывают H–O, #712 — X00–X06, #713–#717 — daily readiness/reconciliation. Они не являются открытой очередью этой программы. PR #709–#711 добавили read-only диагностику поставки/акта.
- Z00–Z02 и Z20 завершены: безопасная база, реестр 16 пунктов меню и связанных пользовательских путей, конечный backlog, актуальные указатели и изолированный тестовый профиль. Все ссылки на 84 тестовых файла существуют; отдельный baseline профиль — 37 passed, tracked JSON hashes до/после совпали. Новых сервисов/тестов пока нет; приложение не запускалось.
- Z03: локальная сверка августовского XLSX подтвердила категории и агрегат; 62 адресных теста прошли. Денежные значения файла в эту рабочую ветку не записывались; полнота source остаётся UNVERIFIED.
- F-01 — подтверждённая ранее ошибка подписи — RESOLVED на Z10 с публичными регрессиями.
- Владелец ещё не предоставил актуальный runtime JSON, полное 56-дневное evidence по кросс-докингу или 24–72-часовое наблюдение. Это внешняя проверка, а не основание объявлять неизвестные данные нулём.
- Z04: себестоимость и external expense flows прошли 54 synthetic regressions; effective date, stale callback и coverage behavior подтверждены, правила учёта не менялись.
- Z05: 103 адресные регрессии прошли; Analytics missing metrics не восстанавливаются, Cancellation и ClientReturn различаются, проценты не показываются при несовпадении когорт. Источник текущего статуса отмены не выдаётся за событие отмены в периоде.
- Z06: 104 адресные регрессии прошли. Основной и подробные экраны, полнота, сравнение, bridge, SKU contribution и экспорт читают один scoped cached snapshot; Ozon-запрос выполняется только при явном обновлении.
- Z18 закрыт synthetic-профилем: backup/verify/dry-run/restore/new-root/read-after-reopen сохранили saved plan/revision, cost effective dates, external expenses/coverage, активный mapping и зашифрованные credentials. С отсутствующим/неверным ключом статус остаётся явной ошибкой; профиль — 33 passed. Z19 подтверждён: 82 изолированных lifecycle/update/preflight/backup теста прошли, включая owned-generation stop, exact-target readiness, общую maintenance блокировку и controlled failure без hidden restart. Z21 local Windows/Python 3.12: 198 integrated checks, полный pytest — 3745 passed, compileall exit 0; exact code head df6b506e прошёл GitHub Verify #40337702406 (Windows, Linux/Python 3.11, Docker build/runtime smoke). PR #718 открыт и CI зелёный; независимый review package: EXISTING_FUNCTIONALITY_COMPLETION_REVIEW_2026-10-26.md. Z23 завершён как ENGINEERING_READY_OWNER_PENDING: в progress journal есть безопасные шаги получения текущей версии, финансового JSON и cross-docking агрегатов. Полный актуальный 56-дневный multi-SKU evidence и 24–72h observation остаются owner evidence.

---
# 2026-10-26 — дополнительные исправления review PR #717

- Исправлен P1: read-only preflight сравнивает входящие Git-пути с локальными ignored файлами и папками по совпадению и предкам/потомкам. Fast-forward защищён опцией `--no-overwrite-ignore` на случай изменений между проверкой и слиянием.
- Исправлен P2 в recovery runbook: путь `restore-drill` вычисляется как абсолютный нормализованный путь, который проходит строгую проверку восстановителя.
- Адресные Windows/Python 3.12 проверки: **57 passed in 15.60s**. Code head `7c065b3a4ca6ef8211b3d149e5d998147cd3f925` прошёл exact-head Verify `40292624411`: Windows/Linux по **3,740 passed**, compile и Linux production Docker build/runtime smoke успешны. Подробности: `DAILY_USE_READINESS_REVIEW_FIXES_2026-10-25.md`.

# 2026-10-25 — новые исправления независимого review

- Исправлены четыре подтверждённых дефекта: ignored-файл, совпадающий с входящим Git-путём, теперь блокирует обновление; общий startup lock удерживается во всём окне обновления; stop привязан к исходному поколению процесса; SQLite backup получает жёсткий timeout и прерываемый subprocess.
- Добавлены regressions. Адресный Windows/Python 3.12 профиль: **70 passed in 14.99s**, связанный soak/restore/control профиль: **8 passed in 3.58s**; in-memory compile 9 файлов и `git diff --check` прошли. Code head `39d1a12bcb699ef504abbbb1c484a5a7745f23a7` прошёл exact-head Verify `40222900262`: Windows **3,736 passed in 69.29s**, Linux **3,736 passed in 15.67s**, compile и production Docker build/runtime smoke успешны. Повторное technical review не выявило новых actionable дефектов.
- Merge/deploy/live bot не выполнялись; изменения находятся в изолированной ветке `codex/daily-readiness-acceptance-rebase`. Подробности: `DAILY_USE_READINESS_REVIEW_FIXES_2026-10-25.md`.

# 2026-10-25 — исправлены R1–R3 review по D01 backup

- Исправлено распознавание list-based `actions.json`, `conversation_history.json`, `store_reports.json`; тип JSON одинаково валидируется при создании и проверке архива.
- Bot startup и backup snapshot сериализуются общим token-scoped OS guard. Mapping registry override в одобренном корне записывается относительным путём и одинаково проходит verify, dry-run и restore.
- Адресный Windows-профиль backup/lifecycle: **32 passed in 1.93s**; compileall и diff-check прошли. Полный exact-head CI по обновлённым PR ожидается. Подробности: `DAILY_USE_BACKUP_REVIEW_FIXES_R1_R3_2026-10-25.md`.

# 2026-10-25 — E01: PR stack, CI и независимый review handoff

- Открыт стек draft PR #713–#717 от проверенной базы PR #712. #713 (`e014f278`) и #714 (`7ec47ef6`) остаются зелёными на текущих heads. Исправления review R1–R3 внесены в #715 (`509fedba0246b87bbc1d407fdadcf990b2daaee0`) и перенесены merge-коммитами в #716 (`5bd3699cf70a3e459ca0bfd21776799a42c37da1`) и #717 (`8559832f802054b564823798c05e0cbf1bccead8`). Exact-head CI для новых #715–#717 ожидается; результаты старых heads больше не считаются актуальными.
- E02 пакет: `DAILY_USE_READINESS_REVIEW_HANDOFF_2026-10-25.md`. Классификация — Architecture Review Required из-за новых backup/restore и update/lifecycle boundaries.
- E03: `DAILY_USE_A05_OWNER_EVIDENCE_REQUEST_2026-10-25.md`, `DAILY_USE_OWNER_OBSERVATION_LOG_2026-10-25.md`; текущий exact-revision JSON, полный 56-дневный cross-docking snapshot и 24–72h наблюдения ожидаются от владельца. Не заявлять production acceptance.
- Ошибки, исправления и limits локальной pytest попытки: `DAILY_USE_CI_REGRESSION_FIX_2026-10-25.md`. Полный журнал, точные base/head и ограничения: `LUNA_DAILY_USE_READINESS_PROGRESS_2026-10-25.md`. Merge, deploy и live start не выполнялись.

# 2026-10-25 — ежедневная готовность, этап E00

- E00 связал пользовательский report flow и synthetic restore path: прибыль → полнота/расходы → refresh/export; расчёт → сохранённый план/себестоимость/расход → backup → dry-run → новый root → чтение с сохранением tenant isolation.
- Связанный изолированный Windows/Python 3.12 profile: **350 passed in 22.70s**. Полный pytest и exact-head CI ещё не выполнены.
- A04 доступен только в документально подтверждённом scope: начисления августа `177282.17 ₽` сходятся; точный текущий bot JSON и полный 56-дневный cross-docking snapshot ждут владельческой проверки. Следующий этап E01.

# 2026-10-25 — ежедневная готовность, этап D06

- Добавлен bounded synthetic soak для повторных расчётов/экспорта, сохранённых планов, себестоимости/расходов и восьми отдельных fake polling циклов. После добавления startup/snapshot guard lifecycle оставляет фиксированные три файла: instance metadata, instance lease lock и persistent startup/snapshot lock. Исторический локальный результат до guard: 0 новых потоков, +2 process handles; максимальный цикл 0,297 с.
- Проверены cache TTL/eviction, timeouts, interrupted backup и staged restore, checkpoint resume, повторное открытие планов/стоимостей/расходов и два изолированных tenant scope. **11 passed in 3.74s** на Windows/Python 3.12.
- Добавлены `docs/daily-use-recovery-runbook.md` и форма владельческого наблюдения `DAILY_USE_OWNER_OBSERVATION_LOG_2026-10-25.md`. Это не заменяет 24–72 часа фактической эксплуатации; owner validation остаётся pending.
- Следующий этап — E00 сквозная регрессия; затем exact-head PR CI, independent review package и внешний пакет приёмки.

# 2026-10-25 — ежедневная готовность, этап D05

- `status_bot.ps1` и CLI отдельно показывают фактическую polling readiness и offline-состояние локальных настроек; показываются revision/mode, checkout-match и только allowlisted last-failure code.
- `stop_bot.ps1` scoped к checkout. Lifecycle сохраняет только безопасный код startup/polling failure; raw exception/path/token не печатаются. Support diagnostic JSON проверенно включает режим сборки.
- D04/D05 + backup/preflight/lifecycle profile: **87 passed**; Python compile и PowerShell parser прошли. Следующий D06.

# 2026-10-25 — ежедневная готовность, этап D04

- `update_bot.ps1` реализует проверенное обновление `main` из canonical `origin/main`: fetch, immutable SHA preflight, checkout-bound graceful stop, verified backup, fast-forward, зависимости и локальные checks; обычный режим подтверждает точную polling readiness, `-NoStart` оставляет процесс остановленным.
- Ошибка после stop показывает verified backup (если создан) и safe recovery check. No automatic rollback/restore, force-kill, stash/reset/clean. Updater сериализован OS lock в private Git directory.
- D03/D04 offline regression profile: **54 passed**. Python compile, PowerShell parse и diff-check прошли. Ни одна реальная установка не выполнялась.

# 2026-10-25 — ежедневная готовность, этап C04

- Профиль подтверждает 0 дополнительных query-service вызовов для аналитики, деталей, полноты, диагностики и exports; явный refresh даёт один новый запрос по тому же периоду.
- Synthetic batch profile на 3 SKU подтверждает один catalog read, 3 snapshots, 3 полные fake finance pages, 6 fake HTTP attempts и 0,06 fake seconds. Это orchestration test, не оценка live latency.
- Подтверждённой лишней production работы не найдено, код расчётов не менялся. Тест: `test_three_sku_batch_performance_profile_counts_catalog_pages_and_http_attempts`; acceptance: `DAILY_USE_PERFORMANCE_ACCEPTANCE_C04_2026-10-25.md`.

# 2026-10-25 — ежедневная готовность, этап C03

- C01: compact report и scoped details; C02: exact-period refresh со scope checks; C03: поздний read-only результат скрывается после смены магазина.
- Duplicate callbacks, explicit refresh, HTTP 429/timeout, transient retry и time/request limits покрыты. C03 profile **44 passed, 1 ACL-bound `tmp_path` test deselected**; in-memory compile и diff-check прошли.
- C00–C03 evidence указан в `LUNA_DAILY_USE_READINESS_PROGRESS_2026-10-25.md`; C03 acceptance — `DAILY_USE_RELIABILITY_ACCEPTANCE_C03_2026-10-25.md`. Далее C04; exact-head CI ещё не запущен. A04 остаётся открыт до C05.

# 2026-10-25 — ежедневная готовность, этап B05

- B05 закрыл рассогласование полноты между отчётом, деталями и экспортами: одна allowlisted status/reason projection из сохранённого снимка теперь доступна в коротком ответе, completeness/diagnostic callbacks, support JSON и CSV/JSON metadata. Detail/export callbacks не выполняют новые запросы к Ozon.
- Приёмка: **41 passed, 1 test deselected** из-за локального Windows ACL на `tmp_path`; exact-head CI ещё требуется. Support JSON по-прежнему не включает суммы или raw payload.
- Матрица и ограничения: `DAILY_USE_COMPLETENESS_ACCEPTANCE_B05_2026-10-25.md`; следующий этап — C00; финальную A04 сверку выполнить после C00–C05 согласно зависимостям.

# 2026-10-25 — ежедневная готовность, этап B04

- Исправлен подтверждённый риск: текущая себестоимость без effective-date больше не восстанавливает исторический finance SKU. При отсутствии исторической записи прибыль с COGS блокируется как incomplete; неизвестная себестоимость не подменяется нулём или будущей стоимостью.
- Подтверждённая историческая cost evidence и раздельное подтверждение «вся история» сохранены. Return COGS по-прежнему требует inventory → attribution → recognition → authorization → commit → final application.
- B04 regression profile: **154 passed in 5.28s**. Отчёт: `DAILY_USE_COGS_EFFECTIVE_DATE_AUDIT_2026-10-25.md`; далее B05 — согласовать полноту проекций и экспортов.

# 2026-10-25 — ежедневная готовность, этап B03

- Повторно проверены источники комиссии и классификация расходов. Полный месяц использует фактические суммы продажи/возврата; логистические подкатегории, Performance CPC и альтернативная сумма хранения не добавляются повторно.
- Core finance/store/cross-docking регрессии: **94 passed in 2.54s**; 5 чистых external-expense evidence tests прошли. 8 SQLite/Telegram setup cases локально заблокированы ACL на `tmp_path`, exact-head CI остаётся обязательным.
- Подтверждённого дефекта B03 нет; production-код не менялся. Отчёт: `DAILY_USE_EXPENSE_CATEGORY_AUDIT_2026-10-25.md`; дальше B04 — себестоимость и Return COGS.

# 2026-10-25 — ежедневная готовность, этап B02

- B02 сверил Analytics и return diagnostics: ordered units **6 117** за 31 день; cancellations/returns Analytics отсутствуют, не ноль. Seller API полностью прочитан: FBO 270 `Cancellation` и 2 `ClientReturn` единицы, FBS пустой.
- Существующие fallback contracts сохраняют разные date bases, типы и количество; доли к несовместимой когорте скрыты. Профиль: **73 passed in 2.48s**. Новой production ошибки нет; следующая задача B03 — проверить классификацию расходов и одинарное включение.

# 2026-10-25 — ежедневная готовность, этап B01

- B01 добавил в существующую completeness projection сумму либо unknown, источник, период/date basis, coverage и причину по каждому материальному компоненту. Observed zero отделён от unknown; проверка рекламы не вычитается повторно.
- Целевой профиль полноты/диагностики/export/Return COGS: **43 passed in 1.58s**. Следом B02 — границы Analytics/Seller API для заказанных, отменённых и возвращённых единиц.

# 2026-10-25 — ежедневная готовность, этап B00

- B00 завершён: действующие completeness projection, диагностика, scoped snapshots/export и Return COGS blocker resolver проверены; **40 targeted tests passed**, новых подтверждённых дефектов нет.
- Gap-реестр: `DAILY_USE_COMPLETENESS_GAP_AUDIT_2026-10-25.md`. B01 продолжает покомпонентное provenance/coverage в существующем view; отмены/возвраты остаются ограничением источника до подтверждения полного API-контракта.

# 2026-10-25 — ежедневная готовность, этап A03

- A03 закрыт: известные финансовые категории и source fallbacks повторно проверены; новая трёх-SKU regression подтвердила разделение затрат и fail-closed при отсутствии COGS. Найденных производственных ошибок нет.
- Два изолированных профиля прошли: **94 passed** для экспериментального отчёта/начислений/cross-docking evidence; **90 passed** для юнит-экономики, продажи, план-факт, v1/v2 adapters и нового multi-SKU случая.
- Полный local pytest не запускался. Несколько temp/SQLite тяжёлых тестов упёрлись в ранее зафиксированное ACL ограничение и не засчитываются в зелёный результат; общий exact-head CI будет обязателен до PR.
- Далее B00 — аудит текущей полноты источников и UI, затем ветки B/C/D по графу зависимостей.

# 2026-10-25 — ежедневная готовность, этап A02

- S00/A00/A01/A02 выполнены в отдельной ветке `codex/daily-readiness-a-foundation`, основанной на проверенном PR #712 head `698c9f8`. PR #712 и основной `main` не менялись.
- Реализованы explicit XLSX profile `ozon_accruals_xlsx_v1`, read-only CLI и сверка signed суммы периода с сохранённым `net_accrual` snapshot Period Profit. Августовский источник прочитан: 38 864 строки, все даты валидны; финансовые суммы не сохранены в Git.
- Новые тесты: **10 passed**. Полный локальный pytest не запускался из-за зарегистрированного риска Windows ACL/shared storage. Далее A03.

# 2026-10-25 — исправлено сравнение ставки в готовности сохранённого плана

- Readiness v2 сравнивает сохранённую ставку кросс-докинга и подтверждённое evidence численно через `Decimal`. Разный формат десятичной части больше не скрывает валидное подтверждение; отрицательные, нечисловые, бесконечные и несовпадающие значения fail closed.
- Добавлены два теста на равенство разных масштабов, нулевую ставку, несовпадение и некорректные значения. Связанный Windows-профиль X00–X06 и readiness: **94 passed in 3.08s**. Exact-code-head Verify [40168401653](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/40168401653) для `88ab62fb9f4cf376ba982c7cef99243e6f567ef4`: Windows/Linux по **3 647 passed**, compile на обеих ОС и Linux Docker build/runtime smoke успешны. Полный локальный pytest не запускался из-за ранее документированного риска Windows ACL/shared storage.

# 2026-10-21 — исправления R1–R3 повторного review PR #712

- Ставка в v2 сохранённом плане валидируется через Decimal equality, поэтому production float `12.0`/`12.5` корректно совпадает с evidence `12.00`/`12.50`; исходное представление допущения сохраняется.
- Adapter теперь повторно нормализует уже сохранённый allowlisted evidence без потери `rate_available` и `amount_per_unit`. Single- и batch-план могут быть открыты, снова захвачены и сохранены; строковая версия модели не теряется.
- Force refresh общего кросс-докингового окна выполняется один раз на root operation trace. Остальные SKU в той же пакетной операции используют общий cache/checkpoint и могут продолжить bounded сбор.
- Проверка без `tmp_path`: **29 passed** по adapter, unit-rate source и batch-plan service. Дополнительно напрямую выполнены пять временно изолированных repository/single/batch persistence regression cases. Широкий локальный pytest-профиль с SQLite fixtures упёрся в Windows ACL на `basetemp`; он не засчитывается как зелёный pytest. Exact-head Verify [39612452624](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/39612452624) для PR head `0e1623391ec4c6bb2e87e49d37b717f85aef68f5` прошёл: Linux и Windows по **3 645 passed**, compile на обеих ОС, Docker build/runtime smoke успешны. Есть только предупреждения GitHub Actions об устаревании Node.js 20.
- Merge, deploy, запуск бота и live Ozon API не выполнялись.

# 2026-10-21 — X00–X06 кросс-докинг реализован, PR #712 перед повторным review

- Автоматический источник считает signed начисления с корректировками за 56 завершённых дней и делит подтверждённую сумму на фактически принятые через cross-docking единицы; расходы SKU и магазина разделены. Неполнота и отсутствие пригодной ставки не превращаются в ноль.
- Ставка подключена к текущей юнит-экономике, калькулятору и планам. В сохранённых v2 снимках остаются allowlisted evidence; v1 продолжают использовать прежний расчёт. План-факт v2 учитывает ставку только со стороны плановой прибыли, фактическая выручка/количество не меняются.
- Exact code head `4f77cfef6e6725929a4b6539e376a258407e8305`, PR #712, base `7e6eabdeba34a822434e5ef417a135995628cc41`. Verify run [39591125957](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/39591125957): Windows/Linux по **3,640 passed**, compile на обеих ОС, Docker build/runtime smoke successful.
- Bounded local X05 profile: 126 passed; v1/v2 plan-fact follow-up: 52 passed. Полный локальный pytest не запускался. Независимый review packet: `CROSS_DOCKING_INDEPENDENT_REVIEW_PACKET_2026-10-21.md`. Merge/deploy, live Ozon API и запуск бота не выполнялись.

# 2026-10-21 — кросс-докинг в сохранённых и пакетных планах (X05)

- Сохранённые планы версии 2 хранят замороженную ставку кросс-докинга и allowlisted source evidence; просмотры, сравнения и экспорты не обновляют данные с Ozon. Явное обновление создаёт capture для новой ревизии/копии и сохраняет историю неизменной.
- Планы объёма считают расход кросс-докинга как ставка × планируемые успешные продажи по SKU; подтверждённый расход учитывается один раз до налога. Неизвестная ставка для строки делает прибыль/маржу набора неполными, а не нулевыми.
- Версия 1 остаётся доступна через централизованный adapter без нового расхода или сегодняшних поставок. Сравнение план-факт принимает v1/v2; подтверждённый расход влияет только на сохранённый план, а фактическая выручка, количества и их мост не меняются.
- Полнота исходного окна отделена от доступности ставки: полностью собранное окно без подходящих поставок сохраняется без числового значения; положительный плановый объём остаётся partial.
- X05 bounded-профиль: **126 passed in 3.29s** на 8 связанных тестовых модулях, включая две ставки SKU, explicit refresh, старую ревизию, sales mix, unavailable rate, comparison и exports. Полный pytest, бот/live Ozon API, merge/deploy не запускались.
- Последующий адресный профиль plan/fact + saved-plan/sales-mix/comparison после версии v2: **52 passed in 1.85s**. Первый PR CI выявил 5 legacy plan/fact regressions из-за строгой проверки версии; совместимость v1/v2 исправлена, тесты теперь подтверждают неизменность фактического моста и недоступную прибыль плана при отсутствующей ставке. Новый полный CI ожидается на следующем head.

# 2026-10-21 — подключён кросс-докинг к юнит-экономике (X04)

- Текущая экономика SKU и плановый калькулятор используют подтверждённую ставку за 56 завершённых дней: фактические signed начисления с корректировками / принятые cross-dock единицы. При доступной SKU-атрибуции применяется ставка SKU; при общих начислениях — оценка магазина, не суммируемая со SKU-частью.
- Компонент вычитается из прибыли до существующего налогового расчёта. Для USN_INCOME налоговая база остаётся прежней; для USN_INCOME_MINUS_EXPENSES расход участвует в расчёте через существующий TaxService. Цены-цели, безубыточность, предел рекламы и sensitivity пользуются тем же ядром.
- Неполная/неприменимая ставка не становится нулём и явно исключается. Текущая экономика не кэширует partial evidence; Telegram показывает период, метод, начисления/принятый объём и покрытие без ID/SKU источника.
- X04 завершён; изолированный профиль: **256 passed in 5.54s** на Windows. Полный локальный pytest, live API и бот не запускались. Далее X05 — сохранённые и групповые планы и версия evidence.

# 2026-10-20 — pure расчёт финансового среднего кросс-докинга (X02)

- Общий classifier категорий Ozon вынесен в [`ozon_accrual_fee_classifier.py`](../app/services/ozon_accrual_fee_classifier.py) и повторно используется существующим отчётом и X02.
- `CrossDockingFinancialEvidenceService` строит complete-only C56 из фактических signed leaf-начислений `/v1/finance/accrual/by-day`, не агрегирует родительские `total_amount`, различает SKU и shared costs и сводит все дни окна, включая дни без продаж.
- Чистая ставка использует только X01 фактически принятые cross-dock units; sales count в контракте отсутствует. Есть SKU rate либо store estimate при общих расходах; observed zero, net refund, отсутствие поставок и любые пробелы остаются разными состояниями.
- Связанный targeted profile: **102 passed in 1.70s**. Полный pytest, live Ozon API, бот, merge и deploy не запускались. X02 завершён; durable collection/cache/checkpoint и production wiring остаются X03–X04.

# 2026-10-20 — реализован bounded read-only источник кросс-докинг-поставок

- X00 закрыт в ограниченной области: две пользовательские сверки подтвердили построчный `fact_quantity` для полной/частичной приёмки и дату завершения одной nested supply по `state_updated_date`; `created_date`, planned dates, `approved_quantity` и summary totals не заменяют эти поля. Доменное правило пользователя: одна supply = один товар.
- X01 добавляет нормализацию единиц по SKU и read-only сбор list/get/accepted act/product данных через уже существующие Seller API adapters. Single-supply completed cross-dock receipts проходят только при точном совпадении order/supply/act, одном SKU и согласованных количествах; все неоднозначности дают `INCOMPLETE` и `total_units=None`.
- Сбор ограничен 64 запросами, 60 секундами и одним HTTP attempt на endpoint; полная cursor pagination, 50-ID detail batches, cutoff по отсортированному `state_updated_date`, timezone `Europe/Moscow`. При исчерпании лимита частный знаменатель не публикуется; durable resume/checkpoint и подключение к калькулятору остаются X03–X04.
- Windows runtime не имел IANA timezone data; добавлен `tzdata` dependency. Новые тесты: **34 passed in 0.54s**; вместе с существующей диагностикой актов — **53 passed in 1.03s**. Syntax-only compile и `git diff --check` прошли. Live Seller API, бот и полный локальный pytest не запускались.

# 2026-10-20 — закрыт X00 для фактического количества кросс-докинга

- Официальные Seller API schemas list/get/act и два пользовательских примера (500/500 и 200/100) подтверждают read-only путь от completed order до одного SKU и фактически принятого `fact_quantity`. `approved_quantity` и summary-level quantity могут расходиться с построчной фактической величиной и не используются как denominator.
- Для completed заявки с единственной вложенной completed cross-dock supply `state_updated_date` совпал с датой завершения в интерфейсе Ozon; `created_date` акта на проверенном частичном примере был на день раньше. Для multi-supply order individual completion date не доказана; такие данные X01 обязан пометить неполными и не включать в denominator.
- Пользовательское правило: одна supply относится к одному товару/SKU. X01 начат. Юнит-экономика, storage и production integrations не изменены.

# 2026-10-20 — исправлено разрешение ID поставки в ID заявки

- В диагностике акта пользователь вводит `supply_id`, но `/v3/supply-order/get` и `/v1/supply-order/act/summary/get` требуют `order_id`. Добавлен bounded read-only поиск заявки по списку и точная сверка вложенного `supplies[].supply_id`; в оба метода передаётся только найденный `order_id`.
- При отсутствии совпадения или ошибке поиска диагностика не подставляет чужую заявку. Показ HTTP статуса безопасен и не раскрывает тело ответа.
- Это исправление только диагностического запроса. Оно не включает поставки в расчёт юнит-экономики: X00 остаётся заблокированным по дате фактической приёмки и универсальной семантике принятого количества. `tests/test_experimental_supply_act_diagnostic.py`: **19 passed in 0.43s**; syntax-only compilation и `git diff --check` прошли; полный local pytest не запускался из-за известного ACL/shared-storage ограничения. Verify run **39419764407** для code SHA `7784d457528dd7b8c3f0b433668ed30768bb25ab` прошёл full-verification и Windows: полные тесты, compilation и production Docker build/runtime smoke успешны.

# 2026-10-20 — расширенная read-only диагностика актов поставки

- Экспериментальная проверка читает `/v3/supply-order/get`, `/v1/supply-order/act/product/get` и ограниченно пытается прочитать `/v1/supply-order/act/summary/get` для введённого ID. Выводятся только типы безопасных полей, статусы, даты и количества; SKU, названия, штрихкоды и ID не раскрываются. `created_date` и дата изменения статуса заявки пока не считаются датой фактической приёмки каждой вложенной поставки.
- Для принятого акта из пользовательского отчёта API вернул `declared_quantity=500`, `fact_quantity=500`, `approved_quantity=0`; интерфейс Ozon показывает 500 принятых единиц. Это подтверждает соответствие `fact_quantity` одному наблюдению, но `approved_quantity` нельзя считать accepted units. Автоматическая ставка в калькуляторы не подключалась.
- Официальная документация пользователя подтвердила list cursor `last_id`, batch get до 50 заявок и `supplies[].is_crossdock`; диагностика читает и обезличивает `/v3/supply-order/get`, ограничивает ответ для Telegram. Targeted `tests/test_experimental_supply_act_diagnostic.py`: **14 passed in 0.51s**; exact-head Verify run **39407794793** на SHA `e9e2f2cec4c55b763660af8dca07ef6f9f8bed10` прошёл: Linux и Windows по **3,534 passed**, compilation и production Docker build/runtime smoke успешны. Автоматический расчёт всё ещё ждёт фактическую сверку даты и количества в API. Полный pytest локально не запускался из-за ACL/shared-storage инцидента.

# 2026-10-19 — диагностический запрос товаров из акта FBO

- В экспериментальном меню добавлена read-only проверка `/v1/supply-order/act/product/get` по введённому `supply_id`. Запрос выполняется только после явного ввода, tenant scope привязан к текущему магазину, ввод истекает через 5 минут, сетевой вызов ограничен 15/25 секундами и двумя попытками.
- Ответ выводит значения и coverage `declared_quantity`, `approved_quantity`, `fact_quantity`, `unidentified_quantity`; SKU, названия, штрихкоды, `act_id` и `supply_id` не попадают в сообщение. Поле `fact_quantity` не интерпретируется как принятое количество без подтверждённой семантики.
- Это разовая диагностика по ID, а не штатный ручной ввод юнит-экономики. `/v1/supply-order/act/product/get` не даёт дату/статус; автоперечисление кросс-докинговых поставок ещё не реализовано. X00 остаётся частично заблокированным до точного контракта списка/деталей поставок и даты фактической приёмки.
- Новые регрессии: `tests/test_experimental_supply_act_diagnostic.py` — **6 passed**. Связанный профиль с `tests/test_telegram_help_discovery.py` и отдельными `AI_ASSISTANT_STORAGE_ROOT`/pytest basetemp — **67 passed in 3.43s** на Python 3.12. `compileall` упёрся в известный Windows ACL при записи `__pycache__`; syntax-only compile всех 6 изменённых Python файлов и `git diff --check` прошли. Полный pytest локально не запускался. Первый exact-head CI выявил устаревшее ожидание состава меню (Linux: 3 525 passed, 1 failed); ожидание обновлено. Follow-up exact-head Verify run **39313014256** прошёл на Linux и Windows: **3 526 passed** на каждом runner, compile и production Docker build/runtime smoke успешны для code SHA `37c07dfb7779eece976210fb3dba6ac4ead27f8f`.

# 2026-10-19 — исправления repeat review planning workspace (R18–R19)

- Цель из рекламного калькулятора хранится в явном session assumption и переживает возврат, применение, сохранение, перезапуск и исторический просмотр; при обновлении существующего плана сохраняется последняя введённая цель.
- Refresh сохранённого single-плана прекращается до переноса ручных значений, если изменилась карточка (`product_id`, `offer_id`, SKU), магазин или owner scope. Перед CAS update точная identity сверяется также для планов без sales mix; прежняя ревизия остаётся нетронутой.
- Добавлены R18/R19 public-flow регрессии. Связанный профиль: **86 passed in 1.99s**; `compileall -q app tests` и `git diff --check` прошли. Code commit `0f359c6c88490416634bc0a0bf57f4f8cb00fcea` прошёл Verify runs [39250181095](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/39250181095) и [39250193274](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/39250193274): полные Windows/Linux suites, compile и production Docker build/runtime smoke успешны. Пользовательские `data/tasks.json` и `data/users.json` сохранены вне Git; независимый review и merge/deploy не выполнялись.

# 2026-10-19 — исправления repeat review planning workspace (R16–R17)

- Legacy/default tenant без активного Ozon-магазина теперь везде использует канонический `store_id=""`: сохранённые планы, readiness field/quantity edits, CSV/JSON и comparison snapshots. Подтверждённые store scopes по-прежнему сверяются точно.
- Для single-SKU калькулятора заданная целевая маржа хранится отдельно от удаляемого экрана результата и переносится в сохранённый план/восстановленный сценарий. Исторический рекламный предел использует сохранённую цель после применения рассчитанной цены или возврата к сценарию.
- Добавлены регрессии R16/R17. Связанный Windows профиль: **142 passed in 2.97s**; `compileall -q app tests` и `git diff --check` прошли. PR #708 exact-head CI и повторный review ещё не выполнены; merge/deploy не выполнялись. Пользовательские `data/tasks.json` и `data/users.json` не включались и не изменялись.

# 2026-10-19 — исправления повторного review planning workspace (R11–R15)

- Сравнение сохранённых планов проверяет, что их `calculation_version` поддерживается активным калькулятором, прежде чем пересчитывать сохранённые inputs. Несовместимые версии сохраняют видимые input differences, но скрывают derived metrics и не вызывают calculator.
- После refresh single/batch планов transient editor context привязан к точному документу и CAS-ревизиям, поэтому последующие локальные правки сохраняют возможность явного обновления исходной ревизии. Идентичность SKU нормализует пустой store ID в поддерживаемом legacy tenant scope.
- Сравнение расходов видно в Telegram; длинные списки изменений читаются страницами из одного owner/store snapshot. Добавленные/удалённые SKU показываются раньше изменений полей. Внешние источники не перечитываются.
- R11–R15 покрыты регрессиями. Связанный Windows-профиль: **62 passed in 3.85s**; `compileall -q app tests` и `git diff --check` прошли. Кодовый commit `ecb1709793d6d6d1541332211fbe42e38624fba0` прошёл Verify `39232047110` и `39232057817`: полные Windows/Linux suites, compile и production Docker build/runtime smoke успешны. Данные `data/tasks.json` и `data/users.json` не менялись (хэши совпали с предыдущими значениями). Новый docs-only head проверяется отдельно; repeat review и merge не выполнялись.

# 2026-10-19 — выполняется программа H–O на feature branch

- Рабочая ветка `codex/planning-workspace-20261019`, база merged `main` `722f368526c278b701cbfd69f3dbb9a474d52386`; документационный checkpoint `79fc0a72`.
- H00–H04: управление локальным экземпляром Telegram через token-scoped kernel lock, безопасный loopback stop, фактическую готовность polling и PowerShell launch/status/stop; PR #705 Verify прошёл Windows/Linux и Docker smoke.
- I00–I05: tenant-scoped saved-plan SQLite repository, версионные сохранения, исторический просмотр/продолжение и CRUD через публичный Telegram handler; PR #706 Verify прошёл Windows/Linux и Docker smoke.
- J00–J02: bounded ad-cap solver, Telegram для single/batch и исторический read-only просмотр saved-plan cap. Локальный профиль J: **63 passed**.
- K00–K03: manual sales-mix для сохранённого плана, построчная экономика, однократный aggregate tax, список фиксированных расходов, partial subtotal и пояснённая сумма индивидуальных ad caps. Связанный K профиль: **27 passed**.
- L00–L04: ограниченная plan/fact projection поверх finalized exact-SKU query, revenue bridge, явная несопоставимость прибыли, immutable snapshot и выгрузка без повторного query. L profile: **36 passed**.
- M00–M03: отдельные статусы готовности расчёта, исторических допущений и факта; прямой переход к одному SKU-полю/неизвестному Q; preview и CAS перед новой revision. Устаревшая правка безопасно конфликтует с конкурентным сохранением.
- N00–N03: сравнение исторических revisions и экспорт сохранённого плана, рекламного лимита, sales mix и сравнения через общий sender; при несовместимых результатах денежная delta прибыли/маржи скрыта.
- O00: межмодульные public flows — **249 targeted tests passed**. PR #705–#708 Verify runs прошли полные Windows/Linux suites (**3,443 / 3,454 / 3,466 / 3,497 passed** на соответствующих code heads), compile и production Docker smoke. Финальный exact-head Verify для PR #708 и независимый architecture review отслеживаются в PR и review handoff.
- Запрошенный полный локальный pytest остановлен навсегда в этой рабочей копии после инцидента **3431 passed, 28 failed** и изменения локальных `data/tasks.json`/`data/users.json`; точных исходных копий нет, восстановление не выполнялось. Не повторять full local suite. Требуются зелёные Windows/Linux exact-head GitHub CI и Docker smoke.
- H/I focused profile до J: **99 passed**; compileall, PowerShell AST и diff-check были успешны. Полный локальный pytest прогон после workaround завершился **3431 passed, 28 failed**: семь multi-tenant тестов из-за повторного использования общей тестовой storage, ещё 21 из-за Windows `%TEMP%` ACL/WinError 5. Он также перезаписал локальные корневые `data/tasks.json` и `data/users.json`; автоматическое восстановление не предпринималось.
- Контрольные суммы исходных файлов до этого прогона: tasks `AC6E856BD17E17029151C25C0D29DE414E553CE7C3607CB8DED9EC22E052110F`, users `900FFAE4759D8CCE6A8E462C8F6B9C3CF64DC88F3388EDB7CDBEB157736AF63A`. Наблюдаемые после прогона: tasks `8F7FFF206A4748DE6EFB3E5DCABABD07E3341188A7326383A21D966B73710698`, users `0B12986702D5C62B8A410EE4B3B3228923FF72BA897F18FF62FEF556CDA88409`. Оба локальных файла и lock оставлены вне Git; точной исходной копии для восстановления в доступных scratch-каталогах не найдено. Не запускать локальный полный suite повторно.
- Ozon/Telegram API, live bot и `.env` не использовались. Пользовательские JSON и ACL scratch paths сохранены вне Git; SHA-256 данных приведены в журнале. Продолжение по `LUNA_PLANNING_WORKSPACE_PROGRESS_2026-10-19.md`; merge/deploy не выполняются.

## Исторический checkpoint подготовки 19.10.2026

- Актуальный baseline подготовки: `main` `722f368526c278b701cbfd69f3dbb9a474d52386`. PR #702 уже слит и включает периодную аналитику, A–G и review fixes R1–R10; записи ниже о незавершённом merge относятся к прежним checkpoint.
- Merged-main Verify `39165543772` successful: Windows/Linux full verification, compileall, production Docker build/runtime smoke. При подготовке повторно проверены GitHub metadata PR и статусы jobs; новый полный pytest не запускался.
- `LUNA_PLANNING_WORKSPACE_TASK_2026-10-19.md`: программа H–O, 36 этапов — lifecycle запуска, сохранённые планы, рекламные пределы, manual sales mix, план/факт, готовность, сравнение/экспорт, приёмка. Реализация выполняется на feature branch; фактические результаты и открытые этапы — в `LUNA_PLANNING_WORKSPACE_PROGRESS_2026-10-19.md`.
- Подготовка изменяет только документацию. Пользовательские JSON, lock и temporary directories сохранены; действующие financial/tax/scenario contracts не менялись. Новые planning persistence contracts должны получить отдельный аддитивный ADR при реализации I00. Merge/deploy/реальный запуск в новое ТЗ не входят.

# 2026-10-18 — исправления повторного review R9–R10

- Batch runtime публикует стартовый план и все обновления через атомарное сравнение с исходной версией. Ручная правка и подтверждение рекламной доли сверяют текущую версию под lock; успешный refresh удаляет ожидающие изменения, рассчитанные из предыдущей версии. Новая сборка не переиспользует тот же batch id/version для другого содержимого. Проверяются границы tenant, ticket, TTL и монотонного `version + 1`.
- Sensitivity runtime строит одну freshness projection для экрана, переноса ячейки и выгрузок. CSV/JSON показывают актуальный статус/причину и разрешение переноса; исходный статус расчёта остаётся в `snapshot_status`. Для уже истёкшего origin используется сохранённый возраст источника и время создания чувствительности, повторного запроса Ozon нет.
- Регрессии R9/R10 добавлены в batch и sensitivity runtime tests. Связанный локальный профиль: **99 passed**; compileall и `git diff --check` успешны. Exact-head Verify `39164302283` для `20ea6f80e7c69329c51ced8fc36c2b41772a3c09` прошёл Windows и full-verification, включая полный pytest и production Docker smoke. Повторная проверка изменений не выявила новых замечаний. PR #704 открыт, не слит и не развёрнут.
- `data/tasks.json`, `data/users.json`, их lock и локальные временные каталоги pytest сохранены и не включены в эти изменения.

# 2026-10-18 — исправления A–G по review R1–R8

- Реализованы восемь исправлений для PR #703: корректное сохранение контекста single/sensitivity; version/ticket-guard от позднего batch refresh; владелец-ориентированный reset новых transient runtimes; дочерние лимиты 120 секунд/128 запросов для product overview; передача родительского operation trace в batch build/refresh; bounded LRU/TTL чувствительности; freshness projection для экрана и экспорта; синхронизация missing/invalid input при пересчёте.
- Проверки локально: **86 targeted tests passed**, `compileall -q app tests` и `git diff --check` успешны. Полный Windows pytest дал **3 030 passed, 21 failed, 369 errors**; локальный прогон ограничен ACL `PermissionError [WinError 5]` на temporary paths. Code commit `664a370a117251a88297e57668a8ba721a80555c` повторно проверен: новых замечаний R1–R8 нет; оба Windows/full-verification CI runs `39161924581` и `39161920417` прошли. Merge/deploy не выполнялись.
- Пользовательские `data/tasks.json` и `data/users.json`, lock-файл и ACL-limited временные каталоги сохранены вне списка изменений.

# 2026-10-17 — выполнение программы Luna A–G начато

- Владелец поручил выполнить `LUNA_LONG_RUN_PRODUCT_TASK_2026-10-17.md` до готовых PR с зелёным CI; merge и deploy запрещены. Журнал этапов: `LUNA_LONG_RUN_PROGRESS_2026-10-17.md`.
- A00 проверен: PR #697 открыт на head `3f7923ced48ba9434fdf5930d1f55431e0eacedd`, base `main` `c55434327f50134324a5ca58e2f084854b809832`. Рабочая ветка `codex/product-workbench-20261017` содержит подготовительный документальный commit `91aac988aa067082434704095cc61a2400b06159` поверх PR head.
- Данные `data/tasks.json`, `data/users.json`, временные каталоги pytest и lock-файл сохранены. Хэши пользовательских JSON записаны в журнал.
- A00–A01 VERIFIED. Review подтвердил: legacy `query_all()` — full-catalog/history lifecycle; price source сбрасывает собственный 60s/64-attempt trace и ждёт inflight фиксированные 61s; outgoing document sender подписывает каждый файл как cost CSV. Это prerequisites для новых путей, не объявлены production regressions.
- A00–A02 VERIFIED. Общий trace поддерживает parent/child deadline и atomic attempt reservation; UnitPriceScenarioSource умеет наследовать его для сгруппированных запусков, ограничивает in-flight wait и не публикует/кэширует поздний результат после cancel. Standalone 60s/64-attempt defaults сохранены.
- A00–E04 VERIFIED; PR #698–#701 остаются открытыми и не слитыми. Exact-head E code и documentation CI зафиксированы в журнале.
- F00 VERIFIED на локальном профиле **27 passed, 1 deselected** (единственный `tmp_path` тест исключён из-за известного Windows ACL при отключённом pytest tmpdir); `compileall` и `git diff --check` прошли. Коммит F00 `057d439` на ветке `codex/product-workbench-module-f`, base — E acceptance head `f598d30`.
- F00–F01 verified locally: bounded period-operation diagnostic view and strict allowlisted `support_diagnostic` JSON. F01 commit `59432ef`; export is owner/store/TTL-bound, reads the cached report only, and masks identifiers.
- F02 verified locally in commit `3e4af5a`: read-only main-menu version screen and the same validated process revision/start time in support JSON; Windows launch script captures Git revision/start time once per launch, and Docker Verify injects the image revision. Profile **58 passed, 1 deselected**; compileall and diff-check passed. The excluded test is the existing ACL-bound `tmp_path` worker-stack test. Exact-head acceptance remains pending.
- F03 verified locally: regressions cover exact attempt counters and secret-free public traces for HTTP 429/timeout, expiry without source refresh, and support-file delivery failure. The combined F00–F03 profile is **77 passed, 1 deselected**; compileall and diff-check passed. The excluded test is the existing ACL-bound `tmp_path` worker-stack test. Exact-head CI is pending.
- G00 verified locally: new public Telegram acceptance connects overview/incomplete filter → exact selection → batch target → local cost assumption → sensitivity → batch/sensitivity CSV/JSON; a period path connects comparison → CSV/JSON → safe support diagnostic. All steps reuse source snapshots, and the main-menu test confirms legacy sections remain accessible. Focused G00 profile: **54 passed, 1 existing ACL-bound `tmp_path` test deselected**. Full exact-head CI remains pending.
- Текущий этап G01: полный pytest, compileall, diff/secret/data review, exact-head Windows/Linux CI and Docker build/runtime smoke.

# 2026-10-18 — программа A–G завершена и передана на независимый review

- PR #698–#703 остаются открытыми stacked PR; #697 — исходная зависимость. Последние проверенные code heads A/B–F имеют зелёные Verify; F PR #702 exact head `55db3e60fda3c3080051da2fbea1902091a4bfff`, run `39069168434`.
- G00/G01 прошли локальные acceptance/regression проверки; exact code head `12447d4cb48823fea938513fbb16dc4f41a080c2` и review-handoff head `1a6664429533e092b239a6240e0b1173358f0cfa` прошли Verify `39069249065` и `39069517726` соответственно (Windows, Linux full verification и Docker smoke). Review handoff: `LONG_RUN_REVIEW_HANDOFF_2026-10-17.md`.
- Полный локальный Windows pytest заблокирован существующим ACL на временные каталоги (`3 018 passed, 22 failed, 369 errors`); ограничения и исправленная stale menu assertion записаны в журнале. `data/tasks.json`, `data/users.json`, их lock и временные каталоги сохранены вне PR.
- Слияние и развёртывание не выполнялись. Перед слиянием нужен независимый архитектурный review stacked PR в порядке зависимостей и зелёный CI на текущих heads.

# 2026-10-17 — подготовлен большой пакет новых функций для Luna

- Поручение владельца: длительная автономная разработка, включая новые возможности продукта. Подготовлено `LUNA_LONG_RUN_PRODUCT_TASK_2026-10-17.md`: 7 крупных модулей A–G, 32 этапа, ориентировочно 12–24 инженерных часа; фактическая длительность не является критерием приёмки.
- Новые функции программы A–G: A–D реализованы; B добавляет bounded обзор выбранных товаров с фильтрами, C — пакетный план до 10 SKU, D — локальную чувствительность и матрицу цены/себестоимости/рекламы. PR #698/#699 открыты для review; D PR готовится. E–G продолжаются по журналу `LUNA_LONG_RUN_PROGRESS_2026-10-17.md`.
- Основание: `LONG_RUN_PRODUCT_AUDIT_2026-10-17.md`. Выявлены реальные prerequisites: `query_all` включает history decoration и весь каталог; source калькулятора начинает собственный budget; outgoing file caption привязан к cost CSV. Они описаны как проверенное поведение, без неподтверждённых P1/P2.
- GitHub проверен 17.10: PR #697 открыт и не слит, head `3f7923ced48ba9434fdf5930d1f55431e0eacedd`, base main `c55434327f50134324a5ca58e2f084854b809832`. Новая реализация должна явно учитывать зависимость, не повторять N00–N08 и не сливать PR автоматически.
- Проверка подготовки: шесть числовых примеров ТЗ сверены настоящими `UnitPriceScenarioService`/`TaxService` на синтетических входах. Это проверка примеров, не тестирование новых функций. Для markdown-подготовки полный pytest не повторялся; production code и пользовательские `data/tasks.json`/`data/users.json` не изменялись.
- Следующий шаг: после команды владельца выполнять новое ТЗ с A00, вести checkpoint journal и завершить на небольших PR с CI и независимым review. Восстановление после compaction и работа с блокерами закреплены в ТЗ.

# 2026-10-15 — N08 принят; периодная аналитика готова к архитектурному review PR

- N06 code commits `e9372b1` (`Add period profit analytics Telegram views`) and `9a6523c` (`Limit analytics overview to confirmed top contributions`) добавили кнопку «Аналитика периода», экраны сравнения, денежного моста и вклада SKU, а также переходы к полноте/исходному отчёту/существующему выбору товара. Первый экран показывает не более трёх крупнейших подтверждённых вкладов; при недоступном мосте показывает ограничение. Детали не повторяют Ozon-запросы.
- Снимок требует точный tenant и owner, ограничен 64 отчётами/600 секундами, deep-copy читается атомарно. В нём остаются только проекции метрик, моста и максимум пяти строк лидеров; управляющие символы в SKU-метках очищаются, длина ограничена.
- N06 локальный профиль: 75 passed, 1 factory test исключён из прогона из-за WinError 5 на доступе Python к изолированному временному каталогу. Factory wiring regression прошла в полном N08 CI. `compileall -q app tests` и `git diff --check` прошли.
- N08 exact code SHA `05bac9b5be203970f0d40b930fe8cc1b6036415d`: Windows **3 268 passed**, Linux **3 268 passed**, compileall, production Docker build/runtime smoke — success (Verify runs `38755542971` and `38755551644`). Architecture review: новый аналитический contract остаётся read-only поверх finalized summaries; новых источниковых запросов, финансовых пересчётов, постоянного хранилища или изменения core finance pipeline нет. Обнаруженная устаревшая presentation assertion исправлена, открытых review threads нет. PR #697 открыт и не слит; решение о слиянии остаётся следующему ревьюеру.
- `data/tasks.json` и `data/users.json` остаются сохранёнными незакоммиченными пользовательскими изменениями. Следующий шаг — независимый review/merge PR #697; развёртывание не выполнялось.
- N07 test commit `db73c64` (`Verify period analytics cache interleavings`) добавил deterministic `Event` regression: пока callback читает и копирует snapshot внутри атомарного lock, новый расчёт заполняет LRU и вытесняет старый report. Текущий читатель завершает READY без KeyError; после записи старый callback controlled-expired, новый открывается; cache остаётся ровно в лимите 64. N06+N07 suite: **76 passed, 1 factory test deselected**. Отдельные budget/dedup/Performance наборы: **13 passed, 68 deselected**. `compileall -q app tests` и `git diff --check` успешны.
- N08 локальный full suite на предыдущем code SHA `bbdebf4`: **2 876 passed, 22 failed, 369 errors in 71.91s**; обычный pytest также завершился `PermissionError (WinError 5)` при обходе basetemp. Диагностический запуск отключал только финальную cleanup-функцию pytest, чтобы получить сводку; причины всех локальных ошибок этим не установлены. Локальный прогон не принят как приёмка; итог подтверждён чистым exact-code-head CI ниже.
- Exact-head CI на промежуточном `c36efb6df6251c470bb0aad887fe2ca3717aa38e` установил одну устаревшую строку ожидания в `test_v1229_existing_comparison_percentage_keeps_its_own_meaning`; исправлено без изменения production-поведения, денежные проверки 40 000 ₽ и 10% сохранены. Связанный локальный модуль: **10 passed**. На окончательном code SHA `05bac9b5be203970f0d40b930fe8cc1b6036415d` обе платформы прошли по **3 268 тестов**, compileall и Docker build/runtime smoke успешны.


# 2026-10-15 — N05 вклад SKU завершён

- N05 code commit `6beaebe8b23f90ca39d4ec6b105c7a191ef801e7` (`Add period profit SKU contributions`) добавил read-only разбор `summary.products` уже рассчитанных current/previous периодов. Однозначное соответствие принимает точную SKU/catalog-SKU, уникальный offer или пару product+offer; конфликтующие и неоднозначные строки не объединяются. Отсутствие counterpart не превращается в нулевую прибыль: отчёт выводит ограниченный список несопоставленных SKU и считает неполноту покрытия.
- Production final query attaches `sku_contribution` к тем же finalized результатам, без новых Ozon/Performance запросов и без N+1 расчёта. Два списка показывают максимум пять подтверждённых ростов и снижений; магазинный delta сходится как сумма сопоставимых SKU и арифметический остаток без распределения остатка по товарам.
- N05 проверочный набор: **67 passed in 1.32s**, включая production-wrapper, source identity recovery, historical cost and contract regressions; `compileall -q app tests` и `git diff --check` прошли. Финансовые значения, налоги, COGS и существующие source loaders не изменялись.
- N04 code commit `710ea8994881fc10a4a09a3f6ef11d7c7426f2c0` (`Add reconciled profit change bridge`) подключает проверяемое `ΔN−ΔC+ΔK−ΔT` и E только при полном покрытии. Его **100 связанных тестов прошли**; compileall и diff check успешны.
- `data/tasks.json` и `data/users.json` остаются сохранёнными пользовательскими изменениями. Следующий этап: N06 — scoped Telegram-снимки и навигация по отчёту.

# История N03–N04

- N04 code commit `710ea8994881fc10a4a09a3f6ef11d7c7426f2c0` (`Add reconciled profit change bridge`) подключает `profit_bridge` к finalized wrapper. Для разрешённых V3/V4 проверяются обе стороны равенства `P_B=N−C+K−T`; дельты раскладываются в `ΔN−ΔC+ΔK−ΔT`. `ΔN` раскрывается как `Δrevenue + Δ(other net accrual)` внутри одной строки.
- Сумма B-вкладов проверяется против authoritative delta; signed rounding допускается до 0.01 ₽ и показан отдельно. Большее расхождение или неподдержанная profit scope делает bridge недоступным. E отдельно проверяет полное покрытие и `P_E=P_B−E` для обеих сторон. Отказ внешних расходов не скрывает подтверждённый B.
- Проверки N04 + предыдущие contract/query integration: **100 passed in 2.54s**; `compileall -q app tests` и `git diff --check` прошли. Неизвестные расходы/категории не вычитаются повторно, новые классификаторы начислений не добавлены.
- `data/tasks.json` и `data/users.json` остаются сохранёнными пользовательскими изменениями. Следующий этап после N04: N05 — SKU-вклад и reconciliation на уже полученных product rows.

- Ветка `codex/luna-store-analytics-task-20261015`; N03 code commit `a02a42c29e11bbef93f824579dd9a15fbe5e796c` (`Add period comparison metrics`), поверх N02 `07c6c99eaea471f5b002e18b5554034af8d5180e`.
- Production wrapper добавляет `comparison_metrics` поверх N02 contract. Суммы/штуки показывают signed delta; процент изменения делит на абсолютную предыдущую базу, при нуле процент undefined. Изменение маржи — в процентных пунктах. Доли от выручки формируются только при известной положительной выручке.
- Налог/прибыль подчиняются policy/scope gate; подтверждённые продажи и независимые метрики могут сравниваться при смене налоговой policy. Частичные внешние расходы видны как partial estimate без delta. Большие количества остаются целыми числами, арифметическое переполнение даёт недоступную дельту без Infinity.
- Проверки N03 вместе с N02/N01 integration boundary: **89 passed in 2.30s**; `compileall -q app tests` и `git diff --check` прошли. Канонические summary и прибыль не изменяются.
- `data/tasks.json` и `data/users.json` сохранены вне коммитов. Следующий этап: N04 — сверяемый денежный мост ΔN/ΔC/ΔK/ΔT/ΔE.

# 2026-10-15 — N02 finalized comparison contract завершён

- Ветка: `codex/luna-store-analytics-task-20261015`, основание `main` `c55434327f50134324a5ca58e2f084854b809832`; N02 code commit `07c6c99eaea471f5b002e18b5554034af8d5180e` (`Add finalized profit comparison contract`).
- N02 вводит read-only проекцию уже finalized summary двух соседних равных периодов. Валидирует период against request, tenant, tax policy, profit scope и component flags; конфликт блокирует только сравнение B/E и сохраняет независимые метрики.
- Применённый Return COGS учитывается только по явному результату final application; подтверждённый K=0 требует `return_cogs_profit_applied=false`, отсутствие суммы и `tax_recomputed=false`. Для прошлого периода используется тот же final application и существующий external-expense evidence/adjustment service; неполное/недоступное E не блокирует B.
- Проверки: 80 профильных query/contract/finalization/request/presentation regressions passed in 2.11s; `compileall -q app tests` и `git diff --check` прошли. Существующий `tests/test_external_operating_expense_coverage_v1261_v1270.py` локально не дал итоговой сводки: семь tmp_path setup errors и pytest cleanup `PermissionError (WinError 5)` на basetemp. N08 CI остаётся обязательным.
- Полный suite отложен до N08 exact-head проверки. `data/tasks.json` и `data/users.json` остаются незакоммиченными пользовательскими изменениями. Следующий этап: N03 — арифметика сравнений, денежных долей и маржи в процентных пунктах.

# 2026-10-15 — N01 исправления сравнения завершены

- N01 code commit: `66d79d6a87c6f3509e187f2a2e5b2441e270086f` (`Keep current profit when comparison is unavailable`), поверх N00 commit `96c3b843621979a1da356d9a0c4363a7b2ff4bb6`.
- A1: production final wrapper и base-only query сохраняют current при сбоях необязательной previous ветки; ошибка mandatory current остаётся fail-closed. Runtime делает один вызов и больше не запускает current повторно при любой ошибке compare-path. `comparison_status`/безопасный код и Telegram-предупреждение указывают недоступность сравнения.
- A2: comparison builder отклоняет пропущенную, boolean, строковую, не конечную или переполняющую арифметику прибыли; поддерживает finite int/float/Decimal, конечный отрицательный результат и известный 0. Scope flags требуют настоящих bool.
- A3: compact и verbose тексты обозначают дельту как прибыль до внешних расходов. Не вычисляется ложная E↔B дельта.
- Targeted query/runtime/final-application/Return COGS/presentation suite: **128 passed in 2.14s**; `compileall -q app` и `git diff --check` успешны. Полный suite отложен до N08 exact-head проверки. PR #697 теперь содержит подготовку ТЗ, N00 и N01; перед merge требуется Architecture Review.
- Незакоммиченные `data/tasks.json` и `data/users.json` сохранены, не staged.

# 2026-10-15 — N00 аналитики прибыли завершён

- Реализация продолжается на docs-ветке `codex/luna-store-analytics-task-20261015`, основанной непосредственно на слитом `main` `c55434327f50134324a5ca58e2f084854b809832`. PR #697 с исходными ТЗ/аудитом открыт; ветка не устарела и кодовая реализация ещё не менялась.
- N00 подтвердил production chain: `period_profit_factory` создаёт base `PeriodProfitQueryService`, оборачивает в `PeriodProfitFinalApplicationQueryService`; runtime вызывает final wrapper, затем compact formatter. Base query остаётся base-only compatibility path.
- Production wrapper отключает comparison в base query, финализирует current Return COGS/внешние расходы и строит сравнение. Ошибка previous summary уже сохраняет current; ошибка прошлых возвратов/анализа/application выходит как общий error, после чего runtime повторяет current. Base-only query также возвращает optional previous summary error напрямую. Текущий compact текст может показывать adjusted profit рядом с неподписанной base comparison.
- Исходные focused tests: `9 passed in 0.48s`. A1–A3 остаются открытыми для N01. Текущие локальные изменения `data/tasks.json` и `data/users.json` сохранены и не staged.

# 2026-10-15 — PR #696 слит; подготовлено ТЗ следующего пакета

- PR #696 слит в `main` squash-коммитом `c55434327f50134324a5ca58e2f084854b809832`. После fetch прямой diff деревьев reviewed head `fc15b9c` и `origin/main` пуст. Прежние записи «PR открыт» ниже являются историей.
- Владелец выбрал приоритеты по аудиту. Аудит `NEXT_DEVELOPMENT_AUDIT_2026-10-15.md` воспроизводит A1–A3 в сравнении периодов; production wrapper уже сохраняет current при ошибке прошлого summary, но отказ прошлых возвратов всё ещё приводит к повтору current через runtime fallback.
- Исполняемое ТЗ: `LUNA_STORE_ANALYTICS_DEVELOPMENT_TASK_2026-10-15.md`, N00–N08. Сначала подтверждённые fixes и единая база сравнения, затем таблица метрик, денежный мост, вклад SKU и связанные scoped Telegram views. **Реализация не начата.**
- Подготовка — только документация. Существующие comparison/query/runtime-fallback tests: **9 passed in 0.48s**; fake-only probes без Ozon/Telegram/business writes. Полный pytest не запускался. Пользовательские `data/tasks.json`/`data/users.json` сохранены.

# 2026-10-15 — Исправлена обработка цены с завершающими нулями в PR #696

- `UnitPriceTargetPlanningService` теперь без потери точности нормализует только завершающие десятичные нули исходной цены до сетки копеек. `11.110` и `11.11` ведут к одинаковому подбору; `11.111` остаётся некорректной исходной точкой для копеечной сетки. Парсер списка цен не ослаблен.
- Добавлены тесты Decimal/string scale и полного Telegram-пути после редактирования цены. Четыре связанных модуля — **87 passed in 1.19s**; `compileall -q app tests` и `git diff --check` прошли.
- Code SHA `4b7839caf54650e672b4410ee21bc1b64c627eff` прошёл Verify runs `38728949431` и `38728942708`: Windows — **3 204 passed** (47.61s и 36.50s), Linux — **3 204 passed** (11.21s и 12.52s); compileall и Docker build/runtime health-check успешны. Локальный полный pytest не дал итоговой сводки: до завершения вывел ошибки/падения и pytest получил `PermissionError (WinError 5)` при перечислении basetemp; результат локального запуска не считается приёмкой. Пользовательские `data/tasks.json` и `data/users.json` не включены в commit.

# 2026-10-15 — PR #696: исправлена последняя находка repeat review

- Planner теперь проверяет ограниченные меньшие цены даже если максимальная цена проходит цель. Из прошедших проб выбирается самая низкая, затем результат уточняется и повторно подтверждается прямым калькулятором. Регрессии фиксируют пример: комиссия 50%, текущая цена 500 ₽, цель 50% → найдено 0,02 ₽ и цель проходит.
- Code commit `007bd5a01a53d8451f8fe291810c76c55467b5c6` прошёл Verify runs `38726919355` и `38726911253`: Windows и Linux — **3 197 passed**, compileall и production Docker build/runtime smoke — success. Четыре связанных модуля — **80 passed in 1.15s**. Локальный full pytest дал **2 808 passed, 21 failed, 368 errors** с `PermissionError (WinError 5)` при обходе общего Windows pytest temp root; этот запуск не принимается как проверка кода.
- Изменены только планировщик, его unit/runtime tests и четыре status/docs файла вместе с ТЗ. Ветка `codex/price-planning-target-margin-20261015`; PR #696 остаётся открытым. Незакоммиченные `data/tasks.json` и `data/users.json` сохранены и не входят в изменения.

# 2026-10-15 — PR #696: повторные исправления R1/R2

- Повторный review точного SHA `81ab8bfaba293f20f1b0606ba1c3f598b17f0cd1` подтвердил: R1 был исправлен только для верхних соседних копеек/известной цены, а поиск при неизвестной цене всё ещё пропускал достижимую цель; R2: fallback не разбирал принятую калькулятором десятичную запятую.
- R1: добавлены ограниченные пробы первых копеек над минимумом и шести ценовых масштабов; при неизвестной исходной цене тестовая цель 49,99% теперь находится и перепроверяется тем же forward-калькулятором. Лимит — не более 127 оценок в расчётном худшем случае при hard cap 128.
- R2: кандидат исходной цены нормализуется теми же правилами пробелов и десятичной запятой, что применяются при расчёте сценария.
- Добавлены helper и Telegram-runtime regressions. Четыре связанных модуля: **78 passed in 1.19s**; `compileall -q app tests` и `git diff --check` прошли.
- Полный pytest Windows в локальной среде: 2 806 passed, 21 failed, 368 errors; pytest завершился с `WinError 5` при работе/очистке временных каталогов. Локальный полный итог не используется как приёмка.
- Verify run **38722009779** на SHA `ac43cb70069ac1e4586b13c7b8e70c9db04e2944` прошёл: Windows/Python 3.12 — **3 195 passed in 43.58s**, Linux/Python 3.11 — **3 195 passed in 11.59s**, compileall и production Docker build/runtime smoke прошли. PR #696 остаётся открытым, merge не выполнялся.
- Ветка `codex/price-planning-target-margin-20261015`; пользовательские `data/tasks.json`, `data/users.json`, lock и временные каталоги сохранены и не входят в изменения.

## Историческая запись — первое исправление review R1/R2 (до повторной проверки)

- R1: если верхняя цена не проходит цель из-за округления до копеек, поиск теперь проверяет восемь ближайших нижних копеечных значений и исходную цену (если задана), затем использует только прямым калькулятором подтверждённую точку как границу. Проверенный бюджет — не более 113 оценок; лимит 128 сохранён.
- R2: новые расчётные цены помечаются `planned_seller_price`, введённые сравниваемые цены — `manual_seller_assumption`; исходное происхождение цены хранится отдельно. Добавлены три регрессионных сценария.
- Связанные helper/runtime/review regression модули: **75 passed in 1.12s**; compileall и `git diff --check` прошли. Полный локальный pytest не дал итог: были ошибки и сбои, а завершение прервал `WinError 5` при перечислении basetemp. На чистом PR CI точный SHA `475f2dbccc069c58a8ac859c9334705472718e0c` прошёл: run **38716365784**, Windows — **3 192 passed in 20.16s**, Linux — **3 192 passed in 11.08s**, compileall, production Docker build и smoke успешны. Повторная проверка исправленного diff не выявила новых замечаний; PR открыт, слияние не выполнялось.
- Изменения находятся в существующей ветке `codex/price-planning-target-margin-20261015`; пользовательские `data/tasks.json`, `data/users.json`, lock-файл и временные каталоги не включать.

# История 2026-10-15 — M00–M04 реализации до первого review PR #696

- PR #695 слит в `main` squash-коммитом `de21561a8b440570ac34bcfd9b3dc48abee1ffac`. Его дерево совпадает с reviewed head `ef6be5e`; merged-main Verify run `38707150836` — success. В предшествующей PR integration проверке Windows/Linux дали по **3 150 passed**; Docker build/runtime smoke прошли.
- PR #695 уже слит; новый этап выполняется в отдельной ветке `codex/price-planning-target-margin-20261015`, созданной от актуального `main` `de21561a8b440570ac34bcfd9b3dc48abee1ffac`.
- M00 audit завершён: диапазон 0,01–9 999 999 999 999,99 ₽, шаг копейка; исходная верхняя граница 104 оценки увеличена до 113 после review-проб ближайших копеек. Никакая обратная формула налога не дублируется, глобальная минимальность не обещается.
- M00 baseline пять существующих unit-price модулей: **57 passed in 1.20s**; точные synthetic случаи сверены напрямую с TaxService.
- M01 добавил чистый `UnitPriceTargetPlanningService`: поиск цели 0–100% и сравнение 2–5 цен через существующий forward calculator, exact Decimal check и максимум 128 расчётов. Шесть калькуляторных модулей — **81 passed in 1.37s**; compile helper passed.
- M02 подключил кнопки/ввод/компактный результат к тому же runtime и factory. Сценарий остаётся неизменным до явного выбора; цель используется при последующем сравнении вариантов. Ошибочный ввод исправляется, пропущенные расходы остаются неизвестными. Тестовый набор M02 — **63 passed**.
- M03 добавил выбор только по callback-селектору сохранённого target/row result, прямую повторную проверку перед применением, обновление только временной цены и provenance, freshness/version/tenant/SKU/snapshot/expiry guards и освобождение session result при TTL. Между изменением сценария и поздним завершением расчёта действует fail-closed guard. Целевой набор M03 — **71 passed**; compileall и diff check прошли.
- M04 добавил регрессию всего публичного пути: карточка товара → плановый сценарий → ввод цели → применение рассчитанной цены через `AssistantButtonHandlerService`. Целевой набор четырёх модулей — **72 passed in 1.13s**.
- PR #696 открыт, не слит: head `46e91cffe66beac1c5f8289ba5cac7984975fd6c`. Verify run **38713193546** прошёл: Windows Python 3.12 — **3 189 passed in 41.30s**; Linux Python 3.11 — **3 189 passed in 12.14s**; `compileall`, production Docker build и smoke прошли. Linux report был создан для PR merge-ref `a083a17692c701cd4d32772d163d9f9673bbf1f8`, который содержал head PR.
- Изолированный локальный Windows full-suite прогон не удалось достоверно завершить: pytest получил `WinError 5` при перечислении временной папки; CI на чистых Windows/Linux runners завершился успешно. Пользовательские JSON/lock и временные данные не копировались в изолированную копию и не включались в commits.
- Пользовательские `data/tasks.json`, `data/users.json`, lock-файл и временные каталоги перенесены сменой ветки без изменений и остаются незакоммиченными; в коммиты не включать.

# 2026-10-15 — M02 целевая маржа и сравнение цен подключены

- Runtime использует injected `UnitPriceTargetPlanningService`, тот же `UnitPriceScenarioService` и `TaxService`, тот же выбранный SKU/store snapshot; production factory не создаёт второй каталог и не добавляет сетевые запросы.
- В Telegram доступны ввод цели и 2–5 вариантов цены. В сравнении сохраняется уже введённая цель; неизвестные строки помечаются как требующие заполнения, а не как ноль или провал цели. Целевой результат содержит найденную цену безубыточности и отдельно результат заданной цели.
- Невалидный процент/список оставляет pending stage для исправления; отмена возвращает исходный сценарий. Изменения параметров, refresh и возврат из результата сбрасывают сохранённый результат. Новые расчёты не изменяют seller price или business state.
- Helper, Telegram runtime, architecture/repeat-review и новые lifecycle regressions: **63 passed in 1.06s** (Windows Python 3.12, изолированный pytest temp, без pytest cache). Проверены 5 строк цены, UTF-16 Telegram limit, callbacks ≤64 bytes, одна исходная загрузка SKU и сохранность цены.
- M02 выполнен отдельным reviewable commit на ветке `codex/price-planning-target-margin-20261015`; его SHA указан в истории выполнения ТЗ. Полный suite и CI нового code SHA остаются M04.

# 2026-10-15 — M03 применение выбранной цены завершено

- Кнопка целевого результата может подставить только проверенную цену, достигшую цели; таблица разрешает выбрать только сохранённую вычислимую строку. Callback содержит индекс строки/селектор цели и связан с user, store, SKU, scenario, version и snapshot; цену из callback runtime не читает.
- Перед изменением цены кандидат повторно вычисляется текущим `UnitPriceScenarioService`. Коммит в память происходит только под lock после проверки версии, активного сценария, tenant/store, SKU и snapshot. Устаревший source или сессия отказывает и очищает transient результат; Ozon и business repositories не меняются.
- При успешном refresh source snapshot получает новое поколение версии, старые callback больше не подходят. Late apply after new input returns stale без перезаписи. Expiry удаляет session, active/pending/operation references и сохранённый result.
- Целевой набор helper/runtime/architecture/repeat-review: **71 passed in 1.11s**; `compileall` изменённых Python files passed; `git diff --check` clean. M04 выполняет полный pytest, production smoke и новый CI/PR.

# История 2026-10-15 — PR #695: R11 исправлен и принят при повторной проверке

- `FinanceService.get_daily_discount_points_evidence` теперь относит POSTING с отсутствующим/null/пустым/пробельным SKU к malformed evidence и делает дневную выборку неполной. Известный отличный SKU сохраняет прежнее поведение и исключается из выбранной когорты.
- Добавлены четыре parser cases и сквозной regression FinanceService → UnitPriceScenarioSource → calculator math/runtime → public handler. Без ручного допущения автоматический процент остаётся unknown и прибыль не показывается; после ручного ввода сценарий рассчитывается.
- Code commit `27dbb2f65166ac63b07fac250eea87a2d9dca939` прошёл полные Windows/Linux/Docker Verify runs **38704396583** и **38704389615**; целевые шесть модулей дали **63 passed**, `compileall` и `git diff --check` прошли. Повторная проверка R11 не выявила открытых замечаний; PR #695 открыт для слияния другой моделью.
- Работа ведётся по `LUNA_PR695_DISCOUNT_IDENTITY_FIX_TASK_2026-10-15.md`. Пользовательские `data/tasks.json`, `data/users.json`, lock-файлы и существующие временные каталоги не изменялись.

# История 2026-10-15 — перед исправлением R11

- Дополнительный review head `9185f65fa75ca0b7dc4d333cc362997209a5cd59` подтвердил закрытие R1–R10 и выявил P2: неразрешённый SKU молча считался другим товаром, поэтому неполное среднее баллов получало `complete=true`.
- Reviewed-head Windows/Linux/Docker CI runs `38635120280` и `38635112065` были зелёными, но не покрывали дефект. Изначальные red probes записаны ниже как историческое подтверждение.

# История 2026-10-14 — PR #695: R10 принят после полного CI и repeat review

- Для R10 source принимает цену/себестоимость только в существующем техническом диапазоне калькулятора; неподдерживаемое значение становится unknown с incomplete completeness/provenance. Отклонённая сохранённая стоимость не получает `cost_as_of`.
- `_money`/`_percent` fail closed для неподдерживаемых Decimal; интеграционные тесты проходят через реальный source → math → runtime → handler. Для invalid cost проверены и result screen, и edit prompt; ручная цена/себестоимость восстанавливает расчёт без изменения исходного хранилища.
- X00 red evidence: оба ожидаемых поведения до исправления возвращали `UNIT_PRICE_SCENARIO_CALLBACK_FAILED`; X01 локальная правка выполнена. Calculator/UI/tax-policy набор: **59 passed in 1.51s**. Один ранний запуск соседних tenant-tax tests не смог стартовать из-за ACL временного каталога Windows; эти два теста не входят в 59.
- Полный pytest в изолированной Windows копии без seller data/.env: **3 144 passed in 16.17s**; `compileall -q app tests` прошёл с одной существующей `SyntaxWarning` в returns-impact test; `git diff --check` прошёл. Два production-tax-policy теста проверены с синтетическим test-only default policy.
- GitHub Verify exact head `2207ec86ec96012f7911706429fdc1b4dfacde23`: runs **38634572358** и **38634565693** success — Windows/Linux full suite, compile, production Docker build/runtime smoke. Повторный архитектурный review не обнаружил открытых R10 blockers; R1–R9 сохранены.
- X00–X03 завершены. PR #695 открыт для слияния другой моделью; merge и production restart не выполнялись. `data/tasks.json`, `data/users.json`, lock/temp файлы сохранены.
- Review меняет только документы; пользовательские data-файлы/locks/temp и production code сохранены. Слияние выполнит другая модель после приёмки.

# 2026-10-14 — PR #695: локально исправлены findings R8/R9

- R8 исправлен field-aware Decimal validation: денежные суммы по-прежнему ограничены 15 значащими цифрами; bounded процентные ставки принимают до 28 цифр контекста Decimal и сохраняют диапазон 0–100 и проверки порядка величины. Полное source → math → runtime значение 50/300×100 рассчитывает сценарий: налог 25 ₽, прибыль 280 ₽, маржа 56%.
- R9 исправлен передачей возраста/TTL source cache в runtime. Cache hit сохраняет исходный возраст плюс elapsed; результат и assumptions используют единый freshness calculation. Source stale на точной границе `age >= TTL`; повторное открытие, локальные правки и повторный текст не омолаживают источник; successful refresh обновляет снимок и сохраняет ручное рекламное допущение.
- Добавлены штатные интеграционные regressions в `tests/test_unit_price_scenario_repeat_review_regressions.py`; targeting calculator/runtime/source/service set: **48 passed**. Red evidence двух кейсов до исправления сохранён в истории review.
- W00–W03 завершены. Calculator review набор: **48 passed**; полный изолированный Windows pytest: **3 141 passed in 24.54s**; `compileall -q app tests` прошёл с одной прежней `SyntaxWarning` в `tests/test_unit_economics_returns_impact_integrity_v971_v980.py:177`. Code SHA `9ed3e2d9bee334b54b874f63493f69dc4197d15f` прошёл Verify run **38621277605**: полный Windows/Linux suite, Docker build и runtime smoke. Повторная проверка R8/R9 не выявила открытых blockers. PR #695 открыт, слияние оставлено другой модели.

# История 2026-10-14 — PR #695 R1–R7: первая приёмка исправлений

- Исправлены семь findings initial architecture review: catalog picker tokens bound to user/store/generation; потребление picker callback атомарно создаёт source operation ticket; late initial/refresh results отсекаются; scenario eviction isolates pending record; READY text returns calculator screen; Decimal/tax invalid outputs fail closed; adapters and store commands clear calculator state before other navigation; source snapshot TTL no longer slides with edits, включая freshness на assumptions screen.
- Добавлены controlled `Event` concurrency, adapter/navigation, text routing, math-boundary и freshness regressions в `tests/test_unit_price_scenario_architecture_review_regressions.py`; math service tests покрывают extreme magnitude/precision и invalid tax output.
- Targeted calculator/UI/routing tests: **62 passed in 2.32s**. Полный Windows pytest: **3 138 passed in 18.68s** в изолированной копии без пользовательских данных, `.env` и live storage. `compileall -q app tests` завершился; видна одна существующая SyntaxWarning в `test_unit_economics_returns_impact_integrity_v971_v980.py:177`.
- Code-bearing SHA `3f4942b6c2e01238cabfd9fda7c274ab479bcba7` опубликован в PR #695 (`codex/unit-price-calculator`). Повторный review по R1–R7 не оставил блокеров. Verify run **38616115735** — success: Windows full suite, Linux full suite, Docker production build и runtime smoke.
- Пользовательские `data/tasks.json`/`data/users.json` и локальные temp/lock файлы сохранены и исключены из commits. `git diff --check` прошёл. PR открыт; merge и production запуск не выполнялись.

# 2026-10-14 — PR #695: архитектурный review требует R1–R7

- Проверен PR head `6d472145fe4586a5fe2a4da0e7b0b796900b8fac`, ветка `codex/unit-price-calculator`. Решение review: не сливать до исправления R1–R7 и проверки нового SHA.
- Один P1 касается callback origin store. Шесть P2 касаются concurrent late activation, pending eviction, text-stage результата, числовой валидации, ранней навигации внешних adapters и source freshness. Для R2 отдельно подтверждено: текущий polling сериализует updates (`max_concurrent_updates=1`), но обязательный параллельный runtime contract нарушен.
- Review: `ARCHITECTURE_REVIEW_PR695_2026-10-14.md`. ТЗ GPT Luna: `LUNA_PR695_ARCHITECTURE_FIX_TASK_2026-10-14.md`, этапы V00–V08 ещё не начаты.
- Targeted existing scenario tests: **26 passed in 1.38s**; 8 изолированных воспроизведений подтверждают 7 находок. Verify run `38604649833` success на review SHA — baseline, не acceptance исправлений.
- В рамках review изменены только документы. Production code, существующие локальные пользовательские данные и API/DB contracts сохранены; merge/deploy не выполнялись.

# 2026-10-14 — U04 локальная приёмка калькулятора цены

- Защищена опциональная composition калькулятора: при неполном test/external unit-economics provider source runtime не создаётся; при штатных sources production wiring остаётся включённым. Добавлен regression.
- Архитектурная проверка убрала отдельный каталог товара калькулятора: выбор SKU теперь идёт через существующий юнит-экономический picker. Регрессии подтверждают переход и изоляцию выбора по магазину.
- Полный Windows pytest: **3 119 passed**; `compileall -q app tests`: passed. Локальный sandbox требует ACL-friendly pytest temp root; тесты и assertions не подменялись. `AI_ASSISTANT_STORAGE_ROOT` задан пустым, как ожидают legacy-storage тесты.
- CI run **38604317400** прошёл на кодовом SHA `acb1e196`: Windows verification, полный Linux verification, Docker build и runtime smoke. PR #695 оставлен открытым для независимого архитектурного review; слияние и production запуск не выполнялись.

# 2026-10-14 — U03 Telegram-калькулятор плановой цены завершён

- Калькулятор встроен в существующий раздел юнит-экономики и detail-карточку; оба пути используют один временный read-only runtime. Сценарии и pending input изолированы по user/store/SKU/id/version и не записывают цену, себестоимость, расходы, налоговую политику или фактические результаты.
- Пользователь меняет цену, себестоимость, ставку комиссии, рекламу, баллы и ручные расходы L/M/E. Автоматические баллы можно вернуть к взвешенному 28-дневному источнику; обновление источников сохраняет ручные допущения. Неизвестная реклама не становится нулём.
- UI явно обозначает FBO estimate; ставка из карточки может измениться с новой ценой. FBS не поддержан этим сценарием.
- U01/U02/U03 + смежные finance/current-economics regressions: **61 passed**; production-factory wiring: **1 passed**; compileall прошёл. На Windows production-factory test вызван с ACL-friendly pytest temporary root. U04 full suite/CI и архитектурный review остаются; live Ozon и production не задействованы.

# 2026-10-14 — U02 read-only источник калькулятора завершён

- Добавлены `FinanceService.get_daily_discount_points_evidence` и `UnitPriceScenarioSource`. Автоматический weighted b доступен только по завершённому 28-дневному точному SKU evidence с явным bonus; отсутствие/конфликт оставляет параметр пустым для ручного ввода.
- Snapshot берёт текущую seller price/FBO rate как оценки, exact product-id RUB cost и активную store tax policy. Расходы на доставку, последнюю милю, acquiring и рекламу не выводятся из сомнительных per-row средних; их нужно ввести для расчёта.
- Источник cache изолирован по tenant/user/SKU, TTL 600 секунд, максимум 128; deep copy, общий same-key refresh, HTTP trace 60 секунд/64 попытки. Автоматическое окно определяется локальной датой приложения. Live Ozon не запрашивался.
- Scenario/source/current finance/tax regressions: **62 passed**. U03 Telegram flow и U04 приёмка остаются.

# 2026-10-14 — U01 чистая модель калькулятора завершена

- `app/services/unit_price_scenario_service.py` — чистый decimal-сервис планового расчёта; `tests/test_unit_price_scenario_service.py` — **8 passed**.
- Контроль: P=500 ₽ → прибыль 186 ₽, маржа 37,20%; P=600 ₽ при тех же ставках/фиксированных расходах → 258,20 ₽ и 43,03%. Налог вызывает существующий `TaxService`; отсутствующая обязательная ставка/политика остаётся unavailable.
- Результат включает scenario identity/version, input units/provenance, source metadata, состав включённого/исключённого и read-only флаги. U02 (source + среднее баллов), U03 (Telegram), U04 (приёмка) не завершены.

# 2026-10-14 — U00 аудита калькулятора плановой цены завершён

- Ветка `codex/unit-price-calculator`, базовый squash SHA `655b3a0` (PR #694 уже в main). U00 source map: `project_brain/UNIT_PRICE_CALCULATOR_SOURCE_AUDIT_2026-10-14.md`.
- Подтверждено: `commission.sale_amount` уже входит в `gross_sales`, `commission.bonus` — отдельные баллы; bonus completeness текущим daily aggregate не доказана. `sales_count` — количество положительных строк товара, не штуки. Текущие finance average L/M/E поэтому не считаются расходом на единицу.
- V1 запросит ручные L/M/E. Текущая FBO ставка и seller price используются только как помеченные оценки; FBO не переносится на FBS. Налоговую модель получает из активного tenant policy и пересчитывает через `TaxService`.
- U00 целевой regression baseline: **44 passed** на Python 3.12 (`PYTHONPATH=app`). Live Ozon и новые изменения кода ещё не проверялись/не выполнялись. `data/users.json` и `data/tasks.json` сохранены вне изменений.

# 2026-10-14 — P00–P08 приняты; слияние PR #694 одобрено

- Пользователь поручил принять решение о слиянии. При независимой проверке `fb1b0db` подтверждены два пропущенных пути R1/R4: повторный текст на whole-history confirmation терял действующие кнопки (single/CSV), а auth timeout Performance не учитывал локальный enrichment остаток и после 401 терял причину global budget exhaustion.
- Оба пути исправлены с meaningful red → green регрессиями. Cost-flow suite: **16 passed**; Performance/SKU-advertising suite: **99 passed / 3 deselected**. Пропущенные локально файловые diagnostics будут включены в полный CI без Windows ACL.
- Полный GitHub CI на code SHA `f7a0f945bc26cadd5d190982a68c2dae6191d632`: Linux Python 3.11 — **3 093 passed**, Windows Python 3.12 — **3 093 passed**, compileall и production Docker build/smoke прошли. Финальный review подтвердил R1–R5 и оба дополнительных пути без открытых блокеров; решение — сливать PR #694. Пользователь дал прямое разрешение принять решение о слиянии.
- P00–P08 приняты с сохранением известных P04 source limitations (неизвестные метрики не становятся нулём). Данные продавца и локальные runtime-артефакты не включены в кодовые коммиты; deployment/перезапуск не входит в эту приёмку.

## Исторический снимок 2026-10-14 — R1–R5 исправлены и перепроверены

- Для PR #694 внесены исправления пяти подтверждённых находок review: привязка себестоимости к draft id, store scope для форм произвольного периода, разрешённый текстовый ввод описания внешнего расхода, общий operation budget для Ozon Performance и блокировка shared decision LRU.
- Целевой regression suite: **74 passed**; прямой повтор ключевых сценариев: **13 passed**; `compileall` затронутых модулей прошёл. На исправляющем code SHA `d3cfddeda006cdb164393ba7a8ae182a24a3c1ea` полный CI прошёл: Linux **3 090 passed**, Windows **3 090 passed**, production Docker build и smoke прошли.
- Повторный Architecture Review exact code SHA не нашёл открытых R1–R5. Изменения классифицированы как **Architecture Review Required** и review завершён; PR остаётся открытым и не слитым по просьбе передать решение другой модели.
- Исходные R1–R5, acceptance evidence и follow-up сохранены в `ARCHITECTURE_REVIEW_PR694_2026-10-14.md`.

## 2026-10-14 — архитектурный review P00–P08

- PR #694, reviewed code `ac0f101`: Architecture Review выявил R1–R5, воспроизведённые probes с production-классами и fake sources; реальных HTTP/данных продавца probes не использовали. Полный CI исходного revision прошёл: Windows/Linux по **3 077 passed**, production Docker build/smoke прошли. Этот CI не покрывал найденные сценарии.
- P01 OS locking/durability extension проверен без архитектурного блокера; приёмка всей ветки P00–P08 остаётся открытой до CI и повторного review исправленного revision.

## 2026-10-13 — снимок состояния до архитектурного review

- P00–P08 реализованы в рабочей копии. Последняя полная изолированная проверка Windows Python 3.12: `pytest tests app/tests` — **3 077 passed in 12.06s**; `compileall app tests` прошёл. P07/P08 combined regression — **173 passed**.
- Коммит `b2d86b0` (`Prepare P00-P08 verification snapshot`) отправлен в `origin/codex/p00-project-baseline`. Первый GitHub Actions запуск: Windows Python 3.12 — **3 077 passed in 37.57s**; Ubuntu Python 3.11 — **3 076 passed, 1 failed** из-за точного сравнения timeout `5.0` с корректным фактическим `4.999994`; Docker build/smoke были пропущены после падения теста.
- Исправление теста `9d17e33` использует контролируемые монотонные часы и сохраняет точную проверку `timeout == 5.0`; локальная целевая проверка — **1 passed**. Полный GitHub Actions run #2978 на `9d17e33`: Ubuntu Python 3.11 — **3 077 passed in 8.51s**, production Docker build и smoke прошли; Windows Python 3.12 — **3 077 passed in 29.43s**. Оба job завершились успешно.
- P04 принят после обезличенной live-сверки Returns/Analytics и полного изолированного pytest (**3 016 passed** на момент приёмки); причины отсутствия Analytics `cancellations`/`returns` и расхождение CSV/API остаются неизвестными и не подменяются нулями. Подробности — в `P04_SOURCE_RECONCILIATION_2026-10-12.md`.
- P01 реализация и Windows-regression завершены (**171 passed**); Linux Python 3.11 runtime Verify теперь прошёл на `9d17e33`. Внешняя приёмка P01 и P08 остаётся открытой до отдельного Architecture Review.
- P07/P08 подключены к production composition factory; экран полноты остаётся read-only и использует ограниченный snapshot того же расчёта. Сводка приоритетов использует существующие сигналы, изолирует кэш по tenant/store и ограничивает длину Telegram-сообщения. P08 классифицирован как Architecture Review Required; отдельного независимого review в этой рабочей копии нет.
- Ветка `codex/p00-project-baseline`, последний проверенный код — `9d17e33`. Изменение касается только детерминированности теста и документации; `data/users.json`, `data/tasks.json`, `data/tasks.json.lock` и локальные тестовые временные каталоги остаются отдельно от кода.

## Исторический снимок: P05 завершён; начат P06

- P04 принят после live-сверки Returns и Analytics и полного pytest: **3 016 passed in 12.09s**, exit code 0. Прогон выполнен в полной изолированной копии без `.git`, `.venv`, секретного `.env`, БД и runtime-данных; исходные `data/users.json` и `data/tasks.json` не копировались и не менялись. Ранее sandbox-запуски блокировались ACL; успешный прогон это ограничение снял.
- Live `/v1/returns/list` за август: FBO — 272 уникальные записи (270 `Cancellation`, 2 `ClientReturn`), FBS — 0; полные страницы, 2 HTTP-попытки. Это наблюдаемые типы/числа, не подтверждение семантики всего enum или построчного соответствия XLSX.
- Live `/v1/analytics/data`: 31 полная дневная строка, `ordered_units=6117` совпал с totals и суммой строк; `cancellations`/`returns` отсутствовали и остаются unknown. CSV содержит 6 119 единиц, из них 2 архивного SKU; причина расхождения и причина отсутствия метрик не доказаны. Сырые SKU и товары не сохранялись.
- Исправленная подпись возвратов, целевые проверки P04 (**79 passed**) и `compileall` по затронутым модулям сохранены. Evidence и границы вывода: [P04_SOURCE_RECONCILIATION_2026-10-12.md](P04_SOURCE_RECONCILIATION_2026-10-12.md).
- P05 завершён: одинаковые расчетные callbacks дедуплицируются по tenant/store и запросу; ручной ввод периода тоже защищён от параллельного повтора. Для одного расчёта действует общий кооперативный лимит Ozon — 600 секунд и 300 HTTP-попыток; историческая CPC-сверка ограничена 180 секундами/120 вызовами. Optional CPC не скрывает доказанную финансовую экономику. Детальные callback связаны с id собственного отчёта, поэтому поздний результат не подменяет другое окно. Итоговая целевая регрессия — **79 passed**, полный isolated pytest — **3 027 passed in 18.29s**, exit code 0.
- P06 завершён: добавлены Telegram меню и выбор периода внешних расходов, просмотр entries/coverage gaps, форма с предпросмотром и подтверждением, отдельное подтверждение полноты. Используются те же repository/evidence сервисы, что Period Profit, без миграции; внешняя сумма вычитается только существующим query contract. Повторные/параллельные подтверждения, stale callbacks и переключение магазина проверены; добавление расхода не подтверждает период автоматически. Targeted integration — **70 passed**, полный pytest — **3 047 passed in 18.70s** в очищенной изолированной копии.
- P07 stage A завершён: `PeriodProfitQueryService` уже отдаёт account summary, SKU/quantity, tax policy metadata, external-expense evidence и Return COGS evidence; `PeriodProfitReturnCogsBlockerStageService` остаётся единственным resolver первой блокирующей стадии. Обычный Period Profit пока не сохраняет view snapshot, поэтому без ограниченного user/store cache повторное открытие вызвало бы новый запрос Ozon. Экран полноты будет read-only; отдельного seller-facing accounting recognition/authorization/commit consumer нет.
- Рабочая ветка `codex/p00-project-baseline`, HEAD `a06150a`. Git read-only, новых commits нет. Существующие изменения кода, документации и пользовательские runtime-данные сохранены. P01 отдельно ожидает Architecture Review и удалённый Linux Python 3.11 Verify.

Ниже оставлены dated snapshots прежних этапов; их статусы относятся к датам заголовков.

## P02: финансовые регрессии и подтверждение себестоимости

Это состояние рабочей копии; live Ozon/Telegram и production deployment не проверялись.

- P00, P01 и P02 реализованы в текущей рабочей копии. P02 закрыл ранее падавшие финансовые/quantity/identity проверки, подтвердил даты себестоимости и атомарность CSV.
- В finance quantity bridge разрешён только точный finance SKU или доказанное однострочное сопоставление; неизвестные строки многострочного отправления не присоединяются к catalog SKU. Дубли одной продажи в пределах одного дня останавливают расчёт; междневное повторное начисление дедуплицируется и проверяется на единую версию стоимости.
- Сохраняется seller-confirmed catalog identity для стоимости. Стоимость относится к подтверждённому effective date, а применение к прошлой истории требует отдельного подтверждения. Неоднозначные evidence не превращаются в ноль или успех.
- Windows Python 3.12: `compileall app` прошёл; весь стандартный `pytest` в изолированной копии — **2 998 passed**. Копия исключала `.git`, `.venv`, секретный `.env` и рабочую runtime data; dotenv поиск в родительском каталоге был отключён.
- Текущая ветка `codex/p00-project-baseline`, HEAD `a06150a`. Нового commit нет: `.git` в среде выполнения доступен только для чтения. Незакоммиченные пользовательские изменения `data/users.json` и `data/tasks.json` сохранены и не stage-ились.
- P03 завершён в рабочей копии; P04 — текущий открытый пакет: фактические обезличенные ответы Returns и Analytics получены и записаны, но полный suite не пройден в среде без ACL-ограничения. P05 зависит от P04. P01 всё ещё ожидает независимого Architecture Review и удалённого Linux Python 3.11 Verify; локальная Windows-проверка не подтверждает эти два пункта.

# 2026-10-12 — P02a: снимок промежуточного состояния

Это текущая рабочая копия; production состояние отдельно не проверялось.

- P02 находится в работе. Завершена первая часть: индивидуальная себестоимость сначала предлагает и показывает effective date/store/product, запись требует подтверждения; вся история требует дополнительного отдельного подтверждения.
- CSV seller-cost теперь содержит дату действия, валидируется и показывается пользователю до записи. Batch сохранение выполняется одной tenant-local SQLite-транзакцией, точный replay идемпотентен, а текущая проекция не откатывается при импорте строки с более ранней датой.
- Старые cost/CSV формы отклоняются, если активный tenant/store изменился до подтверждения. Решение 044 закрепляет контракт, согласованный с владельцем.
- Точная проверка P02a на Windows Python 3.12: 27 passed. Полный baseline до P02 был 2 954 passed / 35 failed из 2 989; P02 ещё не завершён, полный suite после этой части не запускался.
- Текущая ветка остаётся `codex/p00-project-baseline`; рабочие изменения данных продавца `data/users.json` и `data/tasks.json` сохранены отдельно и не входят в P02a.

# 2026-10-12 — P01: актуальное состояние рабочей копии

Это краткий актуальный снимок; ниже сохранена история из последней читаемой ревизии `4d215dc`. Он описывает рабочую копию, не production.

- Текущая ветка: `codex/p00-project-baseline`; P00 сохранён коммитами `9f65322` и `c53f6d2`, P01 — `0057f92` (`Support Windows task persistence locking`).
- Для task store POSIX использует `fcntl.flock`, Windows — OS-level `msvcrt.locking`; оба backend сохраняют optimistic fingerprint, atomic replace и file fsync. На Windows fingerprint учитывает переводы строк текстового режима.
- `.lock` остаётся стабильным пустым coordination file: его наличие не доказывает живую блокировку, файл не удаляется, отсутствие OS backend блокирует запись. Добавлена отдельная межпроцессная проверка contention и автоматического освобождения после выхода владельца.
- На Windows directory fsync обозначается как `TASK_DIRECTORY_FSYNC_UNSUPPORTED`; committed write не откатывается, но диагностика оставляет предупреждение. Linux directory fsync путь сохранён. Для user storage добавлено такое же явное предупреждение.
- Файлы `data/users.json` и `data/tasks.json` содержат рабочие данные продавца; их локальные изменения нельзя включать в исходный коммит. Резервные копии `.env`/БД и диагностические файлы исключаются из Git правилами ignore. Секретные значения здесь не приводятся.
- Windows Python 3.12, изолированная копия без seller-файлов и `.env`: `compileall` прошёл; полный стандартный suite — 2 954 passed / 35 failed из 2 989. Все оставшиеся ошибки лежат в `app/tests` (COGS/финансы/tenant fixtures) и продолжаются в P02; все корневые `tests` прошли.
- Межпроцессный Windows lock, повторная запись после newline translation, shutdown contract и предупреждения о durability включены в полный прошедший корневой `tests` набор. GitHub Linux Python 3.11 job сохранён, Windows Python 3.12 job добавлен; Linux job локально не запускался.
- Стандартный `pytest` включает `tests` и `app/tests`. Девяносто корневых legacy unittest-файлов описаны отдельно и пока не входят в автоматический запуск.
- Следующий этап: P02 — разобрать оставшиеся 35 финансовых падений по контрактам, включая дату начала себестоимости с отдельным подтверждением применения ко всей истории.

---

# 2026-10-06 — Сверка комиссии в экспериментальном отчёте

- Экспериментальный отчёт использует явные типы начислений продажи и возврата вознаграждения, если они присутствуют; суммы нетто и прибыль сохраняются, корректируется только разнесение комиссии/остатка.
- Проверка выполнена по XLSX начислений за август: типы продажи и возврата комиссии дают -69 167,90 ₽.
- Если явных типов комиссии в источнике нет, остаётся прежнее значение комиссии из финансовой сводки.

# 2026-10-06 — Прозрачность логистики и агрегированных начислений

- Строка логистики названа логистикой доставки без обратной логистики; распознанные обратные логистические начисления раскрываются в детализации остатка без повторного вычитания.
- Остаток начислений явно обозначен как сумма после основных категорий; пояснение указывает, что показанные отдельно расходы уже могут входить в остаток. Типы Ozon в детализации могут объединять несколько операций XLSX.
- Короткое имя типа «Размещение» распознаётся как начисление размещения; общие подписи хранения без явного признака услуги по-прежнему не считаются платными.
- Августовский XLSX подтвердил комиссию нетто -69 167,90 ₽ из типов «Вознаграждение за продажу» и «Возврат вознаграждения»; экспериментальный отчёт использует эти явные начисления, когда они доступны, и переносит разницу в остаток без изменения нетто и прибыли.

# 2026-10-05 — Доли выручки и источники экспериментальной экономики

- Денежные суммы экспериментального отчёта показывают процент от общей выручки; количества отмен и возвратов — процент от заказанных единиц.
- Для отсутствующих метрик Analytics используются Seller API fallback: отмены по FBO/FBS отправлениям, попавшим в фильтр дат API и сейчас имеющим статус `cancelled`; возвраты — по FBO/FBS записям со сменой статуса в периоде. Неполная пагинация сохраняет значение неизвестным.
- Начисления распознают две части последней мили — «Доставку до места выдачи» и «Выдачу товара» — и названия стоимости размещения. Отдельный отчет размещения доступен в кабинете/API, но его сумма пока не объединяется с финансовыми начислениями.
- Основная прибыль и формула финансового расчёта не менялись.

# 2026-10-05 — Улучшение экспериментальной экономики магазина

- Финансовая детализация собирается из `posting.products[].delivery.services`, `item_fees`, `non_item_fee` и `container_fees` Seller API. Эти дополнительные узлы меняют только расшифровку, не сумму начислений или формулу прибыли.
- В отчёте отдельно показываются нетто-начисления, налог, прочие начисления и рекламные суммы, только если названия в справочнике начислений однозначно указывают на тип рекламы. Performance CPC показан как сверка по сопоставленным SKU; его нельзя прибавлять к начислениям повторно.
- Количество заказов, отмен и возвратов запрашивается отдельными метриками Analytics; возвраты не подменяют отмены, а отсутствующее поле остаётся неизвестным.
- После результата доступны только возврат в эксперименты и главное меню; выбор периода остаётся в начальном экране отчёта.
- Документация сверена с [примером Ozon for Developers по `ordered_units` и `returns`](https://dev.ozon.ru/case/98-Keis-o-novom-instrumente-dlia-kontrolia-tovarnykh-ostatkov-na-sklade/) и [объявлениями Seller API о замене финансовых методов и поле `container_fees`](https://t.me/s/OzonSellerAPI?before=690).

# 2026-10-05 — Первая версия экспериментальной экономики магазина

- В экспериментальном разделе доступен отчёт за пресеты и произвольный период; пользовательский ввод дат изолирован по Telegram user ID.
- Выручка/налоговая база/баллы и прибыль без себестоимости используют тот же `PeriodProfitSummaryService` и cost-exclusion контекст, что и основной режим «без учёта себестоимости».
- CPC отображается только после полного отчёта Performance и точного совпадения SKU и не называется общим рекламным бюджетом. CPO, CPM и другие типы явно исключены; реклама не вычитается повторно из прибыли.
- Эквайринг, вознаграждение Ozon и логистика берутся из финансовых начислений; подвиды логистики и платное хранение показываются только при явных названиях в breakdown, без повторного вычитания. Общее «хранение» не принимается за платную услугу.
- `ordered_units` и `cancellations` читаются через Seller Analytics; отсутствие доступа/неполная страница не превращается в ноль.
- Основные отчёты и пользовательские данные не менялись.

## Уточнение экспериментальной экономики — Seller Analytics и CPC

- `ordered_units` и `cancellations` проверяются независимо; частично доступный ответ сохраняет валидную метрику и показывает безопасный код только для недоступной/некорректной.
- Historical CPC campaign ID может отсутствовать в строках расходов; нулевой счётчик не показывается как подтверждённое число кампаний.

# 2026-10-04 — Отдельный вход для экспериментальных расчётов

- Главное меню открывает отдельный read-only раздел экспериментов; первая экспериментальная экономика магазина описана выше. Основные сценарии и результаты не меняются.

# 2026-10-04 — Читаемые суммы в прибыли без себестоимости

- Денежные значения в сообщении прибыли без себестоимости отображаются с пробелами между разрядами тысяч; расчёты и числовые значения не меняются.

# 2026-10-04 — Налог после вычета баллов за скидки

- В дневных финансовых данных сохраняются баллы Ozon из `commission.bonus`; общая прибыль и прибыль по выбранному SKU считают налоговую базу как выручку минус эти баллы.
- Та же сумма проходит через бизнес-аналитику, пересчёт Return COGS и историческую/текущую юнит-экономику. При некорректном финансовом поле расчёт закрывается ошибкой.
- В периодном сообщении показываются баллы и выручка для расчёта налога. В юнит-экономике налог показывается с фактической долей от цены продажи.

# 2026-10-04 — Ограничение повторного чтения отправлений в прибыли за период

- В общей прибыли количества, уже подтверждённые точной строкой месячного отчёта реализации, не запрашиваются повторно в `/v1/finance/accrual/postings`; неразрешённые строки остаются на точной цепочке fallback.
- FBO количества загружаются одним ограниченным курсорным окном с последующей точечной проверкой пропусков. Загрузчик возвратов тоже использует одно окно, чтобы не перечитывать курсор от начала для каждого `offset`.
- Кэши количества изолированы по рабочему потоку и сбрасываются на каждый расчёт. В режиме выбранного SKU общий список FBO не используется.
- Денежные правила, расходная привязка и fail-closed поведение для неподтверждённого количества не менялись.

# 2026-10-04 — Разделение пользовательских запросов прибыли

- При переходе к новому сценарию прибыли незавершённый ввод дат предыдущего сценария очищается; общий период не попадает в расчёт выбранного SKU.
- Для выбранного SKU неподтверждённая сверка CPC расходов объясняется безопасным сообщением; финансовый отказ от двойного учёта сохранён.
- Ошибки без пользовательского текста больше не форматируются как полный Python-словарь с контекстом.

# 2026-10-04 — Пояснение ошибки сопоставления SKU

- Периодная прибыль простыми словами объясняет, почему расчёт остановлен, и как указать SKU из карточки товара вместо шаблона.
- Кнопка ведёт в проверку выбранного товара; сообщение предупреждает о выборе периода, а связь сохраняется только после явного подтверждения.
- Правила сопоставления и запрет на смешивание товаров не менялись.

# 2026-10-03 — Локальная копия CPO CSV при ошибке разбора

- Ошибочный CPO CSV сохраняется локально в игнорируемый Git-каталог `.runtime-data/ozon-cpo-diagnostics/` для последующего анализа.
- В Telegram передаётся только проверенный относительный путь; данные отчёта и идентификатор пользователя не выводятся.
- Сохраняется исходный CSV либо весь исходный ZIP; остальные отчёты и правила распределения расходов не меняются.

# 2026-10-03 — CPO исключён из прибыли по выбранному SKU

- Выбранный SKU продолжает учитывать подтверждённые расходы CPC, но историческая цепочка прибыли больше не запрашивает CPO отчёты.
- Сбой или формат CPO больше не блокирует прибыль по SKU. CPO явно обозначен как не включённый и не равный нулю.
- CPO парсер и отчётные endpoint остаются доступны только при явном `include_cpo=True`; fallback по обычному SKU не меняется.

# 2026-10-03 — Endpoint опроса статуса CPO в диагностике

- Диагностика сетевого сбоя исторического отчёта показывает маршрут endpoint по allowlist; UUID опущен.
- Для ошибки без распознанной сетевой классификации Telegram явно показывает `UNCLASSIFIED`, сохраняя read-only и fail-closed поведение.

# 2026-10-02 — Признак заполненности артикула в CPO-диагностике

- Неизвестная строка CPO передаёт в Telegram булев признак заполненности колонки `Артикул`; само значение артикула остаётся только в памяти парсера и не попадает в диагностику.
- Признак не используется для идентификации товара или привязки расхода. Выбранный CPO продолжает блокировать расчёт строки без подтверждённого SKU.

# 2026-10-02 — Диагностика источника ошибочной строки CPO

- Неизвестная строка CPO передаёт до Telegram только известный endpoint, факт заполненности обычного `SKU` и категорию значения продвигаемого SKU; содержимое строки не показывается.
- Обычный `SKU` остаётся диагностическим для отчёта выбранных товаров и используется как fallback только в отчёте всех продвигаемых товаров.

# 2026-10-02 — Пустой promoted SKU в all-products CPO

- Только для отчёта `/api/client/statistics/all_sku_promo/orders/generate` пустой promoted SKU при числовом SKU заказа использует SKU заказа для привязки расхода. Отчёт выбранных товаров остаётся fail-closed; строки без числового SKU заказа остаются ошибкой.

# 2026-10-01 — Диагностика пустого SKU в CPO-отчёте

- Пустая ячейка продвигаемого SKU отображается как `(пусто)` в безопасной диагностике CSV; неопознанная строка по-прежнему блокирует финансовый расчёт.

# Current Project State

## 2026-10-04 — Повторное использование prefetch финансового периода

- Общая прибыль и прибыль по выбранному SKU используют один и тот же загруженный набор дневных начислений при переходе от определения SKU к расчёту.
- Проверка периода повторно загружает данные, если кэш неполон, относится к другому диапазону или другому контексту запроса.
- Денежные формулы, сверка SKU, сравнение периодов и fail-closed проверки не менялись.

## 2026-10-03 — Диагностика нераспознанной строки CPC

- Исторический CPC отчёт пропускает неизвестные подписи SKU только при ровно нулевом расходе; любая положительная или невалидная сумма остаётся fail-closed.
- CSV/ZIP с неизвестной строкой CPC сохраняется в игнорируемом `.runtime-data/ozon-cpc-diagnostics/`; в Telegram выводятся только endpoint, категория расхода и безопасный путь.
- Историческая связь финансового SKU с текущим товаром остаётся отдельной проверкой каталога и не подменяется рекламной диагностикой.

## 2026-09-30 — Ограничение частоты запросов Ozon

- HTTP 429 сохраняется как безопасный статус с очищенным Retry-After.
- Идемпотентные GET-запросы повторяются один раз в пределах ограниченного ожидания; запросы генерации отчётов остаются без повторов.

## 2026-09-30 — Диагностика точечной сверки кампаний Ozon

- Для неизвестного paymentType диагностика сохраняет категорию сбоя точечного GET-запроса: HTTP-статус, известный сетевой тип, некорректный ответ или безопасный общий статус.
- Временный сбой безопасного GET-запроса повторяется один раз; сырое тело ответа Ozon не раскрывается.

## 2026-09-30 — Повторная проверка неизвестных кампаний Ozon

- Записи с отсутствующим или неизвестным `paymentType` повторно запрашиваются по `campaignIds` без фильтра `advObjectType`; явный тип из повторного ответа используется для CPC/CPO/CPM классификации.
- Если запись всё ещё неоднозначна, бот сохраняет fail-closed поведение и показывает статус точечной сверки, даты, состояние и тип объекта; до 10 проблемных кампаний объединяются в одну диагностику.
- Диагностика не выводит сырые поля Ozon и очищается по allowlist в Telegram-слое.

## 2026-09-30 — Периодная фильтрация кампаний Ozon

- Исторические CPC-кампании сверяются с периодом отчёта по `fromDate`, `toDate` и `createdAt`.
- Кампании за пределами отчёта исключаются до проверки типа оплаты; неизвестный тип при пересечении или отсутствии дат остаётся ошибкой.

## 2026-10-02 — Тип архивной кампании Ozon без paymentType

- Для кампании из списка с `advObjectType=SKU` отсутствующий или `CAMPAIGN_TYPE_INVALID` `paymentType` использует документированный тип SKU — «Оплата за клик» (CPC).
- Явные типы оплаты сохраняют приоритет; неизвестное явное значение по-прежнему блокирует расчёт.

## 2026-09-30 — Диагностика неизвестной строки CSV Ozon

- Полный повтор заголовка CSV пропускается; неизвестная метка строки остаётся ошибкой и теперь сопровождается безопасными названиями колонок и типом отчёта.
- Текст строки, SKU и финансовые значения не передаются в диагностику.

## 2026-09-30 — Повтор сетевого сбоя при опросе отчёта Ozon

- Исторические Performance GET-запросы повторяются один раз после сетевого сбоя; создание отчёта POST не повторяется во избежание дублирующего задания.
- В ответе безопасно отображается только класс сетевого исключения: timeout, connection, TLS или общий request error; текст исключения не передаётся.

## 2026-09-30 — Диагностика сетевого этапа исторического отчёта Ozon

- При сетевом сбое Performance API исторический отчёт возвращает одну из фиксированных меток этапа: список кампаний, создание CPC/CPO-отчёта или опрос статуса; выбранные и все продвигаемые товары CPO различаются.
- Этап отображается в диагностике бота только по allowlist; секреты, URL отчёта и содержимое ответа API не раскрываются.

## 2026-09-30 — Исторические расходы CPO через отчёты по заказам

- Исторический CPO расход собирается из отдельных асинхронных отчётов по заказам для выбранных товаров и продвижения всех товаров.
- Каждый расход относится к продвигаемому SKU, а не к SKU заказа; CSV ставок без колонки расхода остаётся ошибкой формата.

## 2026-09-30 — Заголовки CSV в диагностике отчёта Ozon

- При нераспознанном заголовке отчёта CPC/CPO бот передаёт в ошибку ограниченный список безопасных названий колонок и тип отчёта; строки данных и денежные значения не выводятся.

## 2026-09-30 — Заголовок CPC-расходов с символом рубля

- CSV-парсер принимает колонку `Расход, ₽, с НДС`, использованную в SKU-отчёте Ozon.

## 2026-09-29 — Ожидание готовности исторического отчёта Ozon

- Предел ожидания статуса асинхронного CPC/CPO-отчёта составляет около 145 секунд; по истечении лимита операция завершается диагностикой ошибки, не нулевыми расходами.

## 2026-09-29 — Диагностика формата исторического отчёта Ozon

- Ошибка формата CPC/CPO CSV/ZIP сохраняет безопасный этап сбоя до сообщения по выбранному SKU; исходные строки и значения отчёта не выводятся, расчёт расходов остаётся fail-closed.

## 2026-09-29 — Итоговая строка CPC-отчёта Ozon

- CSV-парсер распознаёт `Bcero` как итоговую метку Ozon; нулевой итог без строк по SKU допустим, ненулевой или пустой итог без товарной разбивки отклоняется, чтобы не занижать рекламные расходы.

## 2026-09-28 — Диагностика неизвестного типа рекламной кампании Ozon

- Исторический CPC-отчёт включает только кампании с явным `paymentType=CPC`; `advObjectType=SKU` не используется для вывода модели оплаты.
- Если `paymentType` неизвестен или отсутствует у потенциально активной в периоде кампании, расчёт остаётся fail-closed и возвращает безопасный код диагностики с ID кампании.
- При неизвестном `paymentType` исторического отчёта по SKU в ответ передаются очищенное значение типа, числовой ID кампании и код ошибки.
- Ошибка по-прежнему блокирует расчёт рекламы по SKU; диагностическое значение не используется как CPC/CPO и не заменяет расходы нулём.

## 2026-09-28 — Финансовая диагностика в отчёте по выбранному SKU

- Ошибка предзагрузки финансов Ozon теперь показывает безопасный код диагностики прямо в сообщении выбранного SKU.
- Текст ответа провайдера и небезопасные диагностические значения не раскрываются; финансовый расчёт остаётся fail-closed и read-only.

## 2026-09-26 — Ignore known CPM campaigns in CPC+CPO historical SKU reports

- Historical Performance campaign discovery skips the documented CPM payment type, which is outside the report's CPC+CPO scope, instead of aborting the entire Period Profit calculation.
- CPC remains included, CPO remains retrieved through its separate product report, and unrecognized payment types still fail closed.

## 2026-09-26 — Multi-store selector discoverability

- The main keyboard exposes a store-selection button that uses the tenant-aware `ozon_stores` callback and existing account list.
- Store selection and credential isolation continue to use the established Telegram user plus Ozon Client ID scope.

## 2026-09-26 — Ozon credential status and onboarding safety

- Existing encrypted store records are distinguished from disconnected users when the master key is missing or mismatched.
- Store-scoped storage initialization completes before credentials are saved, so a setup failure preserves an existing credential.
- Onboarding shows safe storage/key diagnostics and advances to tax setup only after a confirmed read-only Ozon connection.

## 2026-09-26 — Isolate concurrent Period Profit finance caches

- Daily Ozon accrual cache state is request-context local on the shared Period Profit finance service.
- Overlapping calculations for different active stores retain their own raw daily finance responses, including when they request the same date.
- Bounded prefetch workers and canonical account-level monetary authority are unchanged.

## 2026-09-19 — Selected-SKU Period Profit latency repair

- Selected-SKU identity recovery no longer performs an unbounded serial posting-detail
  N+1, and current/previous comparison reuses request-local proven identity evidence.
- The final query calculates the previous period once instead of twice.
- Selected-product provider scope is concurrency-safe and no longer mutates shared
  request state.
- Long Telegram workers emit a secret-free diagnostic snapshot and worker stack after
  90 seconds while the informational watchdog continues waiting.
- Exact realization evidence now covers confirming postings outside the bounded
  detail-probe prefix without reintroducing per-posting N+1 requests.
- Rewritten realization SKUs are supported for single-finance-SKU postings only.
- Identity recovery never pages the complete account FBO history; it uses already
  loaded finance/realization evidence and bounded exact fallbacks instead.
- Any previous-period-only failure degrades the optional comparison without rerunning
  or suppressing independently proven current profit.
- Selected finance scope now preserves its unique offer index and prefilters account
  finance SKUs before individual recovery; unrelated SKU network N+1 is removed.

## 2026-09-15 — Telegram help and discoverability

- The main keyboard exposes `Помощь и команды`.
- `/help` and the callback use the same canonical presentation contract.
- Every supported slash command and every exact seller-confirmation phrase family
  is documented in-bot; routine flows link back to the existing production callbacks.
- No Ozon mutation, financial authority, historical-cost, identity, or Return COGS
  gate changed.


Date:

2026-09-03



# Test Status


Verification model: SHA-bound.

Latest full-suite baseline confirmed:

2208 passed on `3f82b65054a2a7a48b9918803c197377bdb3557f`.

GitHub Actions push verification run #1131 completed successfully for this exact main SHA.

See `project_brain/VERIFICATION_STATUS.md`.



# Stabilization Checkpoint


Completed:


[x] Full test suite stabilization


[x] Action Generator contract restored


[x] Action Executor compatibility restored


[x] Action context preservation restored


[x] Priority preservation restored


[x] Memory features remain compatible with existing pipeline



Result:


63 passed



---



# Project Direction


## Main Product


AI Business Assistant



Цель проекта:


Создание бизнес-ассистента-аналитика,
который читает и анализирует данные Ozon,
сравнивает периоды, объясняет риски,
приоритизирует проблемы и рекомендует действия,
но не изменяет состояние Ozon и не выполняет business mutations.



## Internal Development System


AI Development Agent



Назначение:


AI Development Agent является внутренним инструментом,
который ускоряет создание и развитие AI Business Assistant.



Основные задачи:


- уменьшение ручных действий при разработке
- поддержание Project Brain
- контроль документационного drift
- автоматизация тестирования
- ускорение внесения изменений



Архитектурная связь:


AI Development Agent

↓

Development Workflow

↓

AI Business Assistant



---



# Completed Features

[x] Read-only Period Profit presentation by selected tenant catalog SKU with fail-closed identity and amount validation

[x] Resumable Telegram onboarding from production Ozon account and tax configuration sources


[x] Intent detection


[x] Task creation


[x] Task lifecycle


[x] Pause


[x] Resume


[x] Cancel


[x] History


[x] Context


[x] Action Router


[x] Sales Executor


[x] Stock Executor


[x] Marketing Executor


[x] Priority system


[x] Action dependencies


[x] Conditional actions


[x] SKIPPED state


[x] Skip reason


[x] History response formatting


[x] Sales Intelligence Service foundation


[x] Sales Intelligence Integration v1


[x] Sales Intelligence Data Flow v1 - Context Propagation


[x] Sales Intelligence Production Wiring v1


[x] Sales Intelligence Business Data Input v1


[x] Stock Intelligence Foundation v1


[x] Stock Intelligence Integration v1


[x] Stock Intelligence Context Propagation v1


[x] Stock Intelligence Production Wiring v1


[x] Stock Intelligence Business Data Input v1


[x] Finance Intelligence Foundation v1


[x] Finance Intelligence Executor Integration v1


[x] Finance Intelligence Context Propagation v1


[x] Finance Intelligence Production Wiring v1


[x] Finance Intelligence Business Data Input v1


[x] Product-Level Finance Metrics v1


[x] Product Unit Economics Foundation v1.1


[x] Product Unit Economics Query v1


[x] Tax Configuration Foundation v1


[x] Product Unit Economics Production Wiring v1


[x] Product Unit Economics Telegram UI v1



---



# FAILED Execution Handling


[x] Exception interception


[x] FAILED action status


[x] Error message storage


[x] Failed execution test


[x] FAILED history event


[x] Error history storage


[x] Retry action preparation


[x] Retry execution test


[x] Retry history tracking


[x] Retry policy service


[x] Retry decision logic


[x] Retry allowed flag


[x] Retry limit service


[x] Maximum retry attempts


[x] Retry limit validation


[x] Retry blocked history


[x] Retry block event storage



Result:


63 passed



---



# Smart Planning


[x] Multi-level dependencies


[x] Dependency validation


[x] Dependency cycle detection


[x] Replan request trigger


[x] Replanning service


[x] Replanning integration


[x] Replanning execution flow


[x] Automatic replanning engine


[x] Plan correction



Result:


63 passed



---



# Autonomous Business Assistant


Phase 3 foundation completed:


[x] Feedback service


[x] Feedback integration


[x] Automatic feedback collection


[x] Memory service


[x] Feedback → Memory connection


[x] Memory storage


[x] Memory lookup


[x] Memory context in planning


[x] Memory-guided action generation


[x] Full Memory Agent Loop


[x] Memory compatibility stabilization



Completed goal:


Переход от системы выполнения действий
к системе накопления опыта и использования памяти.



Next planned changes:


1. Поддерживать SHA-bound CI verification на каждом новом main


2. Считать kernel-backed task persistence hardening закрытым; поддерживать только regression/release evidence без новых абстракций без конкретной необходимости


3. Считать seller-facing Product Decision Learning Coverage Queue v493-v502 завершённой: использовать её только как read-only очередь сбора feedback/observation evidence, не как business-priority surface


4. Следующий product/operational пакет выбирать по фактическому repo gap после сверки main; не продолжать learning wrappers автоматически


5. Не подключать canonical user-action advisory/checklist chain к Telegram, пока exact persisted Product Decision verification не будет явно пронесён через production Telegram lineage; v831-v840 укрепляет verifier, v841-v850 guidance, v851-v860 checklist, v861-v870 completion evidence, но runtime-подключение по-прежнему не выполнено


6. Поддерживать operator-only persistence diagnostics и Project Brain drift cleanup


7. Не включать Product Decision / Product Task Draft execution без отдельной архитектуры и авторизации


---



# AI Development Agent Infrastructure


AI Development Agent является внутренним ускорителем
создания AI Business Assistant.



Completed:


[x] Project Brain


[x] Architecture documentation


[x] Development rules


[x] Roadmap


[x] Test map


[x] Architecture decisions log


[x] Changelog


[x] AI Development Manager


[x] Project status command


[x] Test runner command


[x] Context generator


[x] Project analyzer


[x] AI Development Manager v4


[x] Project scanner


[x] Test analyzer


[x] Documentation-driven planning


[x] Development planner


[x] Development cycle automation


[x] Change Impact Analysis Service


---



# Current Architecture Level


Stage:


Task Orchestration Engine

+

Smart Planning

+

Autonomous Business Assistant Foundation

+

Development Autopilot Layer



---



# Current Work Queue


NEXT:


AI Assistant Product Development



---



# Previous Completed Phase


TASK:


Phase 4 - Development Infrastructure



Completed goal:


Создана инфраструктура разработки,
которая ускоряет развитие AI Business Assistant
через GPT + GitHub workflow.



# Current Development Task


TASK:


AI Assistant Product Development


Current Goal:


Развитие возможностей основного продукта AI Business Assistant.



---



# Planned Features


[x] FAILED action state


[x] Executor error handling


[x] Error history


[x] Retry execution


[x] Retry execution history


[x] Retry policy


[x] Retry limit


[x] Retry blocked history


[x] Multi-level dependencies


[x] Dependency validation


[x] Automatic replanning


[x] Plan correction


[x] Feedback loop


[x] Memory system


[x] Change Impact Analysis


[x] Documentation Drift Detection


[x] Automated development workflow


[x] Git checkpoint assistant


[x] Long-running tasks


[x] Self-improvement cycle



## Phase 1

Executor Reliability


[x] Completed



## Phase 2

Smart Planning


[x] Completed



## Phase 3

Autonomous Business Assistant


[x] Feedback loop


[x] Memory system


[x] Long-running tasks


[x] Self-improvement cycle



## Phase 4

Development Autopilot Layer


[x] Project scanner


[x] Documentation system


[x] Test analyzer


[x] Change Impact Analysis


[x] Documentation Drift Detection


[x] Automated Development Workflow


[x] Git Checkpoint Assistant


[x] Project Brain Synchronization


[x] Vector memory


[x] Completed



---



# Metrics


Tests:

SHA-bound verification active.

Latest confirmed full-suite baseline:
1901 passed on `84d714909d5082958bf2bb21a30b7b097eb17955`.

Verification source:
GitHub Actions push run #709, exact SHA-bound main verification with canonical `test-report.json` artifact.



Architecture:


Task Orchestration Engine

+

Smart Planning

+

Autonomous Business Assistant Foundation

+

Development Autopilot Layer



Documentation:


Project Brain active



Development Manager:


Active
---

# Current Unit Economics Validation — 2026-08-25

Completed:

[x] Current seller price from Ozon Price API
[x] offer_id / internal Ozon SKU separation
[x] current commission calculation
[x] fresh logistics from Ozon finance accruals
[x] last mile separated from logistics
[x] acquiring average from fresh finance accruals
[x] product cost integration
[x] explicit tax policy integration
[x] USN Income 6% production configuration validated
[x] rubles + percent-of-price presentation
[x] Telegram production wiring
[x] safe None handling for missing mandatory data

Validated production example:

SKU: hook-2

Seller price: 96.00 RUB
Commission: 13.44 RUB
Logistics: 17.85 RUB
Last mile: 1.55 RUB
Acquiring: 1.30 RUB
Product cost: 21.00 RUB
Tax: 5.76 RUB
Calculated profit per unit: 35.10 RUB
Margin: 36.56%

Finance sample:
236 sales / 2 complete days

Historical note:

At this checkpoint returns / buyout losses were not yet included because cancelled
FBO postings could not be reliably separated into pre-shipment cancellations and
real customer non-buyouts.

Current repository state supersedes that old "Next" item: dedicated returns/buyout
analytics, returns-finance attribution, observed return impact, and authorized return
financial-evidence services now exist.

Important current limitation:

Financial return-operation evidence and returns/buyout analytics are not equivalent
to complete return economics. Do not treat the current evidence as proof that all
return costs/losses are fully modeled in unit economics.

---

# Product Decisions v3 — 2026-08-28

Completed:

[x] Returns-aware product decisions
[x] Russian decision card with source metrics
[x] Assortment-wide decision overview
[x] Priority ordering for product decisions
[x] Decision summary counts in Telegram
[x] Seller article plus action label on product buttons

Preserved:

- decision thresholds;
- manual product drill-down;
- no autonomous action execution.

---

# Product Decisions v4 — 2026-08-28

Completed:

[x] 10-minute successful decision cache
[x] Cache expiry and mutation protection
[x] No caching of errors or insufficient decisions
[x] Telegram assortment pagination
[x] Eight products per page
[x] Previous / next navigation callbacks

Preserved:

- existing decision rules and thresholds;
- seller article callbacks;
- no autonomous action execution.

---

# Product Decision Memory v1 — 2026-08-28

Completed:

[x] Persistent successful decision snapshots
[x] Change-only history without repeated duplicates
[x] Previous decision and priority context
[x] Bounded retention per seller article
[x] Atomic JSON persistence
[x] Telegram decision transition explanation

Preserved:

- ProductBusinessDecisionService rules;
- product_memory SQLite schema;
- task and user memory;
- data/users.json;
- no autonomous action execution.

---

# Product Decision Feedback v1 — 2026-08-28

Completed:

[x] Useful feedback signal
[x] Not-relevant feedback signal
[x] Feedback bound to the latest decision snapshot
[x] Idempotent repeated feedback
[x] Telegram feedback buttons
[x] Safe missing-history and invalid-feedback responses

Preserved:

- feedback does not change decision rules;
- feedback does not execute actions;
- existing decision history retention remains unchanged.

---

# Product Decision Outcome Correlation v1 — 2026-08-28

Completed:

[x] Prior feedback linked to the next changed decision
[x] Priority decrease observation
[x] Priority increase observation
[x] Same-priority decision change observation
[x] No inference without explicit feedback
[x] Non-causal Telegram wording

Preserved:

- observations do not alter decision rules;
- observations do not prove action causality;
- no autonomous action execution.

---

# Product Decision Learning Summary v1 — 2026-08-28

Completed:

[x] Assortment-wide learning summary
[x] Snapshot, feedback, and outcome counts
[x] Product-level latest decision history
[x] Russian decision and priority labels
[x] Feedback and observation details in history
[x] Telegram navigation from overview and product card

Preserved:

- no success-rate claim on limited data;
- no causal claim;
- no influence on decision rules;
- no autonomous action execution.

---

# Safe Product Action Proposals v1 — 2026-08-28

Completed:

[x] ProductDecisionActionProposalService
[x] Replenishment review proposal
[x] Unit-economics review proposal
[x] Margin review proposal
[x] Monitoring-only proposal
[x] Manual-confirmation boundary
[x] Telegram next-step presentation
[x] Assortment actionable-proposal count

Preserved:

- no replenishment quantity inference;
- no price-change inference;
- execution_allowed is always false;
- Action/Executor workflow is not invoked.

---

# Product Action Proposal Confirmation v1 — 2026-08-28

Completed:

[x] Confirm or dismiss actionable proposal
[x] Latest-decision stale proposal guard
[x] Idempotent stored proposal status
[x] Telegram confirmation controls and Russian status
[x] Explicit executed=False response

Preserved:

- confirmation is stored intent, not execution permission;
- monitoring-only has no confirmation buttons;
- no quantity or price draft is inferred;
- no external API mutation or Action Executor.

---

# Confirmed Product Task Drafts v1 — 2026-08-28

Completed:

[x] Persistent ProductActionTaskDraftService
[x] Idempotent draft per decision snapshot
[x] Draft dismissal on proposal rejection
[x] Draft summary in Telegram
[x] Draft status on product card
[x] Dedicated production storage and wiring

Preserved:

- drafts are not executable tasks;
- no replenishment quantity or price is inferred;
- executed_count is always zero;
- no existing Action Executor or Ozon mutation path is invoked.

---

# Product Task Draft Review Lifecycle v1 — 2026-08-28

Completed:

[x] Automatic stale detection against current decision snapshot
[x] DRAFT / STALE / DISMISSED / ARCHIVED states
[x] Compact identifiers for new and legacy drafts
[x] Idempotent terminal archive action
[x] Telegram lifecycle counts and archive controls
[x] Current-card guard against old drafts

Preserved:

- lifecycle transitions never execute tasks;
- archived drafts cannot be reopened implicitly;
- no quantity, price, Ozon mutation, or Action Executor connection.

---

# Product Draft Review Queue Prioritization v1 — 2026-08-28

Completed:

[x] Separate ProductTaskDraftReviewQueueService
[x] Deterministic review score and priority category
[x] Explainable reason codes
[x] DRAFT and STALE queue scope
[x] Oldest-first stable tie breaker
[x] Telegram priority counts, reasons, and icons
[x] Production composition wiring

Preserved:

- queue priority does not alter product decisions;
- priority is not persisted as learned truth;
- no lifecycle mutation, task execution, or Ozon API call.

---

# Product Task Draft Detail and Audit v1 — 2026-08-28

Completed:

[x] Dedicated Telegram draft detail card
[x] Source proposal, priority, profit, and margin context
[x] CREATED / REOPENED / MARKED_STALE / DISMISSED / ARCHIVED audit events
[x] Event source, timestamp, and status transition
[x] No duplicate events for idempotent commands
[x] Honest legacy-history fallback
[x] Terminal archived detail without action controls

Preserved:

- audit facts do not influence decisions or queue score;
- old history is never inferred;
- detail and audit paths cannot execute tasks or mutate Ozon.

---

# Product Task Draft Readiness Checklist v1 — 2026-08-28

Completed:

[x] Separate ProductTaskDraftReadinessService
[x] Proposal-specific factual requirements
[x] Review-ready / needs-data distinction
[x] Explicit missing-field output
[x] Proposal-specific execution policy blockers
[x] Detail-card readiness section
[x] Review-queue readiness counts and item labels
[x] Production composition wiring

Preserved:

- review_ready never implies execution_ready;
- execution_ready_count remains zero;
- missing values are not inferred;
- checklist does not mutate decisions, drafts, or Ozon.


---

# Product Decision Learning Coverage Queue v1 — 2026-08-30

Completed:

[x] Per-SKU learning coverage from persisted Product Decision history only
[x] NEEDS_USER_FEEDBACK / NO_DECISION_HISTORY / WAITING_FOR_LATER_OBSERVATION states
[x] Deterministic learning-attention rank with exact SKU tie-break
[x] Latest-feedback semantics without treating old outcomes as future observation
[x] Fail-closed malformed, duplicate and cross-SKU history handling
[x] Telegram navigation and seller wording
[x] No Product Decision query call while opening the queue
[x] Production DI of the pure coverage builder

Verified product baseline:

- PR #219 head run #61: success
- merged main SHA: `ef8b52ad34740d5cbb657988866ec01ebfe7191b`
- push run #62: success
- full suite: 1321 passed, 0 failed

Preserved:

- queue rank is not business priority;
- no causality, success-rate or profitability claim;
- no Product Decision rule update;
- no Product Task Draft execution;
- no Ozon mutation;
- `automatic_execution_allowed=False`;
- `executed=False`.


---

# Product Decision Learning Coverage Navigation v1 — 2026-08-30

Completed:

[x] State-specific inline navigation from the per-SKU learning coverage queue
[x] Existing `product_decision:<sku>` route reused; no new runtime route
[x] Top-10 navigation matches visible queue ordering
[x] Return path to the full Product Decisions screen
[x] Forged or malformed navigation fails closed
[x] Queue opening remains read-only and does not query Product Decisions
[x] No direct feedback callback is emitted from the queue

Preserved:

- seller explicitly opens a concrete Product Decision before feedback;
- no Product Decision rule change;
- no Product Task Draft execution;
- no Ozon mutation;
- no persistence or finance/mapping change;
- `automatic_execution_allowed=False`;
- `executed=False`.


---

# Store Period Default Composition Hardening — 2026-08-30

Completed:

[x] Removed duplicate StorePeriodRunnerService initialization
[x] Missing period profit dependency fails closed with an explicit error result
[x] StorePeriodSummaryService rejects malformed runner output
[x] Default summary path no longer raises AttributeError on missing profit service
[x] Existing constructor DI remains backward compatible

Preserved:

- no new data source or invented financial state;
- no change to profit formulas;
- no Product Decision or execution wiring;
- no Ozon mutation;
- no data/users.json change.


---

# Unknown Advertising Financial Evidence v1 — 2026-08-30

Completed:

[x] Production advertising defaults to unknown instead of implicit zero
[x] Explicit advertising_cost=0 remains a valid known zero
[x] Business profit and margin stay unknown without advertising evidence
[x] Revenue and gross profit remain independently available
[x] Advertising and business-profit dashboards render unknown as «—»
[x] Sales analysis preserves unknown profit metrics instead of optimistic zero
[x] Tax errors remain visible when advertising is unknown

Preserved:

- no advertising auto-fetch or heuristic classification;
- no financial double counting;
- no change to Ozon fee formulas;
- no Product Decision rule change;
- no seller/business execution or Ozon mutation;
- no data/users.json change.


---

# Finance Context Evidence Hardening v1 — 2026-08-30

Completed:

[x] FinanceContextProvider fails closed on malformed period payloads
[x] Missing gross_sales / gross_profit no longer normalize to zero
[x] Non-finite and boolean financial facts are rejected
[x] Explicit numeric zero remains valid evidence
[x] Finance context output shape remains backward compatible
[x] Finance Intelligence uses gross-result wording instead of accounting-profit claims
[x] Finance executor presentation uses evidence-scoped labels

Preserved:

- existing revenue / gross-profit arithmetic for complete evidence;
- no extra expense inference;
- no tax / advertising / returns double subtraction;
- no accounting net-profit claim;
- no Product Decision or task execution wiring;
- no Ozon mutation;
- no data/users.json change.


---

# Stock Evidence Availability Hardening v1 — 2026-08-30

Completed:

[x] Missing stock dependencies no longer imply verified safe stock
[x] Empty or partial assortment evidence is marked unavailable
[x] Complete no-risk evidence is distinguished from unavailable evidence
[x] Confirmed low-stock action context remains backward compatible
[x] Stock Intelligence rejects malformed/non-finite/boolean/negative evidence
[x] Cross-product stock/sales evidence fails closed
[x] Explicit zero sales remains valid NO_SALES evidence
[x] General fallback does not claim “no critical problems” when stock evidence is unavailable

Preserved:

- existing low-stock threshold behavior for complete evidence;
- no replenishment quantity inference;
- no Product Decision rule change;
- no new stock execution route;
- no Ozon mutation;
- no data/users.json change.


---

# Sales Evidence Availability Hardening v1 — 2026-08-30

Completed:

[x] Configured missing/partial sales evidence no longer becomes a clean no-decline result
[x] Missing or malformed revenue comparison does not normalize to 0%
[x] Confirmed sales-decline action context remains backward compatible
[x] Complete non-decline comparison is explicitly distinguishable from unavailable evidence
[x] Partial configured AssistantEntryService path suppresses sales action
[x] Legacy no-data AssistantEntryService fallback remains backward compatible
[x] Sales Intelligence rejects malformed action context before analytics
[x] Missing required revenue/gross-profit metrics fail closed
[x] Unknown business profit/margin remain None
[x] Explicit numeric zero remains valid
[x] Missing comparison change no longer produces a false “stable” insight
[x] Sales executor renders unknown metrics as «—»

Preserved:

- existing sales-decline threshold: revenue change < 0;
- no Product Decision rule change;
- no Product Task Draft execution;
- no new sales execution route;
- no Ozon mutation;
- no data/users.json change.


---

# Executor Error-Result Lifecycle Integrity v1 — 2026-08-30

Completed:

[x] Executor `error=True` results enter the existing FAILED lifecycle
[x] Direct router `execute()` result contract remains backward compatible
[x] Non-dict and malformed executor results fail closed
[x] Missing executor error message uses stable `EXECUTOR_RETURNED_ERROR`
[x] Failed action no longer reaches `complete_action()`
[x] Task remains ACTIVE after executor-returned failure
[x] Pending action is cleared through the existing failure owner
[x] Failure history/feedback use FAILED semantics
[x] Existing retry policy and retry preparation remain active
[x] Successful executor results preserve the DONE lifecycle
[x] Exact feature/docs branch push verification is now available
[x] Pull-request merge-ref evidence is distinguished from exact branch-head evidence

Preserved:

- no new executor or production runtime route;
- no Product Decision or Product Task Draft execution change;
- no Ozon mutation;
- no retry-limit change;
- no task persistence-format change;
- no data/users.json change.


---

# Marketing Evidence Integrity v1 — 2026-08-30

Completed:

[x] Unsupported marketing executor no longer invents checked-channel evidence
[x] Marketing recommendation requires explicit evidence availability and context
[x] Missing/malformed marketing evidence fails closed
[x] Persisted router run enters existing FAILED lifecycle on missing evidence

Preserved:

- no marketing API or campaign mutation;
- no Product Decision/Product Task Draft execution;
- no Ozon mutation;
- no data/users.json change.

---

# Finance Evidence Availability Propagation v1 — 2026-08-30

Completed:

[x] Derived finance context success is marked available
[x] Derived finance context failure with period evidence is marked unavailable
[x] Missing period evidence does not invent finance availability
[x] Explicit finance context remains authoritative and available
[x] Unavailable finance evidence suppresses finance recommendation
[x] Unavailable finance evidence prevents false clean-business fallback
[x] Legacy finance_context-only recommendation callers remain compatible

Preserved:

- FinanceContextProvider output shape;
- existing finance arithmetic;
- no fee double subtraction;
- no accounting net-profit claim;
- no Product Decision/Product Task Draft execution;
- no Ozon mutation;
- no data/users.json change.

---

# Business Planner Result Integrity v1 — 2026-08-30

Completed:

[x] downstream recommendation error propagation
[x] malformed recommendation result fail-closed
[x] downstream planning error propagation
[x] malformed planning result fail-closed
[x] Action Plan execution error propagation
[x] execution actions/count integrity validation
[x] optional task-creation result validation
[x] general-only recommendation remains non-actionable

Preserved:

- existing constructor dependency injection;
- existing valid plan/action ordering;
- no Product Decision/Product Task Draft execution;
- no Ozon mutation;
- no business-evidence inference.

---

# Business Flow Result Integrity v1 — 2026-08-30

Completed:

[x] malformed intent result fail-closed
[x] execution result validation before success presentation
[x] execution error message preservation without false completed wording
[x] cancel/pause/resume downstream failure propagation
[x] task status/history/details/next malformed-result guards
[x] skip pre-mutation next-action validation
[x] skip result validation and post-mutation partial-state reporting
[x] continue next-action and pending-action result validation
[x] planner error propagation and actions/count integrity validation

Preserved:

- existing constructor dependency injection;
- existing valid execute/task/planner response structure;
- no Product Decision/Product Task Draft execution;
- no Ozon mutation;
- no automatic rollback or retry;
- no business-evidence inference.

---

# Product Decision Learning Telegram Result Integrity v1 — 2026-08-31

Completed:

[x] Learning Summary requires dict + explicit real boolean `error`
[x] Successful summary counts are non-negative non-booleans and internally consistent
[x] Missing summary evidence cannot become zero through optimistic defaults
[x] Decision History requires a real list instead of treating `None` or malformed payloads as empty success
[x] History records must match the requested SKU and carry valid decision, priority, timestamp, feedback and outcome semantics
[x] Unknown feedback is not mislabeled as `NOT_RELEVANT`
[x] Legitimate all-zero summary remains read-only success
[x] Legitimate empty history remains read-only success
[x] Stable seller-facing failures do not expose internal exception text

Verified product baseline:

- entering main `9bfa6a03e50d5c36a874e2ef30088e94efdb104c`: push Verify #440, 1655 passed / 0 failed, digest `sha256:b34831e479e283a17391174e150bf43b07e084510ff82a25eea7269f15f0cd92`
- final feature `7976dbdebdda82660f9fc5bbc7ebffd804990f8f`: push Verify #442, 1666 passed / 0 failed, digest `sha256:95787b366dc1fef928b8ba8f8571bb6053172cd6775ba70c4181901f083965c1`
- PR #286 synthetic merge `44ec86f9587831f6560e3e5ca2bbb9819abd4c29`: Verify #443, 1666 passed / 0 failed, digest `sha256:a46757c2e1baec4ad175c7afc3fcaf2dac5b3b08140d2723fa60f30cc73e6356`
- squash main `d3e9e61e4fee3a9e3aa1f1e34f2e7a1da8cf931c`: push Verify #444, 1666 passed / 0 failed, digest `sha256:67af33c7c3c17dd68d0339edcf58e86fb934925ec2a318fd0615f3f0168fb77c`

Preserved:

- Product Decision rules and thresholds;
- persistence behavior and interaction semantics;
- Product Task Draft remains non-executable;
- no Action Executor connection;
- no business mutation authorization, quantity/price inference, or Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Telegram Analyze / Plan History Integrity v1 — 2026-08-31

Completed:

[x] assistant result validated before analyze/plan success-history persistence
[x] explicit assistant failure records no success history
[x] malformed assistant result fails closed before history side effects
[x] valid success records exactly one expected history event
[x] explicit history persistence failure is not hidden
[x] malformed/exceptional history persistence remains unknown; no rollback is fabricated
[x] exception text is sanitized

Verified product baseline:

- entering main `9c2f783710e125b183e8a314e1ac4c2eac1754f1`: #449, 1666 passed / 0 failed, digest `sha256:a292cffdbb1309e47f33c028062ce699fd1364f18f3db1007cf50e46295b51fa`
- final feature `dd6a5984026f591941fa0f2db62fc260a48f9e02`: #451, 1674 passed / 0 failed, digest `sha256:328c9cc03f7b0b8e292ceb1e42cc78895ba5f86bc32875916c4fc5a5d46ecd02`
- PR #288 synthetic merge `83a8863f79f3ad76d721d4f7fd9eee2ed28a2b20`: #452, 1674 passed / 0 failed, digest `sha256:3c38001164cc6a7eb1b9f2838356843aff9a546ce7f15c5048eed2966251da3c`
- squash main `1bd23e97a565e15b2c2ef6e2067278eacac6caa0`: #453, 1674 passed / 0 failed, digest `sha256:46778bcf50f95fbf335d2d03c2e64aedf648461ec980818c8348fa8d627fca26`
- no failed/cancelled intermediate production SHA occurred in v766-v773
- `externally_verified=False`


---

# Telegram History / Memory Read Integrity v1 — 2026-08-31

Completed:

[x] missing History service is unavailable, not empty success
[x] missing Memory service is unavailable, not empty success
[x] missing user context is failure, not zero/clean evidence
[x] History/Memory read exceptions are sanitized
[x] results require dict + real boolean error
[x] History success requires list; Memory success requires dict
[x] explicit downstream failure is preserved
[x] legitimate empty history and memory remain success

Verified product baseline:

- entering main `c889ff8614c589853b3a29b41caf739067672db0`: #457, 1674 passed / 0 failed, digest `sha256:8eac2e70c655e3c8d3974aa05efdbdfa53b47db31acb8f1a70bfc23684bcc0d6`
- final feature `f4b9b2b8c840a9b5245eb19bfe04430196bc565c`: #459, 1684 passed / 0 failed, digest `sha256:afaafbe46852fe59d83140d69ef0c891db5ebbaeeb55141d83d4b5578427a496`
- PR #290 synthetic merge `69d5928a49ab871fa845b25362fcd581173db484`: #460, 1684 passed / 0 failed, digest `sha256:039b2734f83708c1b48acb6706a16afc214af30fba459ac60afb77c9c50e648c`
- squash main `f432814d74ee4e175d291b69c79767d86d506e0a`: #461, 1684 passed / 0 failed, digest `sha256:e4a08c01b1fc1a83019ca8c947954ce0bf7321d4409e79687263dc8efa03d7b3`
- no failed/cancelled intermediate production SHA occurred in v774-v783
- `externally_verified=False`


---

# Telegram Context Preparation Integrity v1 — 2026-08-31

Completed:

[x] analyze/plan validate last_action context update before current_task update
[x] failed/malformed first context update stops assistant and history side effects
[x] current_task update result is validated independently
[x] failure after successful last_action reports partial committed context state
[x] malformed/exceptional second update remains unknown and does not fabricate rollback
[x] context exception text is sanitized
[x] internal TypeError is not retried
[x] valid preparation still invokes assistant once and history once
[x] optional no-service/no-user context behavior remains compatible

Verified product evidence:

- entering main `656ff93a0cba3194481b007c288f0eeadbaf1441`: push Verify #465, 1684 passed / 0 failed, digest `sha256:69bbe78f6231f4824e1d5fec9f46e09edea685e6ecba001ec75fca57f73e3ed8`
- cancelled intermediate `67e08c87de7564dc76c60fe2e9caebf05ba8f793`: push Verify #466, conclusion cancelled; test step completed 1693 passed / 0 failed; digest `sha256:0f6297bec68de51f7f461208d22f6d63d5f03e39bd8b5b4f39bb8edb9a9495eb`; cancelled evidence only, not green
- final feature `80f85b1b45e1e49279c334078c5991eac2757cc7`: push Verify #468, 1693 passed / 0 failed, digest `sha256:9da810f8425014178cd51fa58fd682582af85d11042998ff3c0c4df8be0e204d`
- PR #292 synthetic merge `978b6e0170693ac5d8d39471dd45983ab394c0c3`: Verify #469, 1693 passed / 0 failed, digest `sha256:0cb7f1a3be2f36c446597636103e4b8778072da5c5e1ffdd8a0abcc15603aaa8`
- squash main `a7748785341ccea0a459ec06c7de460213cec038`: push Verify #470, 1693 passed / 0 failed, digest `sha256:b1fee9bfe0ccdf6d154bd2a2a3786ecd5515fdc1b0ceb7f53dd87bcec9138259`
- `externally_verified=False`


---

# Product Task Draft Freshness Telegram Presentation Integrity v1 — 2026-08-31

Completed:

[x] malformed readiness/freshness metadata fails closed before presentation
[x] partial freshness count maps cannot invent missing categories as zero
[x] malformed optional evidence maps do not become seller-facing synthetic zeros
[x] invalid detail status/age/reasons/coverage/guidance fails closed with stable non-secret result
[x] unknown enum strings are not surfaced as business facts
[x] legitimate all-zero freshness counts remain success
[x] legitimate UNKNOWN freshness and evidence-limited guidance remain read-only success
[x] Product Task Draft remains non-executable

Verified product evidence:

- entering main `3f59d0d71f4ac5dea9e2b915d6b4e0a7fc7008c5`: push Verify #474, 1693 passed / 0 failed, digest `sha256:a334436fd6e357ab6c9948baf907d472e67331442860fdf8fa0c15d5a3afeff0`
- final feature `e0cbd9e4ba3e56600e81f76d7740ef381dbfb124`: push Verify #476, 1703 passed / 0 failed, digest `sha256:b35bb81059445bcc1ca089d5237874461b904ec7795d08db69c2d5383179349a`
- PR #294 synthetic merge `1fc456087126b0cc91e6b3354a6560477a989b4c`: Verify #477, 1703 passed / 0 failed, digest `sha256:f286f803fc87a2c4a65c4f32afb6d606df31635c5b1ad7be1b1aaae21cc0e231`
- squash main `701b5a31575a2e37d76da22af260c206d4a68b50`: push Verify #478, 1703 passed / 0 failed, digest `sha256:640190ca4afe1dad7c2aa6cc326b351064e44121cd539db488f7d7e5eddf8848`
- no failed/cancelled intermediate production SHA occurred in v793-v802
- `externally_verified=False`


---

# Telegram Adapter Runtime Exception Containment v1 — 2026-08-31

Completed:

[x] assistant dispatch exceptions are contained at the Telegram adapter boundary
[x] button-handler exceptions are contained without retry-after-exception
[x] internal TypeError is not retried with legacy arity
[x] legacy arity selection remains pre-call only
[x] keyboard-builder exceptions do not claim successful start
[x] internal exception text is not exposed to sellers

Verified product evidence:

- entering main `ad3692c46e31d4eceeef504e4b55d7cbaa829a09`: push Verify #482, 1703 passed / 0 failed
- cancelled duplicate branch run #483 remains cancelled evidence only
- failed intermediate `c3336160fccddbc25a9d8e2b1f7aeccccaa8be70`: push Verify #484, 1710 passed / 1 failed
- final feature `21776a8cdd61dd35e28a885b5c573a2db3b15c92`: push Verify #485, 1711 passed / 0 failed
- PR #296 synthetic merge `929a1bd4c8ace607ff0bf6c67924aa14ec84b612`: Verify #486, 1711 passed / 0 failed
- squash main `01300c69d1ab54731657ea741687cc728c9e5600`: push Verify #487, 1711 passed / 0 failed
- `externally_verified=False`

Preserved:

- no Product Decision/Product Task Draft execution
- no Ozon mutation
- no quantity or price inference
- `data/users.json` unchanged


---

# Post-Decision Observation Integrity v1 — 2026-09-01

Completed:

[x] malformed checklist and later-decision inputs fail closed
[x] checklist status requires explicit error=False and USER_REPORT evidence
[x] numeric identifiers are not coerced into canonical identities
[x] later decision requires explicit boolean error state
[x] explicit downstream decision failure remains failure
[x] decision type / priority / confidence are validated against canonical values
[x] reasons require a real list of non-empty strings
[x] valid observation remains observation-only and non-causal

Verified product evidence:

- entering main `6d06cca860fbc1b423db02f0166554c562e2b67c`: push Verify #492, 1711 passed / 0 failed, digest `sha256:365511645081a003af4df8d00daf2e78c865d0e81b066d40557ffc2724672064`
- final feature `68c42c5fe4331d776eefe828263dfb930e9c8cd7`: push Verify #494, 1721 passed / 0 failed, digest `sha256:45f9677ae94b941606bfd4ef99ace1722c100d265e7e4354e15e1d6e8823998f`
- PR #298 synthetic merge `ffee00d5b609aa8c0e2c547db0e587dd4be93b94`: Verify #495, 1721 passed / 0 failed, digest `sha256:c184f12cabf364705cc115c94fb8bf7a0d2911d1f66a6b93583c7b40e44bdd8f`
- squash main `cc485098da06834f31fcd09430d83bd96b96f1e1`: push Verify #496, 1721 passed / 0 failed, digest `sha256:9ad01f64be4b80f26bf79cdf8f8127339aa4e88453542d8b27a5b92eba7612c5`
- no failed intermediate production SHA occurred in v811-v820
- `externally_verified=False`

Preserved:

- no Product Decision recomputation or mutation
- no Product Task Draft execution
- no Action Executor connection
- no Ozon mutation
- `data/users.json` unchanged


---

# Task Persistence Operator Presentation Integrity v1 — 2026-09-01

Completed:

[x] operator operational/release/provenance presentation requires explicit error=False
[x] blockers, warnings and incident categories require real unique string lists
[x] operational counts/state/attention claims are internally consistent
[x] release-ready / incident / human-review claims are validated
[x] provenance revision and CI-binding metadata is structurally validated
[x] external-verification and execution/mutation overclaims fail closed
[x] valid operator messages remain read-only and non-sensitive

Verified product evidence:

- entering main `cc485098da06834f31fcd09430d83bd96b96f1e1`: push Verify #496, 1721 passed / 0 failed
- failed intermediate `41c289221c100ce4dc1462603b42349434f2f406`: push Verify #498, 1730 passed / 1 failed; failure was a new test wording expectation and remains failed evidence
- final feature `a0e977595238dd256e9ae0d54e68ac337b04bb91`: push Verify #499, 1731 passed / 0 failed, digest `sha256:173173c93a222338ef8efd942fcb4a9af425df2e9768d6530f2d957c7b2c1cc6`
- PR #299 synthetic merge `c77df0221826e27e444f3d68150419e4adf9bc8d`: Verify #500, 1731 passed / 0 failed, digest `sha256:8f80f8bf4a7c0a4c03a912bdd4adeead94198f10b4e262e776eb3f88292b2f95`
- squash main `c2f1bd3d26fc5e2be33d725b8ecd2898a7b1dbfa`: push Verify #501, 1731 passed / 0 failed, digest `sha256:30db2fb7e7f68ed1460aee79cafee957467eccfd0468bacaa1953816e0340d09`
- `externally_verified=False`

Preserved:

- task persistence ownership and storage format
- no automatic retry or lock deletion
- no business execution readiness
- no Product Decision/Product Task Draft execution
- no Ozon mutation
- `data/users.json` unchanged


---

# Product Decision Persistence Verification Integrity v831-v840 — 2026-09-01

Completed:

[x] Non-mapping persistence-verification application input fails closed

[x] Product Decision lineage IDs and SKU are not coerced from non-string identities

[x] Explicit persisted-preview error markers are structurally validated

[x] Canonical decision type, priority and confidence are required

[x] Reasons require a real non-empty list of non-empty strings

[x] Durable history snapshot semantics fail closed before verification success

[x] Recorded-at lineage requires an explicit string binding

[x] Valid verification remains read-only, non-executable and externally_verified=False

Verified exact main:

`a3aa88f351985e8519f754923880165f96fb29ad`

GitHub Actions push Verify #518: 1741 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring in this package;
- no Ozon mutation;
- `data/users.json` unchanged.


---

# Product Decision User Action Guidance Integrity v841-v850 — 2026-09-01

Completed:

[x] Guidance accepts only mapping-shaped verification input

[x] Verification/application IDs and SKU require canonical non-empty strings

[x] Explicit verifier error=False and verified status are required

[x] Non-empty verification mismatch evidence blocks seller guidance

[x] External-verification and execution/persistence overclaims fail closed

[x] Verified recorded-at is bound to the exact durable snapshot timestamp

[x] Priority and confidence use canonical enums

[x] Reasons require real non-empty string-list evidence

[x] Valid guidance carries exact verified lineage forward without enabling execution

Verified exact main:

`e793ca7ab241d54a12af8b3b402b1dc862652bf2`

GitHub Actions push Verify #534: 1751 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no persistence owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring for the newer user-action chain;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Checklist Integrity v851-v860 — 2026-09-01

Completed:

[x] Checklist accepts only mapping-shaped guidance input

[x] Guidance / verification / application IDs, SKU and verified-recorded-at require canonical non-empty strings

[x] Explicit guidance error=False, ready status and decision-persistence verification are required

[x] Verification remains bound to the persistence application ID

[x] External-verification and persistence/execution overclaims fail closed

[x] Decision/action pairing, priority, confidence, title and reasons are structurally validated

[x] Manual checklist steps require real non-empty strings and are never coercively stringified

[x] Valid checklist carries exact verified persistence lineage forward without enabling execution

Verified exact main:

`405fdea64008e21173e7851e8b370b63eae7ef73`

GitHub Actions push Verify #550: 1761 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no persistence owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring for the newer user-action chain;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Completion Evidence Integrity v861-v870 — 2026-09-01

Completed:

[x] Completion evidence accepts only mapping-shaped checklist input

[x] Checklist / guidance / verification / application IDs, SKU, item ID and verified-recorded-at require canonical strings

[x] Exact guidance → verification → application lineage is preserved

[x] Explicit checklist error=False, ready status and persisted-decision verification are required

[x] Non-string completion decisions are not coerced

[x] External-verification and persistence/execution overclaims fail closed

[x] Item count, completed count and checklist item structure are validated

[x] User-reported completion carries verified persistence lineage forward without enabling execution

Verified exact main:

`c788760babc8b0c6becb886f37937f20d5d09028`

GitHub Actions push Verify #567: 1771 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no persistence-owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring for the newer user-action chain;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Completion Persistence Integrity v871-v880 — 2026-09-01

Completed:

[x] Completion persistence accepts only mapping-shaped evidence input

[x] Exact completion → checklist → guidance → verification → application lineage is required

[x] Completion status, decision and user-reported boolean are mutually consistent

[x] Root and revision evidence IDs use canonical deterministic lineage

[x] Malformed storage containers and records fail closed

[x] Explicit save=False is not reported as durable success

[x] Successful persistence carries exact verified lineage and item/revision metadata forward

[x] Completion revisions preserve verified lineage without enabling execution

Verified exact main:

`834df2a9ded1c3e05731a9c249683d15b188c661`

GitHub Actions push Verify #584: 1781 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no persistence-owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring for the newer user-action chain;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Completion Revision Predecessor Integrity v881-v890 — 2026-09-01

Completed:

[x] Completion revision 2+ requires exactly one durable predecessor

[x] Duplicate predecessor IDs fail closed as ambiguous

[x] Predecessor exact verified lineage and user-owned safety state are validated

[x] Predecessor status/decision/report consistency is validated

[x] Revision 3+ requires canonical predecessor revision/root/previous-ID lineage

[x] Duplicate current revision IDs fail closed

[x] Valid root → revision 2 → revision 3 requires actual durable predecessor records

Verified exact main:

`73c349d50dad1a5562a09777df5a69f661869645`

GitHub Actions push Verify #599: 1791 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no persistence-owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Checklist Status Persistence Lineage Integrity v891-v900 — 2026-09-01

Completed:

[x] Checklist-status input and report collection shapes fail closed

[x] Exact checklist → guidance → verification → application lineage is required

[x] Matching persisted USER_REPORT receipts require canonical verified lineage

[x] Matching malformed receipts cannot degrade into NO_USER_REPORTS

[x] Completion revisions require real integers and canonical root/evidence/previous IDs

[x] Duplicate item+revision receipts fail closed as ambiguous

[x] Per-item persisted revision chains must be contiguous from revision 1

[x] Valid aggregate output carries verified persistence lineage while remaining non-executable

Verified exact main:

`3dec82f8aa93c1a35a699aa9270dcfd8e91c1f46`

GitHub Actions push Verify #616: 1801 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no persistence-owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Post-Decision Observation Lineage Integrity v901-v910 — 2026-09-01

Completed:

[x] Canonical checklist-status ID and exact checklist/guidance/verification/application lineage required

[x] Persisted Product Decision verification preserved into observation

[x] USER_REPORTED_COMPLETE requires exact item/reported/completed consistency

[x] Reported/completed item identities remain canonical and non-coercive

[x] Later Product Decision result remains explicit and SKU-bound

[x] Observation carries verified lineage while remaining read-only, non-causal and non-executable

Failed intermediate evidence retained:

`0896d8112971966aec9fb61c7a2250436f19d76a` / Verify #623 / 1804 passed / 7 failed.

Verified exact main:

`c7c864814ec609b0f2c58b4578a522b2e5e8dad1`

GitHub Actions push Verify #626: 1811 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no persistence-owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Post-Decision Outcome Lineage Integrity v911-v920 — 2026-09-01

Completed:

[x] Observation → outcome boundary requires exact persisted Product Decision lineage

[x] Complete USER_REPORT counts and item identities remain canonical

[x] Prior/later decision type, priority, confidence and reasons require canonical contracts

[x] Prior SKU must match observed SKU exactly

[x] Noncanonical MEDIUM priority is rejected

[x] Canonical NONE priority is supported for INSUFFICIENT_DATA outcomes

[x] Valid outcome remains non-causal, externally unverified and non-executable

Verified exact main:

`82867cd9efb6a0b4a187d72ca097ee6bda0c0f39`

GitHub Actions push Verify #634: 1821 passed / 0 failed.

Preserved:

- no Product Decision threshold/rule change;
- no persistence-owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Learning Summary Outcome Integrity v921-v930 — 2026-09-01

Completed:

[x] Non-list outcome collections fail closed

[x] Non-mapping/malformed outcome rows fail closed instead of disappearing

[x] Exact v911-v920 outcome lineage and persisted Product Decision verification required

[x] Complete USER_REPORT evidence remains exact through learning summary

[x] Unsafe or contradictory outcome classification blocks

[x] Duplicate outcome IDs cannot inflate descriptive learning counts

[x] Canonical NONE priority outcomes remain valid; MEDIUM remains rejected

[x] Only a real empty list can produce zero-observation success

Failed intermediate evidence retained:

`21051b20acdfc0036a15d875d01b488283791ff3` / Verify #640 / 1830 passed / 1 failed.

Verified exact main:

`b492b655030791d5e703c8aa607d2763d455e486`

GitHub Actions push Verify #643: 1831 passed / 0 failed.

Preserved:

- no Product Decision threshold/rule change;
- no persistence-owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Learning Evidence Quality Summary Integrity v931-v940 — 2026-09-01

Completed:

[x] Learning summary input and explicit success are validated

[x] Counts are exact integers and never string/missing coercions

[x] Outcome/priority/SKU aggregate maps must be canonical and mathematically consistent

[x] Outcome IDs are exact, unique, and count-bound

[x] Zero evidence requires truly empty aggregates

[x] Existing evidence-quality thresholds remain unchanged

Failed intermediate evidence retained:

`849b0d0e78e441f3080631419ecbc0ea192890ec` / Verify #649 / 1840 passed / 1 failed.

Verified exact main:

`9a504323b6b4bb0adb2a6d5a75507b4c0b6f19f9`

GitHub Actions push Verify #652: 1841 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Learning Confidence Evidence Integrity v941-v950 — 2026-09-01

Completed:

[x] Learning evidence-quality input and explicit success are validated

[x] Counts are exact integers and never string/missing coercions

[x] Quality name and score must match actual sample shape

[x] Outcome/priority/SKU aggregate maps remain mathematically consistent

[x] Outcome IDs remain exact, unique and count-bound

[x] Existing confidence thresholds remain unchanged

[x] Confidence output remains descriptive-only and non-executable

Verified exact main:

`0671c0a0b06c662e935b4dcbf00e4cad12e32175`

GitHub Actions push Verify #660: 1851 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no persistence-owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Action Proposal Result Integrity v951-v960 — 2026-09-01

Completed:

[x] Action proposal result must be a mapping

[x] Proposal safety booleans and automation prohibition are exact

[x] Proposal SKU / priority / decision type / reasons remain Product Decision-bound

[x] Proposal type and confirmation semantics are decision-bound

[x] Proposal exceptions fail closed without secret leakage

[x] Malformed proposal is not cached and cannot enter task-draft lifecycle

[x] Assortment query fails closed instead of counting malformed proposal state

[x] Telegram renders neutral failure without proposal controls

Verified exact main:

`7637177202c21d3f2894105e39137efd86855b8c`

GitHub Actions push Verify #668: 1861 passed / 0 failed.

Integration finding:

- verified Product Decision user-action guidance/checklist remains intentionally unwired from Telegram;
- current durable Product Decision history does not store exact persistence-application receipt lineage;
- do not synthesize lineage IDs or invoke persistence application as a read side effect.

Preserved:

- no Product Decision rule/threshold change;
- no new persistence owner;
- no Product Task Draft execution;
- no Action Executor connection;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision History Context Result Integrity v961-v970 — 2026-09-01

Completed:

[x] History record context is mapping-only and whitelisted

[x] History context cannot overwrite Product Decision identity/error fields

[x] Malformed or exceptional history context becomes explicit unknown/unavailable state

[x] Unknown history count remains None and is not coerced to zero

[x] Invalid history context is not cached

[x] Invalid history context cannot enter task-draft lifecycle

[x] Telegram latest history rejects malformed, cross-SKU and unknown-status records

[x] Telegram task draft attachment requires exact SKU/proposal/revision and non-execution safety

Verified exact main:

`10977368ac4179f1f7168943a38fcdbc01ecfd78`

GitHub Actions push Verify #677: 1871 passed / 0 failed.

Preserved failed evidence:

- `bfcc3551166431288f38ba0c06912133bed56818`: Verify #674, 1870 passed / 1 failed;
- failure was a production NameError in the new draft-copy path;
- final feature head `ab24a87c19072b5bbb3b9efd6b1630b513bf6645`: Verify #675, 1871 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no new persistence owner;
- no Product Task Draft execution;
- no Action Executor connection;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Unit Economics Returns Finance Impact Integrity v971-v980 — 2026-09-01

Completed:

[x] Returns impact requires explicit success/error contract

[x] Complete/classification/finance markers are exact booleans

[x] Required categories and counts are validated without zero coercion

[x] Observed/matched/event count consistency is enforced

[x] Invalid evidence cannot become known zero return cost

[x] Invalid evidence cannot become confirmed risk-adjusted profit

[x] Invalid evidence cannot remove returns from missing data

[x] Valid estimated and confirmed paths preserve prior numeric behavior

Verified exact main:

`db5ab92503f499dfe470402ffefc00b15b9c6e59`

GitHub Actions push Verify #686: 1881 passed / 0 failed.

Preserved failed evidence:

- `b4f0d33d163ee0a81d0252e466519169c55fd1f2`: Verify #683, 1880 passed / 1 failed;
- failure was a legacy cache fixture using a pre-contract minimal success shape;
- production validation remained strict;
- final feature `0a2ece03b60e019b264b5ecda8a010bca873e7bb`: Verify #684, 1881 passed / 0 failed.

Preserved:

- unknown finance values remain unknown;
- no Product Decision threshold/rule change;
- no new persistence owner;
- no Product Task Draft execution;
- no Action Executor connection;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Result Integrity v981-v990 — 2026-09-01

Completed:

[x] Product Decision service result must be a mapping

[x] Unexpected error/code injection is rejected

[x] Product ID and SKU are exact query-bound identity

[x] Decision type and priority pairing is canonical

[x] Confidence, reasons and missing-data contracts are validated

[x] Invalid decision cannot reach history/proposal/cache/draft lifecycle

[x] Invalid decision gets deterministic seller-safe Telegram failure

Verified exact main:

`5f0534bb72dba2471c3c339a69cd7041552dfb4a`

GitHub Actions push Verify #698: 1891 passed / 0 failed.

Cancelled intermediate evidence retained:

- `f21c1ca4b21b57a634a502ecb754e93fabb78e18`: Verify #693 cancelled;
- `689fd2b9db65861f8853251accb0f2a3e0cf86d8`: Verify #694 cancelled.

Failed intermediate evidence retained:

- `8a286947bdc5862834a05794e330d87ef370ffe7`: Verify #695, 1889 passed / 2 failed;
- failure source was a legacy freshness fixture with noncanonical empty reasons;
- final feature `8b90c11763622cc413802a488171738cf2332a1a`: Verify #696, 1891 passed / 0 failed.

Preserved:

- no Product Decision threshold/rule change;
- no new persistence owner;
- no Product Task Draft execution;
- no Action Executor connection;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Assortment Overview Integrity v991-v1000 — 2026-09-01

Completed:

[x] Overview decision rows require explicit success and unique SKU identity

[x] Decision type → priority pairs are canonical

[x] Decision counts are recomputed and exact

[x] Proposal counts are recomputed and exact

[x] Actionable count is recomputed from exact booleans

[x] Nested proposal execution remains prohibited

[x] Contradictory overview state cannot generate seller keyboard

[x] Valid mixed overview remains deterministic and non-mutating

Verified exact main:

`84d714909d5082958bf2bb21a30b7b097eb17955`

GitHub Actions push Verify #709: 1901 passed / 0 failed.

Preserved failed evidence:

- `3fe8ef0caa6b03a5dabbabae463cb0037a4c9ca5`: Verify #704, 1882 passed / 9 failed;
- `86b6e9063c1a9cfa500d4e0409ba6668623c5321`: Verify #705, 1892 passed / 9 failed;
- `0b2da626f71a45adf54f0f9f0dbfd8b5a8e75353`: Verify #706, 1898 passed / 3 failed.

Production validation was not weakened; legacy test fakes were aligned to the canonical producer contract.

Preserved:

- no Product Decision threshold/rule change;
- no new persistence owner;
- no Product Task Draft execution;
- no Action Executor connection;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Task Draft Lifecycle Result Integrity v1001-v1010 — 2026-09-01

Completed:

[x] Task-draft reconcile result requires an exact explicit mapping contract

[x] Lifecycle error/executed/execution_allowed markers are exact safety booleans

[x] stale_count is a non-negative exact integer and equals stale_drafts length

[x] Stale drafts remain exact-SKU and canonical proposal-bound

[x] Current Product Decision revision cannot be reported as stale

[x] Stale draft status is exactly STALE

[x] Stale drafts remain executed=False and execution_allowed=False

[x] Malformed/exceptional lifecycle result fails closed with deterministic non-secret code

[x] Invalid lifecycle result is not cached and assortment query fails closed

[x] Valid lifecycle is attached as a defensive copy

Verified exact main:

`288c6452703eee4082414d1ad36680b4ddf02caa`

GitHub Actions push Verify #717: 1911 passed / 0 failed.

Feature and integration evidence:

- final feature `12e4f1d4f38296b8f46680302478f377121644a8`: Verify #715, 1911 passed / 0 failed;
- PR #336 synthetic `005ac13b1fbb01bb6e95314d1f8c89b994ba85c6`: Verify #716, 1911 passed / 0 failed;
- no failed production SHA in this package.

Preserved:

- no Product Decision rule/threshold change;
- no new persistence owner;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram user-action persistence wiring;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Unit Economics Result Integrity v1011-v1020 — 2026-09-01

Completed:

[x] Unit Economics query exceptions are sanitized before Product Decision generation

[x] Downstream `error` must be an exact boolean

[x] Explicit downstream `error=True` remains unknown economics, never zero

[x] Successful economics requires exact boolean `available`

[x] Malformed/duplicate/non-string `missing_fields` is rejected

[x] Boolean, NaN and infinity decision-finance values are rejected

[x] `available=False` cannot claim profit or margin

[x] Confirmed returns-adjusted profit requires complete returns finance evidence and known per-delivered-unit reserve

[x] Estimated returns profit requires exact estimate readiness plus required estimate evidence

[x] Invalid economics result fails closed with deterministic non-secret code and is not cached

Verified exact main:

`982dc4f58fec6172a4fa99475ae72800c107981f`

GitHub Actions push Verify #727: 1921 passed / 0 failed.

Failed evidence preserved:

- `c27b1fbfba804d36167855228f1881c08c4ef506`: Verify #723, 1917 passed / 4 failed;
- `1114863bdc5b23969fe8cf2d3c9166fe5e7cd523`: Verify #724, 1918 passed / 3 failed.

Final feature and integration evidence:

- final feature `fa9cd0e874347ba00320c8e9c36c85d0efb530a0`: Verify #725, 1921 passed / 0 failed;
- PR #338 synthetic `8014a74ae903863da672ee4b82f9fb565ad3d6cc`: Verify #726, 1921 passed / 0 failed;
- squash main `982dc4f58fec6172a4fa99475ae72800c107981f`: Verify #727, 1921 passed / 0 failed.

Preserved:

- no finance formula or fee subtraction changed;
- unknown finance remains unknown;
- no Product Decision threshold/rule change;
- no new persistence owner;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Operational Metrics Result Integrity v1021-v1030 — 2026-09-01

Completed:

[x] Sales source exceptions are sanitized before Product Decision generation

[x] Stock source exceptions are sanitized before Product Decision generation

[x] Non-mapping operational metrics fail closed

[x] Explicit metrics `error` marker must be boolean when present

[x] Explicit `error=True` remains unavailable/unknown data, never zero

[x] Sales velocity is finite, non-boolean, and non-negative

[x] Sales trend is canonical: GROWING / DECLINING / STABLE

[x] Stock quantity and days-of-stock are finite, non-boolean, and non-negative

[x] Stock priority semantics are canonical, including NO_SALES

[x] Existing `stock_priority` alias contract is preserved and contradictory aliases are rejected

[x] Malformed missing-data/evidence fields fail closed

[x] Invalid operational metrics result is not cached

Verified exact main:

`70466d338951b2b7cc2bb7c48a9d2c7ee2dc91df`

GitHub Actions push Verify #736: 1931 passed / 0 failed.

Failed evidence preserved:

- `678739dea2fa85af3f71933f048f9bfb193fdc62`: Verify #733, 1929 passed / 2 failed.

Final feature and integration evidence:

- final feature `6af041c39b86791821249058d0632070f2f68685`: Verify #734, 1931 passed / 0 failed;
- PR #340 synthetic `7e64fcd23df9fb405c8c422359e3703b6a720f56`: Verify #735, 1931 passed / 0 failed;
- squash main `70466d338951b2b7cc2bb7c48a9d2c7ee2dc91df`: Verify #736, 1931 passed / 0 failed.

Preserved:

- no Product Decision threshold/rule change;
- no finance formula change;
- unknown sales/stock values remain unknown;
- no new persistence owner;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Persistence Commit Receipt Integrity v1031-v1040 — 2026-09-01

Completed:

[x] Base Product Decision history writes no longer ignore storage save results

[x] Rejected/unknown saves cannot return a successful available history context

[x] Failed base writes are removed from in-memory state and retried from known state

[x] Durable persistence application requires explicit record_persistent() support

[x] In-memory-only history cannot issue a durable commit receipt

[x] Successful receipt requires saved=True and persistence_state=COMMITTED

[x] Receipt binds exact SKU, recorded_at, history count, and history context

[x] Product Decision persistence application requires the committed receipt before product_decision_persisted=True

[x] Product Decision persistence verification requires the same receipt before readback verification

[x] No persistence/application lineage is synthesized into history snapshots

Verified exact main:

`7d53fecac126973122270eacfdfc122e50ae3de3`

GitHub Actions push Verify #745: 1941 passed / 0 failed.

Failed evidence preserved:

- `14a0709209228310625dd91871e963a866ab6cc9`: Verify #742, 1940 passed / 1 failed.

Final feature and integration evidence:

- final feature `88372919c9275a51482703e59fe21d8c4d9c5682`: Verify #743, 1941 passed / 0 failed;
- PR #342 synthetic `7e54ca702706ad192eb70da63e351e96efdb31b5`: Verify #744, 1941 passed / 0 failed;
- squash main `7d53fecac126973122270eacfdfc122e50ae3de3`: Verify #745, 1941 passed / 0 failed.

Preserved:

- existing Product Decision History storage remains the persistence owner;
- no Telegram read path invokes persistence application;
- Telegram verified-guidance blocker remains open because application receipt lineage is not durably embedded in history snapshots;
- no Product Decision rule/threshold or finance formula change;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Durable Application Lineage v1041-v1050 — 2026-09-01

Completed:

[x] Persistence application constructs exact lineage before durable Product Decision write

[x] Existing Product Decision History owner validates the complete lineage chain

[x] Lineage binds application/readiness/authorization/eligibility/review/delta/preview IDs, draft_id and SKU

[x] Malformed and cross-SKU lineage is rejected before storage mutation

[x] Durable Product Decision snapshot stores the exact application lineage atomically

[x] COMMITTED persistence receipt returns the same lineage

[x] Persistence application rejects forged receipt lineage

[x] Persistence verification requires exact receipt lineage

[x] Persistence verification requires durable history snapshot lineage to match the exact application

[x] JSON storage restart preserves application lineage

[x] Feedback mutation preserves the snapshot lineage

[x] Restart readback verifies without execution or Ozon mutation

Verified exact main:

`19851b9d40827b3ca5e3889c3858ca32c5602f67`

GitHub Actions push Verify #754: 1951 passed / 0 failed.

Failed evidence preserved:

- `cfeb3528d5f902625819b6897db192bf794fddda`: Verify #751, 1915 passed / 36 failed.

Final feature and integration evidence:

- final feature `5e856591925d2288db871ac9632eab5ee7f7a649`: Verify #752, 1951 passed / 0 failed;
- PR #344 synthetic `13f8cb191c24eb0589cf4f5ba892d7b13b402bc5`: Verify #753, 1951 passed / 0 failed;
- squash main `19851b9d40827b3ca5e3889c3858ca32c5602f67`: Verify #754, 1951 passed / 0 failed.

Preserved:

- Product Decision History remains the only persistence owner;
- application lineage is written, never inferred after the fact;
- Telegram read path still does not invoke persistence application;
- Telegram guidance/checklist wiring is not yet enabled;
- no Product Decision rule/threshold or finance formula change;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Read-Only Persistence Verification v1051-v1060 — 2026-09-01

Completed:

[x] Product Decision History storage exposes explicit durable read receipt

[x] Corrupted JSON/non-list/mixed durable data is distinguishable from no history

[x] latest_persistent() reads storage directly rather than self.records

[x] In-memory-only history cannot become persistence proof

[x] Read-only verifier validates durable read receipt before business semantics

[x] Read-only verifier validates snapshot SKU, recorded_at, decision semantics and stored application lineage

[x] Missing/cross-SKU/broken-chain lineage fails closed

[x] Valid durable history produces canonical PRODUCT_DECISION_PERSISTENCE_VERIFIED payload

[x] Runtime verification ID is produced only after exact persisted application ID validates

[x] verify_latest() performs no save/application/execution/Ozon mutation

Verified exact main:

`b0bfdd5dd79349244ceaf64d1d4df9899211344a`

GitHub Actions push Verify #762: 1961 passed / 0 failed.

Feature and integration evidence:

- final feature `c0da07cbafeb1fe38001729eebca94648149d96b`: Verify #760, 1961 passed / 0 failed;
- PR #346 synthetic `0ccae174a2adfe5c650ca96bf7dcf90ceafaec80`: Verify #761, 1961 passed / 0 failed;
- squash main `b0bfdd5dd79349244ceaf64d1d4df9899211344a`: Verify #762, 1961 passed / 0 failed.

Preserved:

- Product Decision History remains the only persistence owner;
- no persisted application lineage is inferred;
- read-only verification never calls persistence application;
- Telegram guidance/checklist wiring is not yet enabled;
- no Product Decision rule/threshold or finance formula change;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Telegram Verified Product Decision Guidance / Checklist Wiring v1061-v1070 — 2026-09-02

Completed:

[x] Telegram production factory shares one Product Decision History instance between decision query and read-only persistence verifier

[x] Product Decision detail presentation invokes only `verify_latest(sku)`

[x] Telegram never invokes Product Decision persistence application as a read/presentation side effect

[x] Verified durable snapshot must match the currently displayed Product Decision by SKU, recorded_at, decision_type, priority, confidence and reasons

[x] Existing guidance builder is consumed only after canonical durable verification succeeds

[x] Existing checklist builder is consumed only after verified guidance passes safety validation

[x] Malformed/blocked/old/unverified durable state preserves the existing Product Decision card without a false verified claim

[x] Builder/verifier exceptions are contained and do not leak secret error details into Telegram

[x] Valid verified guidance is rendered as a manual checklist with automatic execution explicitly disabled

[x] No Telegram callback/button starts Product Decision execution, Product Task Draft execution or Ozon mutation

Verified exact main:

`dbec4ecfc5f38b31aeba5e86a6d0ad09c40d58bb`

GitHub Actions push Verify #771: 1971 passed / 0 failed.

Failed evidence preserved:

- `f449e7d738b56fb72f39e0836eb2ea3464b899a9`: Verify #768, 1970 passed / 1 failed.

Final feature and integration evidence:

- final feature `09abed3a9db1c1cf90a13d4393bb3771f09c964d`: Verify #769, 1971 passed / 0 failed;
- PR #348 synthetic `400bbfa95038edd3876a2ea0eb4b2e28db65fefb`: Verify #770, 1971 passed / 0 failed;
- squash main `dbec4ecfc5f38b31aeba5e86a6d0ad09c40d58bb`: Verify #771, 1971 passed / 0 failed.

Preserved:

- Product Decision History remains the sole persistence owner;
- read-only Telegram verification uses durable history and stored application lineage;
- no missing persistence/application IDs are inferred;
- no Product Decision rule/threshold or finance formula change;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Telegram Query Exception Containment v1071-v1080 — 2026-09-02

Completed:

[x] Seller-facing Product Decision overview contains `query_all()` exceptions locally

[x] Seller-facing Product Decision detail contains `query(sku)` exceptions locally

[x] Query exceptions return deterministic `PRODUCT_DECISION_QUERY_FAILED`

[x] Overview and detail return seller-specific messages instead of generic Telegram dispatch failure

[x] Exception details are not exposed to the seller response

[x] Query failures are one-shot and are not retried

[x] Keyboard/feedback presentation is not invoked after query exceptions

[x] Explicit downstream `error=True` semantics remain unchanged

[x] Valid overview remains unchanged

[x] Valid detail remains unchanged and preserves defensive-copy behavior

Verified exact main:

`41473566a558bb09899f64d581010b72e4053fbd`

GitHub Actions push Verify #780: 1981 passed / 0 failed.

Failed evidence preserved:

- `31902d6e4f1302a5fe221e091b54bd5e2c4a8f3d`: Verify #777, 1980 passed / 1 failed.

Final feature and integration evidence:

- final feature `30da677a1db0fdca3cd4ac2b0928859e0b9b81a8`: Verify #778, 1981 passed / 0 failed;
- PR #350 synthetic `a0bbb0059c67c3d4e0583f2b13883f5dd3f8857e`: Verify #779, 1981 passed / 0 failed;
- squash main `41473566a558bb09899f64d581010b72e4053fbd`: Verify #780, 1981 passed / 0 failed.

Preserved:

- generic Telegram adapter exception containment remains the outer safety net;
- no retry or duplicate query call introduced;
- no persistence owner or persistence contract changed;
- Product Decision thresholds/rules unchanged;
- finance formulas unchanged;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Financial Telegram Query Exception Containment v1081-v1090 — 2026-09-02

Completed:

[x] Unit Economics product-list source exceptions are contained locally

[x] Returns Finance Impact product-list source exceptions are contained locally

[x] Unit Economics query exceptions are contained locally

[x] Returns Finance Impact query exceptions are contained locally

[x] Unit Economics formatter exceptions are contained locally

[x] Seller responses use deterministic finance-domain failure codes

[x] Internal exception details are not exposed

[x] Financial source/query calls are one-shot and are not retried

[x] Generic Telegram adapter containment remains the outer safety net

[x] Valid Unit Economics and Returns Finance Impact UI remains compatible

Verified exact main:

`0f484141713f2452f451e818caf600d113df6ad4`

GitHub Actions push Verify #788: 1991 passed / 0 failed.

Final feature and integration evidence:

- final feature `6cf579771939ceb765a996fa761a406175e003d3`: Verify #786, 1991 passed / 0 failed;
- PR #352 synthetic `69383b1fcfe87aab31dfb6bb29cd4f73bf051e13`: Verify #787, 1991 passed / 0 failed;
- squash main `0f484141713f2452f451e818caf600d113df6ad4`: Verify #788, 1991 passed / 0 failed.

Preserved:

- finance formulas and calculations unchanged;
- no retry or duplicate finance source/query call;
- no persistence change;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Tax Configuration Persistence & Result Integrity v1091-v1100 — 2026-09-02

Completed:

[x] Persisted tax configuration root must be a mapping

[x] Tax and minimum-tax rates reject booleans, non-numeric values, NaN/inf, negatives and values above 100%

[x] Explicit NONE mode preserves the zero-tax normalization contract

[x] Truncated or malformed persisted tax configuration fails closed as unconfigured instead of raising into startup

[x] Valid tax configuration is serialized before write

[x] Valid tax configuration is written to an fsynced temporary file and atomically replaces the target

[x] Failed atomic replace returns deterministic `TAX_CONFIGURATION_SAVE_FAILED`

[x] Failed write cleans temporary data and preserves the previous durable tax policy

[x] Production `create_telegram_core` survives malformed tax configuration and keeps tax unknown/unconfigured

[x] TaxService formulas and calculation branches are unchanged

Verified exact main:

`38e54ddc6d289f0f75121cc63efa0268ef2784f8`

GitHub Actions push Verify #796: 2001 passed / 0 failed.

Final feature and integration evidence:

- final feature `8cc003f6fa66eb499c67d7d3d74f90c0c75abecf`: Verify #794, 2001 passed / 0 failed;
- PR #354 synthetic `5167b644bc53edc27a40c7b15c7068e0c669d2fc`: Verify #795, 2001 passed / 0 failed;
- squash main `38e54ddc6d289f0f75121cc63efa0268ef2784f8`: Verify #796, 2001 passed / 0 failed.

Preserved:

- existing TaxConfigurationService remains the sole tax-config persistence owner;
- TaxService formulas/calculation semantics unchanged;
- no new retry or execution path;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Tax Calculation Input & Result Integrity v1101-v1110 — 2026-09-02

Completed:

[x] Unsupported tax mode is rejected before numeric conversion

[x] Missing tax mode preserves the explicit unconfigured contract

[x] Revenue and gross-profit inputs reject booleans, non-numeric values and NaN/inf

[x] Tax and minimum-tax rates reject booleans, non-numeric values, NaN/inf, negatives and values above 100%

[x] Explicit NONE mode preserves the existing zero-tax result

[x] Numeric-string compatibility remains supported

[x] Existing negative tax-base clipping remains unchanged

[x] Non-finite/overflow tax calculations fail closed instead of returning NaN/inf

[x] ProductUnitEconomicsProvider continues to map TaxService failures to unknown tax rather than inventing a value

[x] Existing tax formula branches and configured percentages remain unchanged

Verified exact main:

`1bc8cfc745a94c7bfe3442bf2c774947f79bce8b`

GitHub Actions push Verify #804: 2011 passed / 0 failed.

Final feature and integration evidence:

- final feature `85fc4b76baa725cbc586ca39e8454e30a70fb168`: Verify #802, 2011 passed / 0 failed;
- PR #356 synthetic `7d070c91d97e811491849475ddcd65552eadd1c7`: Verify #803, 2011 passed / 0 failed;
- squash main `1bc8cfc745a94c7bfe3442bf2c774947f79bce8b`: Verify #804, 2011 passed / 0 failed.

Preserved:

- TaxConfigurationService persistence contract unchanged;
- TaxService formula branches/percentages unchanged;
- no new retry or execution path;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Advertising & Expense Finite Result Integrity v1111-v1120 — 2026-09-02

Completed:

[x] Advertising cost rejects boolean and NaN/inf values

[x] Missing advertising remains explicit unknown; zero remains explicit configured zero

[x] Negative advertising retains the existing explicit rejection contract

[x] Campaign aggregation ignores malformed/non-finite/negative/bool rows under the existing tolerant list model

[x] Advertising aggregate overflow fails closed instead of returning infinity

[x] Other-expense aggregation ignores malformed/non-finite/negative/bool rows under the existing tolerant list model

[x] Other-expense aggregate overflow fails closed instead of returning infinity

[x] Single expense rejects boolean and NaN/inf values

[x] Existing numeric-string compatibility remains

[x] BusinessAnalyticsService does not emit business profit when advertising is invalid or other-expense aggregation overflows

Verified exact main:

`cb0148a1d6ad14b2e53f18ca948b66e8422da3c4`

GitHub Actions push Verify #812: 2021 passed / 0 failed.

Final feature and integration evidence:

- final feature `c45284c99d70a45b1bed2b5f62049a7bb5c40df6`: Verify #810, 2021 passed / 0 failed;
- PR #358 synthetic `8b8bcfda3b61518637637a05b1b60109a7907192`: Verify #811, 2021 passed / 0 failed;
- squash main `cb0148a1d6ad14b2e53f18ca948b66e8422da3c4`: Verify #812, 2021 passed / 0 failed.

Preserved:

- finance formulas unchanged;
- existing AdvertisingService/ExpenseService owners unchanged;
- no persistence contract change;
- no new retry or execution path;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Store Profit Aggregation Result Integrity v1121-v1130 — 2026-09-02

Completed:

[x] Store-profit input container is validated

[x] Non-mapping product-profit records fail closed

[x] sales_count rejects boolean, negative, fractional, non-numeric and non-finite values

[x] Financial aggregate fields reject boolean, non-numeric and NaN/inf values

[x] Aggregate overflow and non-finite margin fail closed

[x] Failed product-profit rows remain skipped

[x] Missing numeric fields retain existing zero defaults

[x] Numeric-string and loss-product compatibility remain

[x] BusinessAnalytics propagates store-profit failure before downstream finance calculations

[x] SalesIntelligence and AssistantSalesExecutor preserve the failure end-to-end

Verified exact main:

`87c95cf2eb139cd8782d8df79d43b2313939bba0`

GitHub Actions push Verify #820: 2031 passed / 0 failed.

Final feature and integration evidence:

- final feature `a888d3c4aa35aaba7526df186bfdbdd2902f9369`: Verify #818, 2031 passed / 0 failed;
- PR #360 synthetic `decce34f5a0cf348a4f9ab1ab80c50179d5e9d2b`: Verify #819, 2031 passed / 0 failed;
- squash main `87c95cf2eb139cd8782d8df79d43b2313939bba0`: Verify #820, 2031 passed / 0 failed.

Preserved:

- StoreProfitService success schema and missing-field zero defaults;
- aggregation formulas and margin formula unchanged;
- no persistence change;
- no new retry or execution path;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Business Profit Calculation Result Integrity v1131-v1140 — 2026-09-02

Completed:

[x] Non-mapping store-profit/tax inputs fail closed

[x] Malformed store/tax error/configured markers fail closed

[x] Gross-sales/gross-profit inputs reject boolean, non-numeric and NaN/inf

[x] Advertising/other-expense inputs reject boolean, negative, non-numeric and NaN/inf

[x] Tax amount rejects boolean, negative, non-numeric and NaN/inf

[x] Unknown tax remains unknown rather than zero

[x] Existing tax-error message/presentation contract remains compatible

[x] Business-profit and margin overflow/non-finite results fail closed

[x] Valid numeric strings and existing formulas remain compatible

[x] New BUSINESS_PROFIT_* integrity failures propagate through BusinessAnalytics, SalesIntelligence and AssistantSalesExecutor

Verified exact main:

`189455bb5b44c47bbf5abf188d1b456dad14b1ba`

GitHub Actions push Verify #828: 2041 passed / 0 failed.

Final feature and integration evidence:

- final feature `98edb5b5500c25e53b77237016afe3a223360ab8`: Verify #826, 2041 passed / 0 failed;
- PR #362 synthetic `6e335e508c07903d6e4488f1aac40d28a9e4152f`: Verify #827, 2041 passed / 0 failed;
- squash main `189455bb5b44c47bbf5abf188d1b456dad14b1ba`: Verify #828, 2041 passed / 0 failed.

Preserved:

- business-profit/margin formulas unchanged;
- TaxService/tax formulas unchanged;
- no persistence change;
- no new retry or execution path;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Finance Period Aggregation Result Integrity v1141-v1150 — 2026-09-02

Completed:

[x] Daily finance source exceptions are contained as failed days with sanitized seller-safe evidence

[x] Non-mapping daily finance results fail closed instead of raising during aggregation

[x] Malformed explicit error markers fail the affected day

[x] Operations and sales counters reject boolean, negative, fractional, non-numeric and NaN/inf values

[x] Finance amount fields reject boolean, non-numeric and NaN/inf values

[x] Malformed or non-finite fee breakdown values fail the whole affected day

[x] Invalid days do not partially commit counters, amount totals or fee breakdown totals

[x] Partial periods retain only fully valid days and preserve the existing partial-success contract

[x] Aggregate amount/fee overflow fails closed with FINANCE_PERIOD_AGGREGATE_INVALID

[x] Valid numeric strings and signed fee values remain compatible

[x] StoreAnalytics finance path preserves contained source failures

Verified exact main:

`d1655adf6719e6000f996b4635253c6b99193ba3`

GitHub Actions push Verify #837: 2051 passed / 0 failed.

Final feature and integration evidence:

- failed intermediate `f54132ebf109240242a87037a81b1db5ed052d5b`: Verify #834, 2050 passed / 1 failed; test-only false positive remains failed evidence;
- final feature `52661a7c37068759d20797644943a3b9e5e5ebcc`: Verify #835, 2051 passed / 0 failed;
- PR #364 synthetic `ef001cc855661041bd3987604496d03e55acaf30`: Verify #836, 2051 passed / 0 failed;
- squash main `d1655adf6719e6000f996b4635253c6b99193ba3`: Verify #837, 2051 passed / 0 failed.

Preserved:

- FinanceAnalyticsService amount/fee formulas unchanged;
- existing partial-period success semantics unchanged;
- no persistence change;
- no new retry or execution path;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Period Profit Summary Input & Result Integrity v1151-v1160 — 2026-09-02

Completed:

[x] Daily FinanceService exceptions are contained as seller-safe period-profit failures

[x] Non-mapping daily finance results fail closed

[x] Malformed explicit daily error markers fail closed

[x] sales_count rejects boolean, negative, fractional, non-numeric and NaN/inf values

[x] Period-profit finance amount fields reject boolean, non-numeric and NaN/inf values

[x] fee_breakdown requires a mapping with finite numeric amounts

[x] Cost inputs reject boolean, negative, non-numeric and NaN/inf values

[x] Cost source exceptions are contained without leaking exception text

[x] Invalid tax-rate configuration fails closed instead of raising during service construction

[x] Product/day/period amount and fee aggregate overflow fails closed

[x] Valid numeric strings and signed fee values remain compatible

[x] PeriodProfitQueryService and AssistantPeriodProfitRuntimeService preserve integrity failures end-to-end

Verified exact main:

`0ca4d226f3f75e2b20035a87a13b1a10d6c71581`

GitHub Actions push Verify #849: 2061 passed / 0 failed.

Final feature and integration evidence:

- final feature `4ab53fe054504c633fbcd6fb708ccb7dc557eaa4`: Verify #847, 2061 passed / 0 failed;
- PR #367 synthetic `a9030acff2031b118c0c0600c008804c3d6ff08a`: Verify #848, 2061 passed / 0 failed;
- squash main `0ca4d226f3f75e2b20035a87a13b1a10d6c71581`: Verify #849, 2061 passed / 0 failed;
- no failed production SHA occurred in this package.

Preserved:

- period-profit formula `profit = net_accrual - product_cost - tax` unchanged;
- configured tax multiplication semantics unchanged;
- no persistence change;
- no new retry or execution path;
- Period Profit route remains read-only;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Telegram Period Profit Analyst Wiring v1161-v1170 — 2026-09-03

Completed:

[x] Period-profit runtime wired into production Telegram core

[x] Telegram main menu exposes "💵 Прибыль за период"

[x] Today / 7 / 28 / 56 / 90-day read-only period menu

[x] Natural-language requests such as "прибыль за 28 дней"

[x] Direct analytical text is rendered as Telegram text instead of Python dict output

[x] Period-profit callback success requires read_only=True

[x] Period-profit callback success requires executed=False

[x] Runtime exceptions are contained with seller-safe failure

[x] Malformed or execution-adjacent callback results fail closed

[x] Existing partial-core test fixtures remain backward compatible

Verification:

- entering exact main `bb2e444b5a7ee6caa9cc4e39adccc5df64949835`: Verify #859, 2061 passed / 0 failed;
- failed intermediate `e7fce70c39f976e97bf78687621ace5125f9d30a`: Verify #866, 2069 passed / 2 failed;
- final feature `9c5d14f0220e5f13ee0a7d834855f7e07db58cab`: Verify #868, 2071 passed / 0 failed;
- PR #369 synthetic `04b20cc49a253bfb357626cf62a71b779a75112e`: Verify #869, 2071 passed / 0 failed;
- squash main `d06a5f8cc23814e3177f58f6182bef6fbceb0697`: Verify #870, 2071 passed / 0 failed.

Current product boundary:

- assistant is a read-only analyst/advisor;
- Ozon price, advertising budget/bid, stock/replenishment, product-card and other seller mutations are out of scope;
- recommendations, checklists and drafts do not grant execution permission;
- `data/users.json` unchanged by this package;
- `externally_verified=False`.

---

# Telegram Custom Period Date Input v1171-v1180 — 2026-09-03

Completed:

[x] Localized custom Period Profit input in `ДД.ММ.ГГГГ`

[x] Example `01.05.2026 - 03.09.2026` routes through production Period Profit

[x] Single-digit day/month input remains accepted

[x] En dash and em dash separators remain accepted

[x] Existing ISO `YYYY-MM-DD` input remains supported

[x] Localized dates normalize to ISO before the Period Profit query layer

[x] Invalid calendar dates fail closed without finance query

[x] Incomplete custom date input fails closed

[x] Missing-period help now shows seller-friendly localized date format

[x] Localized custom Period Profit bypasses the general execution flow

Verification:

- entering exact main `fa30bafeecfa9291175e7f1c4ac0ad2c078b4607`: Verify #881, 2071 passed / 0 failed;
- final feature `62b040e392514bc410b34d82eccb8e0385b9c548`: Verify #884, 2081 passed / 0 failed;
- PR #371 synthetic `b865b551289ba4592d8d32594323ea8a6dc64c61`: Verify #885, 2081 passed / 0 failed;
- squash main `05f94da42e21c5ad5f7d78cb7f55bb2d40730f77`: Verify #886, 2081 passed / 0 failed;
- no failed production SHA occurred in this package.

Preserved:

- Decision 036 read-only Ozon analyst boundary;
- no finance formula changes;
- no Product Decision/Product Task Draft execution;
- no Action Executor connection;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Tax Policy Production Availability v1181-v1190 — 2026-09-03

Completed:

[x] Restored repository production tax policy `USN_INCOME / 6%`

[x] Clean Telegram deployment receives configured tax policy

[x] Explicit environment tax fallback when persisted file is absent

[x] Environment fallback requires explicit `TAX_MODE`

[x] Missing policy remains unknown rather than zero

[x] Invalid environment policy fails closed

[x] Persisted policy has precedence over environment

[x] Malformed persisted policy does not silently fall back

[x] hook-2-like current economics calculates 6.00 ₽ tax at 100 ₽ tax base

[x] hook-2-like base net profit calculates to 35.83 ₽ before returns adjustment

Verification:

- entering exact main `8ca28c36249a052fdf83cfd5ab86a13d986cbb1c`: Verify #896, 2081 passed / 0 failed;
- final feature `1d0df2799fb87b57d916843a96a080389e2ac07b`: Verify #900, 2091 passed / 0 failed;
- PR #373 synthetic `a6493407f0bb915f366573404fcffd220e6757a1`: Verify #901, 2091 passed / 0 failed;
- squash main `9c9d379e36edf2123a466ad2b3cd1d000d81bae3`: Verify #902, 2091 passed / 0 failed;
- no failed production SHA occurred in this package.

Preserved:

- Decision 036 read-only analyst boundary;
- missing tax is never interpreted as zero;
- returns/non-buyout evidence remains separate;
- no Product Decision/Product Task Draft execution;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Period Profit Returns Protobuf Timestamp Compatibility v1191-v1200 — 2026-09-03

Completed:

[x] Reproduced live Ozon protobuf Timestamp failure

[x] Identified Period Profit return-evidence path as source

[x] Date-only Returns API start normalized to RFC3339 UTC start-of-day

[x] Date-only Returns API end normalized to RFC3339 UTC end-of-day

[x] Existing full RFC3339 timestamps preserved

[x] Custom Period Profit ranges reach Returns API with valid timestamps

[x] Preset Period Profit ranges reach Returns API with valid timestamps

[x] Existing Returns filter/pagination/timeout contract preserved

[x] Return evidence remains read-only and non-financial

Verification:

- entering exact main `d3f32e2ca2e30192a59c4551cf5633dfa0941ec6`: Verify #912, 2091 passed / 0 failed;
- final feature `9e2c5b27a1df9f32c8e950766abc809ba93f7976`: Verify #918, 2101 passed / 0 failed;
- PR #375 synthetic `86bc4a07477e910fcaf56a1a1b908fa28a4a68f5`: Verify #919, 2101 passed / 0 failed;
- squash main `c1c3da7cb69d6ce2af550e57bc6c5e38a0bb8a89`: Verify #920, 2101 passed / 0 failed;
- no failed production SHA occurred.

Preserved:

- Decision 036;
- no Ozon mutation;
- no execution changes;
- no finance formula changes;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Period Profit Data Completeness Integrity v1201-v1210 — 2026-09-03

Completed:

[x] Persisted SQLite product tuples normalized for Period Profit

[x] False-success zero summary over zero usable products blocked

[x] Empty/malformed product sets fail with PERIOD_PROFIT_PRODUCTS_UNAVAILABLE

[x] Existing dict product contract preserved

[x] Returns evidence paginates beyond the 500-record first page

[x] Pagination advances via has_next + last_id

[x] Pagination bounded to 10 pages

[x] Complete return counts marked exact

[x] Incomplete return counts marked as lower bounds

[x] Telegram partial-return wording uses "как минимум N"

[x] Legacy READY return-evidence response compatibility preserved

Verification:

- entering exact main `5e8e74a78e2c5aa41ed59378c27a0f1ed7b55397`: Verify #930, 2101 passed / 0 failed;
- failed intermediate `e3d8b2ed1600e3759135bda4f62865ba38a43ae9`: Verify #935, 2103 passed / 2 failed;
- failed intermediate `49c02ae1790b7d395794932e7ac4fa95cbac1644`: Verify #936, 2109 passed / 2 failed;
- final feature `16c53622612b72bce2aa43fd97d5ff66d47466c3`: Verify #937, 2111 passed / 0 failed;
- PR #377 synthetic `f1593267f67339f2dd68d235056cdbc69960160a`: Verify #938, 2111 passed / 0 failed;
- squash main `7b2b570278c9cc71f3eb6dbb23b5554d41de07f7`: Verify #939, 2111 passed / 0 failed.

Preserved:

- Decision 036 read-only analyst boundary;
- no finance formula change;
- no return-cost inference;
- no Ozon mutation or execution changes;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Period Profit Tax Rate Unit Integrity v1211-v1220 — 2026-09-03

Completed:

[x] Live 600% Period Profit tax bug reproduced

[x] Production Period Profit now reads validated TaxConfigurationService policy

[x] USN Income 6.0% converts to 0.06 fraction

[x] NONE converts to zero fraction

[x] Unsupported USN Income Minus Expenses fails closed

[x] Non-finite/invalid tax percentages fail closed

[x] PeriodProfitSummaryService rejects tax multipliers above 1.0

[x] Seller live sample regression: tax 80 902.27 ₽, profit 310 701.55 ₽, margin 23.04%

Verification:

- entering exact main `590b068ef46f58e56509ac038759f465975c9a8a`: Verify #949, 2111 passed / 0 failed;
- failed `a7d5cead4c7c49907d6d045b54a3cec30d48efad`: Verify #953, 2110 passed / 1 failed;
- failed `ee463cd1000113998ae5b895da02334bb5a5f495`: Verify #954, 2120 passed / 1 failed;
- final feature `4c50429bc4c2f6515d80b497b85fe8c9663e24eb`: Verify #955, 2121 passed / 0 failed;
- PR #379 synthetic `68c0f7360dd93738377f7111f5f4732d0b4d48af`: Verify #956, 2121 passed / 0 failed;
- squash main `2f438bd6bb739938cee4fe56b83af8f4a563f942`: Verify #957, 2121 passed / 0 failed.

Preserved:

- Decision 036;
- read-only Period Profit;
- no Ozon mutation or execution changes;
- `data/users.json` unchanged;
- `externally_verified=False`.

Next seller-requested presentation work:
- add percent-of-revenue in parentheses for each Period Profit monetary line.

---

# Period Profit Revenue Share Presentation v1221-v1230 — 2026-09-03

Completed:

[x] Revenue line shows 100.00%

[x] Ozon net accrual shows share of revenue

[x] Commission / logistics / acquiring / other fees show share of revenue

[x] Product cost shows share of revenue

[x] Tax shows share of revenue

[x] Profit shows share of revenue

[x] Negative profit keeps negative share

[x] Zero revenue suppresses derived shares

[x] Existing comparison percentage meaning preserved

[x] Existing margin and scope warnings preserved

Verification:

- entering exact main `5cb69fed7bc44fcd5f66a8a004e625bee9993953`: Verify #967, 2121 passed / 0 failed;
- final feature `77994ccb67c060f7c01694ac65eea5c8aec24e1d`: Verify #970, 2131 passed / 0 failed;
- PR #381 synthetic `b9a72b875081d6f12fe7f5b50d4b0c6f6af13e89`: Verify #971, 2131 passed / 0 failed;
- squash main `08d0d0fa6860101921ead603ec4a00b95c9ee8bf`: Verify #972, 2131 passed / 0 failed.

Preserved:

- Decision 036;
- presentation-only change;
- no financial formula changes;
- no Ozon mutation or execution changes;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Finance Accrual Pagination & Read Session Integrity v1231-v1240 — 2026-09-03

Completed:

[x] Ozon accrual-by-day first request sends required empty last_id

[x] Finance accrual pages are read until cursor exhaustion

[x] Malformed page responses fail closed

[x] Repeated pagination cursors fail closed

[x] Page-cap exhaustion fails closed instead of returning partial finance as complete

[x] Target SKU evidence on later accrual pages is included

[x] Same calendar day is reused for multiple SKUs inside one read session

[x] Each Period Profit calculation starts a fresh finance read session

[x] Read-session failures are contained without leaking private exception text

Verification:

- entering exact main `400ca040d743dc7db93480605ebd62a7fe9b02f3`: Verify #984, 2131 passed / 0 failed;
- failed `8d159ed09410ed978bef6cfdb5719a67bc5491b1`: Verify #990, 2140 passed / 1 failed;
- final feature `ad215b8d86c547e740dcb3583e7b7f580e9fb823`: Verify #991, 2141 passed / 0 failed;
- PR #383 synthetic `4b1f8e48de3f92c6aecc590232697890c8814d08`: Verify #992, 2141 passed / 0 failed;
- squash main `e66125d5e2c737497762178bef86dd36a62721f3`: Verify #993, 2141 passed / 0 failed.

Preserved:

- Decision 036;
- read-only finance retrieval;
- no financial formula changes;
- no Ozon mutation or execution changes;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Account-Level Ozon Profit Reconciliation v1241-v1250 — 2026-09-03

Completed:

[x] Decision 037 account-level Ozon monetary authority

[x] Account-level daily revenue/net accrual/fee totals drive Period Profit V2

[x] SKU-level finance remains COGS and product-revenue evidence

[x] Product revenue must reconcile to account revenue within 0.01 RUB

[x] Revenue coverage mismatch fails closed

[x] Account-minus-SKU net reconciliation is exposed

[x] Account-level charges without SKU are included once

[x] Multi-SKU posting-level net duplication is corrected by account total

[x] Account-level fee breakdown replaces summed SKU fee breakdown

[x] Mapped Ozon expenses remain evidence and are never deducted twice

Verification:

- entering exact main `0aa27a1267b9d54f1207455b05e32db843091d86`: Verify #1003, 2141 passed / 0 failed;
- final feature `a0e528f36b1b4721af0e8d0b419c414d20fabea6`: Verify #1010, 2151 passed / 0 failed;
- PR #385 synthetic `4a361a58d62e56c2e2aa4c608620ae86992ac05f`: Verify #1011, 2151 passed / 0 failed;
- squash main `a359e3d8e68784849caa659dec0123fb15dc6932`: Verify #1012, 2151 passed / 0 failed.

Preserved:

- Decision 036;
- read-only analytics;
- no Ozon mutation;
- no unsupported accounting-net-profit claim;
- `data/users.json` unchanged;
- `externally_verified=False`.

Next accounting gap:
- return-related COGS reversal / recovered-goods evidence;
- then non-Ozon overhead/taxes if the seller provides them.

---

# Return COGS Recovery Evidence v1251-v1260 — 2026-09-03

Completed:

[x] Nested Returns API product / status / compensation evidence preserved

[x] Customer-return units at return-place exposed as candidate recovery

[x] Candidate recovery value calculated from current configured product cost

[x] Compensated returns separated from COGS recovery candidates

[x] Unproven return statuses remain unresolved

[x] Missing product cost remains unknown, not zero

[x] Partial return sample cannot become complete recovery evidence

[x] Historical cost basis remains unconfirmed

[x] Originating sale-period lineage remains unconfirmed

[x] Saleable inventory recovery remains unconfirmed

[x] Period/accounting COGS recovery remains unconfirmed

[x] Candidate recovery never changes Period Profit

[x] Telegram and coverage expose candidate evidence and limitations

Verification:

- entering exact main `55942648266e9ca4fbb3d3380180c3a67bfc4c56`: Verify #1022, 2151 passed / 0 failed;
- failed `2339d8aa8da1ec43c3298be2da8506a1e6dd8b9b`: Verify #1033, 2159 passed / 2 failed;
- final feature `30f3edafd9d2af603f2277701cb13492a334dd30`: Verify #1038, 2161 passed / 0 failed;
- PR #387 synthetic `c5947439450297dabb353b3dfd125e3fc6417576`: Verify #1039, 2161 passed / 0 failed;
- squash main `d845c7183ef5a914853a15b788e18b0cebfd1c93`: Verify #1040, 2161 passed / 0 failed.

Preserved:

- Decision 036;
- Decision 037;
- account-level Ozon monetary authority;
- no automatic return COGS reversal;
- no accounting net-profit claim;
- `data/users.json` unchanged;
- `externally_verified=False`.

Next accounting priority:
- explicit seller-configured non-Ozon operating expenses;
- unknown external expense remains unknown, never zero.

---

# External Operating Expense Coverage v1261-v1270 — 2026-09-03

Completed:

[x] Decision 038 external operating expense evidence and coverage contract

[x] Existing local `expenses` rows retained as explicit seller-entered external expense evidence

[x] `expense_coverage` intervals added as explicit completeness confirmation

[x] Requested-period coverage is complete only when every calendar day is covered

[x] Empty uncovered period remains unknown, not zero

[x] Empty fully covered period becomes explicit confirmed 0 ₽ external expense

[x] Partial expense rows produce observed adjusted profit only

[x] Complete coverage permits complete profit-after-external-expenses adjustment

[x] Invalid expense dates fail closed

[x] Boolean, NaN and infinite expense amounts fail closed

[x] Period Profit Telegram text distinguishes base profit, entered expenses and coverage completeness

[x] Ozon advertising/storage/return charges already inside account net accrual are never subtracted again

[x] `confirm_expense_coverage.py` provides explicit local coverage confirmation

Derived formula:

`profit_after_external_expenses = period_profit - external_expenses`

The base Period Profit formula and Decision 037 account-level Ozon monetary authority remain unchanged.

Verification:

- entering exact docs-reconciled main `9a29e853727c82abdf75b1992c45c532bd45e3ef`: Verify #1050, 2161 passed / 0 failed;
- failed `55d8f189dc170cc524aa8798aea42b1b7ae6251c`: Verify #1054, 2150 passed / 11 failed;
- failed `9f32163739d849dfe3681a9de6358fb64db40100`: Verify #1055, 2150 passed / 11 failed;
- failed `e788e5110109eb678767313278580989b192f689`: Verify #1060, 2160 passed / 1 failed;
- cancelled intermediate SHAs carry no transferable success evidence;
- final feature `07f9a35eb238280e95b52bc14d18cc6aba735703`: Verify #1062, 2171 passed / 0 failed;
- PR #389 synthetic `77dd43cfeb36ebe0066f8747c6c51580083848a6`: Verify #1063, 2171 passed / 0 failed;
- squash main `875cc4a783a48eb9a9059b9e2e9ba85316fbdc0d`: Verify #1064, 2171 passed / 0 failed.

Preserved:

- Decision 036;
- Decision 037;
- Decision 038;
- account-level Ozon monetary authority;
- no double subtraction of Ozon expenses;
- no automatic return COGS reversal;
- no accounting net-profit claim;
- `data/users.json` unchanged;
- `externally_verified=False`.

Next accounting priority:
- prove return-related COGS recovery with stronger historical cost, sale-period lineage and saleable/restored inventory evidence;
- keep candidate recovery out of profit until that proof exists;
- then address taxes/accounting adjustments outside the configured tax policy and any uncovered external-expense periods.

---

# Return Sale-Period Lineage Evidence v1271-v1280 — 2026-09-03

Completed:

[x] Positive sale posting evidence extracted from Ozon daily finance

[x] Sale evidence reuses the Period Profit FinanceService read-session cache

[x] Return records matched to positive sale evidence by posting_number + SKU

[x] Same posting with a different SKU does not confirm lineage

[x] One unique positive sale-accrual date inside the selected period is matched lineage

[x] Multiple positive sale dates remain ambiguous

[x] Missing finance days keep lineage partial

[x] Malformed positive-sale evidence cannot become clean evidence

[x] Incomplete Returns pagination prevents aggregate sale-period confirmation

[x] Return COGS candidate records expose lineage status and matched accrual date

[x] Telegram explains confirmed or partial selected-period lineage

[x] Period Profit coverage exposes sale-lineage confirmation without changing profit

Preserved:

- `confirmed_cogs_recovery_amount=0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- `historical_cost_basis_confirmed=False`;
- `saleable_inventory_recovery_confirmed=False`;
- Decision 036;
- Decision 037;
- Decision 038;
- no Ozon mutation;
- no profit-formula change;
- no persistence-contract change;
- no double subtraction;
- `data/users.json` unchanged;
- `externally_verified=False`.

Verification:

- entering exact docs-reconciled main `356fa301a9025e15a5a9fbb94da706d10670416a`: Verify #1074, 2171 passed / 0 failed;
- failed `db2c6c0fa900720c303a8f8face32ef3eec3be11`: Verify #1081, 2170 passed / 1 failed;
- cancelled intermediate SHAs carry no transferable success evidence;
- final feature `e96fb63007647857045f226c9c41fd8157ae962e`: Verify #1083, 2185 passed / 0 failed;
- PR #391 synthetic `26d6ca0e9b2ef2b4a358cc6a517bd13bf152bffc`: Verify #1084, 2185 passed / 0 failed;
- squash main `5c0ed4bd40207e3f4bcce3770e89e71e163288b1`: Verify #1085, 2185 passed / 0 failed.

Next accounting priority:

- add evidence-bound historical product cost history applicable to originating sales without backfilling unknown history by assumption;
- separately prove saleable/restored inventory recovery;
- keep COGS reversal blocked until both are proven;
- then resolve compensation timing/accounting and remaining external tax/expense gaps.

---

# Historical Product Cost Evidence v1281-v1290 — 2026-09-03

Completed:

[x] Decision 039 versioned historical product cost evidence contract

[x] Separate append-only `product_cost_history` table

[x] Existing mutable `product_costs` current-cost contract preserved

[x] No automatic migration/backfill from current cost into history

[x] Explicit `effective_from` required for historical cost versions

[x] Duplicate `product_id + effective_from` versions rejected

[x] Historical lookup selects latest explicit version effective on sale date

[x] Identifier ambiguity remains unconfirmed

[x] Dates before first explicit version remain unknown

[x] `record_product_cost_history.py` added for explicit local evidence input

[x] Return COGS candidates resolve historical cost only after matched sale lineage

[x] Historical candidate value exposed without changing Period Profit

[x] Telegram distinguishes current-cost diagnostic value from historical-cost evidence

[x] Coverage exposes historical cost confirmation state

Preserved:

- `saleable_inventory_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- Decision 036;
- Decision 037;
- Decision 038;
- no Period Profit formula change;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- `data/users.json` unchanged;
- `externally_verified=False`.

Verification:

- entering exact docs-reconciled main `212df575cc60a809032954d425902fad86623956`: Verify #1095, 2185 passed / 0 failed;
- no failed production SHA occurred;
- cancelled intermediate SHAs carry no transferable success evidence;
- final feature `f3fcb80588f394eb05e5944ca2812ed59adf7649`: Verify #1103, 2195 passed / 0 failed;
- PR #393 synthetic `672e18f904768742917df9c808c48ec476d9fd3e`: Verify #1104, 2195 passed / 0 failed;
- squash main `9ca4497dda61615076b8203d0404502630ab7e81`: Verify #1105, 2195 passed / 0 failed.

Next accounting priority:

- prove saleable/restored inventory recovery after customer returns;
- distinguish saleable recovery, unresolved/non-saleable outcomes and compensation;
- prevent double counting between inventory recovery and Ozon compensation;
- keep automatic COGS reversal blocked until recovery-state evidence is complete.

---

# Return Inventory Recovery Evidence v1291-v1300 — 2026-09-03

Completed:

[x] Decision 040 explicit return-level inventory recovery evidence contract

[x] Append-only `return_inventory_recovery_history`

[x] Explicit `SALEABLE_RESTORED` and `NON_SALEABLE` states

[x] Exact return_id + posting_number + SKU identity required

[x] Candidate quantity must exactly match recovery evidence quantity

[x] Missing recovery evidence remains unknown

[x] Identity drift remains conflicting/unconfirmed evidence

[x] Stock snapshots/deltas are not accepted as automatic recovery proof

[x] Compensated returns remain outside automatic saleable recovery

[x] Return COGS candidate rows expose recovery state/source/date

[x] Coverage exposes inventory recovery state

[x] Telegram explains confirmed/partial recovery state

Preserved:

- `recovery_period_attribution_confirmed=False`;
- `confirmed_cogs_recovery_amount=0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- Decision 036/037/038/039;
- no Period Profit formula change;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.

Verification:

- entering exact docs-reconciled main `7f859d1073338c5c0144edea8fe15574460e5210`: Verify #1115, 2195 passed / 0 failed;
- failed `41b409edcd2a96016bf49e8e8303a7aec00c1886`: Verify #1125, compile failure;
- failed `4643126328c9e461712aae30f5f7a694a7549e89`: Verify #1126, compile failure;
- failed `d90549d21c8fb46b0a9012c205520c68e012dbfa`: Verify #1127, compile failure;
- failed `13e4cfbacf617bb60c5b897137b619f079c3d500`: Verify #1128, 2203 passed / 5 failed;
- cancelled intermediate SHAs carry no transferable success evidence;
- final feature `1a83e5466bfebd79370e9576ce00b43b79bb668d`: Verify #1129, 2208 passed / 0 failed;
- PR #395 synthetic `7d7b3a5e180a2505850345cc753a7d40ba391cbf`: Verify #1130, 2208 passed / 0 failed;
- squash main `3f82b65054a2a7a48b9918803c197377bdb3557f`: Verify #1131, 2208 passed / 0 failed.

Next accounting priority:

- prove the accounting period in which a confirmed saleable return recovery should reverse COGS;
- verify originating-sale quantity consistency;
- keep compensation treatment separate and prevent double counting;
- keep automatic COGS reversal blocked until these remaining facts are complete.

---

# Period Profit Tenant Context Propagation — 2026-09-14

Completed:

[x] Traced Telegram callback/text production wiring through Period Profit finance prefetch
[x] Identified lost tenant ContextVar at ThreadPoolExecutor boundary
[x] Propagated an independent request context into every READ-ONLY finance worker
[x] Covered 7D, 28D, 56D, 90D, and a custom date range through TelegramBotService
[x] Preserved fail-closed finance/quantity evidence and historical/Return COGS authority

---

# Safe Period Profit Finance Diagnostics — 2026-09-14

Completed:

[x] Preserve safe finance failure identity across the parallel prefetch boundary
[x] Expose only sanitized diagnostic codes in Telegram
[x] Keep Ozon payloads, credentials, identifiers, and amounts hidden

---

# Period Profit Monetary Validation Stage Diagnostics — 2026-09-14

Completed:

[x] Distinguish accrual list/record, total amount, posting, products, commission, and sale-component blockers
[x] Preserve the existing fail-closed monetary result
[x] Expose no payload, identifiers, credentials, or monetary values

---

# Period Profit Related-SKU Runtime Base Fix — 2026-09-14

Completed:

[x] Traced live FINANCE_PERIOD_PROFIT_MONEY_UNAVAILABLE_COMMISSION to the #558 client inheritance regression
[x] Restored PeriodProfitRuntimeOzonClient as the related-SKU client's finance-normalization base
[x] Preserved account total_amount for non-sale postings without inventing SKU revenue or quantity
[x] Kept malformed/partial commission evidence fail-closed
[x] Preserved historical effective-cost authority and Return COGS gates

---

# Selected-SKU bounded reverse identity lookup — 2026-09-20

Completed:

[x] Proved the remaining latency was account-wide `/v3/posting/fbo/list` pagination
[x] Replaced hundreds of FBO pages with one lookup for the selected current SKU
[x] Reused the proven related identity in downstream finance scoping
[x] Kept missing/ambiguous identity fail-closed
[x] Added regression coverage for 500 unrelated finance SKUs and zero FBO list calls
[x] Added bounded directional related-SKU discovery for asymmetric Ozon relations
[x] Added exact batched finance-posting SKU evidence to selected prefilter
[x] Persist fast selected-SKU identity failure diagnostics immediately
[x] Cover the traced production entrypoint against diagnostic NameError regressions
[x] Resolve rewritten posting SKU by bounded parallel exact-offer samples
[x] Guide the seller through historical-SKU identity confirmation in Telegram
[x] Revalidate a candidate against current posting evidence before persistence
[x] Retry the original selected-SKU period automatically after confirmation
[x] Let the seller revoke one exact incorrect historical/current SKU identity
[x] Preserve a local revocation audit snapshot and invalidate prior report guidance
[x] Expose revocation directly on the report created from a confirmed SKU mapping
[x] Expose exact revocation on every report that consumes a confirmed alias
[x] Batch report mapping lookup into one local SQLite read and zero Ozon calls
[x] Show selected-SKU monetary lines with their revenue share in parentheses
[x] Add discoverable date-only custom-period input to the Period Profit menu
[x] Isolate pending custom-period input per Telegram user
[x] Reuse canonical seller-cost coverage in `/start` and skip completed setup
[x] Resolve Period Profit tax policy from the active store on every request
# 2026-10-13 — P07/P08 завершены; P00–P08 реализованы в рабочей копии

- P07 добавляет read-only экран полноты расчёта поверх текущего Period Profit result и canonical Return COGS blocker chain. Повторное открытие работает по ограниченному snapshot-кэшу user/store и не вызывает Ozon повторно; detail view остаётся привязанным к тому же результату.
- P08 добавляет кнопку «На что обратить внимание» в главное меню. Сводка использует существующие Product Decision signals, сортирует до пяти приоритетов устойчиво по уровню и SKU, показывает факты/as-of и отдельно причины, по которым данных недостаточно.
- Устаревшие или неизвестные timestamps исключают сигнал из актуальных приоритетов. ДРР/ROAS не рассчитываются без подтверждённой рекламы и атрибутированной выручки; внешние расходы и Return COGS направляются в существующую «Полноту данных».
- Приоритеты отображаются по-русски; для длинного текста включается компактный Telegram-safe формат до 3 500 UTF-16 единиц. Стресс-тест включает длинные Unicode SKU и подтверждает сохранение предупреждений.
- Tenant/store isolation исправлена для SKU decision cache и prepared product metrics cache. Decision LRU ограничен 512 записями; экранные кэши имеют короткий TTL и ограниченный размер.
- P07/P08 target regression: **173 passed**; UI/cache subset: **80 passed**. `compileall app tests` прошёл. Полный isolated `pytest tests app/tests`: **3 077 passed in 12.06s**, exit code 0; копия исключала `.git`, `.venv`, `.env`, базы и пользовательские runtime-данные.
- Для P01 дополнительно проверена грамматика Python 3.11: Python 3.12 AST parser разобрал 874 Python-файла с `feature_version=(3,11)`, ошибок синтаксиса нет. Это не заменяет Linux runtime suite: Python 3.11, установленного WSL-дистрибутива и Docker в среде нет.
- Полный suite также закрыл ранее незавершённый критерий P03. Исходные `data/users.json` и `data/tasks.json` не копировались в тестовую копию; рабочие пользовательские данные сохранялись.
- Повторная Windows-регрессия P01: **171 passed** по task persistence, межпроцессным блокировкам, atomic user storage и shutdown contract. Linux runtime пока не подтверждён; на текущем host нет установленного WSL-дистрибутива, Docker или Python 3.11.
- Ветка `codex/p00-project-baseline`, HEAD `a06150a`; новых commits нет, поскольку `.git` доступен только для чтения. P01 остаётся с внешним критерием Architecture Review и Linux Python 3.11 Verify; локальная Windows-проверка не заменяет их.

# 2026-10-13 — P06 завершён; начат P07
# 2026-10-17 — база новых экранов обзора и пакетных расчётов

- Модуль C добавляет read-only пакетный план цены для 2–10 точных товаров одного магазина. План строит отдельные результаты по каждой строке, сохраняет source age/provenance, допускает только локальные допущения и подтверждённое обновление источников. Telegram entry находится в обзоре товаров после выбора строк.
- Готовый candidate можно открыть в одиночном калькуляторе через публичный tenant/version-bound handoff. Freshness, FBO scheme и точная identity проверяются заново; forward calculation повторяется без HTTP. Функциональность не пишет цену в Ozon.
- Пакетный экран принимает последующий текст только как read-only ввод до явного выхода; смена раздела очищает его callbacks, поэтому текст не уходит старому одиночному сценарию.
- Локальная регрессия модуля C: **116 passed**; `compileall -q services`, `git diff --check` прошли. Нужна полная CI проверка после push.

- A00–A04 большой программы Luna выполнены. Общий Ozon budget наследуется grouped calls; точный CI для основания зелёный. B00 добавил selected-row query без истории/предложений и повторных загрузок каталога; B01 строит snapshot projection и coverage.
- Совместный профиль A02/A03: 34 passed, 1 существующий `tmp_path` test исключён локально из-за Windows ACL. Полный exact-head CI на SHA `be76a4f8e4c7d78160e0d1047515651993062d54` прошёл: Windows/full-verification, полный pytest, compileall и Docker build/runtime smoke; Verify run `39059951770`. A04 закрыт.
- Реализацию B/C/E нужно подключить к `ScopedTransientSnapshotStore`; пока consumers не подключены, helper не меняет существующие пользовательские экраны.
- B00 добавил выбранную read-only выборку строк decision query и перестал повторно разрешать один SKU через каталог в каждом источнике. 53 профильных теста прошли; один существующий `tmp_path` тест исключён по ACL. B01 строит snapshot projection и coverage.
- B01 добавил `ProductOverviewService` с owner/store-scoped snapshot, whitelist решения/метрик, source provenance/freshness и страницами только из снимка. 69 связанных проверок прошли; следующий этап — фильтры и сортировка без Ozon-запросов.
- B02 добавил snapshot-only фильтры существующих decision signals, безопасную сортировку с unknown числовыми значениями в конце и передачу явного cache-stale metadata; 75 связанных тестов прошли.
- B03 подключил Telegram «Обзор товаров»: ограниченные группы сортируются по артикулу, явно помечаются как группа, а фильтры/сортировка/страницы читают снимок без нового источникового запроса. Карточка показывает модельные показатели и пропуски без обещания итоговой прибыли магазина. Добавление в пакет цен tenant-scoped и точное по SKU; активный одиночный сценарий заменяется только после явного подтверждения, привязанного к его версии. B04 проверил границы каталога 0/1/20/21, частичные источники, budget exhaustion, конкурентную публикацию поколений, старые/чужие callbacks, лимит 10 SKU, Telegram message/callback limits и wiring production factory. 93 целевых теста прошли; связанный товарный набор — 1 018 passed, 12 тестов с `tmp_path` локально исключены из-за ACL в Windows temp root; `compileall app` и diff-check прошли. B модуль локально VERIFIED, exact-head CI остаётся общей проверкой G01.

# 2026-10-17 — пакетный план цен, этапы C00–C02

- C00/C01 добавили пакетный план 2–10 точных SKU одного активного магазина. Один каталог загружается на пакет; source snapshots проверяют полную product/offer/SKU identity, индивидуальную свежесть и provenance, используя общий 120-секундный/128-attempt budget.
- `UnitPriceScenarioSource` принимает проверенную строку каталога для batch-пути, не загружая каталог повторно, и изолирует cache/in-flight ключи полной идентичностью. Cache hit сохраняет фактические age/TTL.
- C02 pure core поддерживает локальное редактирование допущений по строке, общую цель маржи, отдельный preview/confirmation для общей рекламы и explicit source refresh с сохранением provenance ручных значений, включая 0. Telegram batch runtime остаётся следующим шагом.
- Локальный профиль C00/C01/domain C02: 75 passed; `compileall -q app tests` и `git diff --check` прошли.

# 2026-10-17 — приёмка модуля C, этап C05

- Весь модуль C00–C05 принят. Локальный связанный профиль B/C: **193 passed**; `compileall -q app tests` и `git diff --check` прошли.
- Exact-head `07b9d595df32b11b736aaa2dc13c822df7f52ec4` прошёл Verify runs `39063730904` и `39063717597`: Windows/full-verification, полный pytest, compileall и production Docker build/runtime smoke успешны.
- PR #699 открыт stacked над PR #698, готов к независимому review; merge/deploy не выполнялись. Следующий модуль — D, чувствительность и матрица цен.

# 2026-10-17 — модуль D, чувствительность плановой экономики

- `UnitPriceSensitivityService` выполняет 1D sweep или 2D матрицу максимум 7×7 через существующий forward calculator. Принимаются только абсолютные числовые значения с границами, разделителем и запретом нечисловых/переполненных значений. Подпись охватывает точную identity/version, inputs, provenance и sources; расчёт не мутирует snapshot.
- Telegram runtime принимает чувствительность из одиночного калькулятора и готовой строки пакетного плана; текстовый вывод ограничен страницей, и все ячейки доступны без потерь. Stale result остаётся доступным для просмотра с as-of, но перенос отключён. Применение требует точного совпадения исходной версии, owner/store и повторного forward расчёта; сетевых запросов и записи в Ozon нет.
- Локальный профиль D00–D03: **117 passed**; `compileall -q app tests` и `git diff --check` прошли. Полный локальный pytest: **2 978 passed, 21 failed, 369 errors** из-за ACL Windows temp (`WinError 5`; SQLite не может открыть файл в созданном временном каталоге). Exact-head `d7c33dfa9d4d1e3ffde626d375dd17d2f0d38824` прошёл Windows и full-verification в Verify runs `39065039552` и `39065028764`. Данные `data/tasks.json` и `data/users.json` сохранили исходные SHA256. PR #700 открыт, stacked над #699; merge/deploy не выполнялись.

# 2026-10-17 — модуль E00, безопасная отправка файлов

- В `telegram_document_contract.py` введены allowlist document-kind, MIME/расширения, безопасное имя без пути и статическая подпись. Текущий cost CSV явно объявлен `seller_cost_import_template`; будущие аналитические файлы используют тип, который запрещает загрузку в поток себестоимости.
- `_send_result` отправляет файл до сообщения об успехе; ошибка контракта/Telegram даёт явную ошибку и не запускает повторную отправку. Существующий шаблон себестоимости и его подпись сохранены.
- Профиль E00: **12 passed**; compileall и diff-check прошли. Следующий этап E01 — versioned CSV/JSON сериализаторы.

# 2026-10-17 — модуль E01, сериализаторы

- `AnalyticsExportSerializer` формирует schema v1 CSV/JSON из переданных rows и metadata. Поддерживаются денежные/десятичные/целые/текстовые/status/boolean типы; неизвестное сохраняется как `null` в JSON и пустая ячейка в CSV, ноль остаётся нулём.
- CSV: UTF-8 BOM, `;`, русская десятичная запятая для чисел, формульно безопасные типизированные текстовые ячейки и встроенная metadata/schema. JSON: UTF-8, денежные/десятичные значения строками с точкой, единицы и семантика колонок.
- Лимит 2 MiB, max rows/columns и default-deny для неизвестных полей; при превышении возвращается явная ошибка, данные не обрезаются. Имена файлов статические.
- Профиль E01: **17 passed**; compileall и diff-check прошли. Следующий этап — подключить экспорт точных снимков периода.

# 2026-10-17 — модуль E02–E04, выгрузки точных снимков

- `AnalyticsExportService` переводит сохранённые analytics snapshot в отдельные схемы: finalized прибыль за период (сравнение, B/E bridge, reconciliation, top-SKU только с TOP_K/coverage маркерами), обзор товаров, пакетный план и чувствительность.
- Периодный отчёт экспортируется только из owner/store-bound report cache с прежним TTL. Обзор читает все строки сохранённого scope после текущих filter/sort; пакет и чувствительность экспортируют весь точный snapshot вместо открытой страницы. Callback для плановых выгрузок bound к версии и session.
- Плановые CSV/JSON маркируются как `PLANNED`, одна успешная продажа, оценка FBO, цель, provenance и ограничения. Фактический период помечается как finalized basis. Суммы-разложения несут семантическую пометку, чтобы их не складывали повторно.
- Public callback → document transport и regressions проверяют payload, полный набор строк, stale/foreign/expired scope, отсутствие повторного чтения источников и прежний seller-cost export.
- E00–E04 профиль: **73 passed**; `compileall -q app tests` и `git diff --check` прошли. Первый CI нашёл устаревшую assertion состава клавиатуры; после исправления на итоговом SHA `47cfa2527b2f963d2604511c76d1a41b6e6201f0` Windows и Linux прошли по **3 389 тестов**, Docker build/runtime smoke успешны (Verify `39066587245`). PR #701 открыт, не слит/не развёрнут.
- E documentation acceptance SHA `f598d300164916434de27a5180bb033d8a9f4293` also passed exact-head Verify `39066774774`.
- F00 добавил ограниченную 256-событийную трассу с общими счётчиками попыток/проверок и экран «Почему расчёт неполный?» по точному owner/store-bound report snapshot. Экран использует кэш, не повторяет запросы и показывает только разрешённые статусы/причины и действия. Локальный профиль: **27 passed, 1 deselected** (существующий `tmp_path` stack-dump тест исключён из-за Windows ACL при запуске с отключённым tmpdir); compileall и diff-check прошли. F01 — безопасный JSON-экспорт.

# 2026-10-19 — H/I: локальный lifecycle и сохранённые планы

- H01–H03 реализованы: один polling-процесс на token fingerprint, локальные status/stop команды и graceful shutdown. RUNNING требует подтверждённого PTB polling и обработки updates. Focused lifecycle profile: **40 passed**; compileall и PowerShell AST validation прошли. Реальный бот не запускался.
- I00–I04 реализованы: `PlanningWorkspaceRepository` добавляет tenant-scoped таблицы в текущую SQLite DB; сервисы и публичный Telegram handler обеспечивают сохранение single/batch планов, исторический просмотр после пересоздания сервисов, продолжение в transient editor, копирование/переименование/архив, восстановление и подтверждённое удаление.
- Сохранённый snapshot имеет строгую allowlist; CAS и idempotency защищают версии. После явного refresh можно добавить новую ревизию исходного плана или создать копию. Ручные допущения сохраняются только на той же identity. Ошибки БД, некорректных часов, повреждённой записи и future schema fail closed.
- H/I focused profile: **98 passed** на Windows/Python 3.12; точная команда указана в `LUNA_PLANNING_WORKSPACE_PROGRESS_2026-10-19.md`. Полный pytest и exact-head CI ещё не выполнены; H04/I05 остаются незавершёнными до чистых cross-platform checks.
- `.env`, Ozon/Telegram API и пользовательский бот не запускались. В полном локальном pytest прогоне тесты затронули root `data/tasks.json`/`data/users.json`; после прогона они оставлены на месте, не staged/committed. Исходные H00 SHA256 и текущие SHA256 зафиксированы в `LUNA_PLANNING_WORKSPACE_PROGRESS_2026-10-19.md`; исходные точные копии в доступных scratch directories не найдены. Не выполнять автоматический restore и повторный локальный полный suite.

# 2026-10-19 — исправления архитектурного review planning workspace R1–R10

- Закрыты локально все десять подтверждённых замечаний к стеку PR #705–#708: точный перенос sales mix при CAS обновлении; отдельная `state_revision` для metadata/payload mutations; сохранение batch/editor context; корректные расходные дельты и readiness; атомарная schema migration; generation ticket до plan/fact запроса; единые денежные/объёмные лимиты; видимый полный состав SKU в сравнении и выгрузках.
- Добавлены регрессии в `tests/test_planning_workspace_repository.py`, `tests/test_saved_planning_plan_telegram_flow.py`, `tests/test_sales_mix_planning_service.py` и `tests/test_planning_plan_comparison_service.py`. Связанный локальный H–O профиль: **259 passed**; `compileall -q app tests` и `git diff --check` прошли.
- Полный локальный pytest не повторялся из-за ранее выявленных ACL/shared-storage проблем. SHA256 сохранённых локальных данных после целевых проверок: tasks `8F7FFF206A4748DE6EFB3E5DCABABD07E3341188A7326383A21D966B73710698`, users `0B12986702D5C62B8A410EE4B3B3228923FF72BA897F18FF62FEF556CDA88409`; data и scratch paths не включаются в изменения.
- Exact-head `d057031364e6d934f258fec2efa385a045f6e3bf` прошёл Verify `39221770481` и повторный Verify `39221764654`: Windows/Linux, compile, production Docker build и smoke успешны. После этой записи добавляется только документационный commit, поэтому latest exact-head Verify нужно подтвердить отдельно. Далее нужен независимый повторный architecture review. Слияние и развёртывание не выполнялись.
# 2026-10-21 — X03 bounded cross-docking collection and wiring

- X03 adds read-only 56-day finance and supply collection with process-local scoped checkpoint/resume, a bounded in-memory cache, in-flight deduplication, shared 64-attempt/60-second limits, reuse of the current request's 28-day finance cache, and lazy current/scenario factory wiring.
- Complete rates are still evidence-only; X is not yet subtracted in unit-economics calculations and is not frozen into saved plans. Those are X04–X05.
# 2026-10-25 — ежедневная готовность, этап C05

- C05 закрыт локально: external-expense action сохраняет точные даты, возвращает к scoped report и принимает только валидный сохранённый контекст; stale owner/store callbacks отклоняются.
- Связанный сценарий `report → details → completeness → expenses → confirm → return → explicit refresh → CSV` прошёл. Профиль: **81 passed, 3 temp-backed tests deselected** из-за локального Windows ACL; exact-head CI обязателен.
- Acceptance и limitations: `DAILY_USE_END_TO_END_ACCEPTANCE_C05_2026-10-25.md`; далее A04 final/A05, затем D00.

# 2026-10-25 — ежедневная готовность, этап D00

- Инвентаризация кода выявила credential DB в configured storage root, tenant DB/JSON в hashed dirs, а также оставшиеся legacy project-relative DB и JSON; проверка настоящих данных не выполнялась.
- Зафиксирован backup/restore manifest v1 и согласованная архитектурная граница: только local data, backup после подтверждённой остановки, новые пустые destination для restore, ключ шифрования хранится отдельно.
- D00 acceptance: `DAILY_USE_STORAGE_INVENTORY_D00_2026-10-25.md`; дальше D01. Решение 056.

# 2026-10-25 — ежедневная готовность, этап D01

- Добавлена проверяемая offline-команда локальной резервной копии с SQLite backup API, JSON контрактной проверкой, SHA-256 manifest, завершённым marker и атомарной публикацией; работает только при подтверждённо остановленном боте.
- Синтетическая регрессия D01: **7 passed**; реальный storage, `.env`, ключи и процесс бота не читались. См. `DAILY_USE_BACKUP_ACCEPTANCE_D01_2026-10-25.md`.
# 2026-10-25 — ежедневная готовность, этап D02

- Реализовано dry-run и staged restore D01 архивов только в новую отсутствующую папку; проверяются manifest/checksums, размер, типы/пути и исходная tenant isolation. Restore не меняет `.env`, текущий storage и работающий процесс.
- Синтетический restore прошёл через существующий `ExpenseRepository` для двух tenant scopes; **13 backup/restore tests passed**. Эксплуатационный запуск не проводился; см. `DAILY_USE_RESTORE_ACCEPTANCE_D02_2026-10-25.md`.
# 2026-10-25 — ежедневная готовность, этап D03

- Добавлен локальный `update_bot.ps1 -CheckOnly`: он показывает текущую ревизию, кэшированный target SHA, безопасные data conflicts, зависимости, lifecycle и необходимость backup. Fetch/update/stop/start не выполняет.
- Synthetic Git preflight: **9 passed**; Git ref, worktree и fake process state не изменились. Exact-head CI предстоит; см. `DAILY_USE_UPDATE_PREFLIGHT_ACCEPTANCE_D03_2026-10-25.md`.
# 2026-10-27 — unit-price observation Q17

- Q17 bounded read-only collection завершён: точное FBO/SKU окно использует существующие ограниченные Ozon finance/Performance adapters; денежные и ценовые основания не выдаются за подтверждённую прибыль. Изолированный профиль: 172 passed; полный pytest/CI ещё впереди (Q33–Q35). Acceptance: `UNIT_PRICE_OBSERVATION_COLLECTION_Q17_2026-10-27.md`.

# 2026-10-27 — unit-price observation Q18

- Q18 добавил pure normalizer для денег, окон/дат, DRR bases, взвешенных знаменателей и conflict-safe dedup. Без полной скидочной базы, price history, successful-sale units и дедуп-подтверждения результат остаётся incomparable; финансы и CPC не вычитаются повторно. Связанный профиль: 184 passed. Acceptance: `UNIT_PRICE_OBSERVATION_NORMALIZATION_Q18_2026-10-27.md`.
# 2026-10-31 — Реализация маржи до рекламы: MA05

- Плановый canonical scenario теперь возвращает отдельный versioned `pre_ad_margin` до рекламы; no-ad сценарий вызывает существующий `TaxService` отдельно. При неизвестной рекламе before-ad может быть доступен, legacy after-ad `profit`/`margin_percent` остаются без изменений.
- Проекция подписывает неполный expense scope и не считает неизвестные расходы нулём. Существующий cross-docking denominator guard и цель after-ad оптимизации сохранены.
- Новый `advertising_tax_bridge` v1 разделяет T0/T1, рекламный расход и налоговый эффект; формула `after = before − ad + (T0−T1)` сверяется. TaxService unchanged, SalesMix по-прежнему считает налог один раз на группу.
- Linked scenario/current-card/Telegram profile: **315 passed in 4.97s**. Полный suite/current-head CI pending; live Ozon/Telegram и запуск бота не выполнялись.
# 2026-11-06 — FIFO FC22 correction impact and commit

- FC22 `DONE_WITH_GAP`: a read-only before/after service now reports FIFO units/COGS by basis and recalculates period tax/profit through the existing `TaxService`. Owner confirmation is bound to exact store/SKU/draft and source, stream, allocation, tax and impact fingerprints.
- FIFO schema v9→v10 appends a correction audit snapshot atomically with the new rate. The former allocation projection is invalidated; Period Profit is not changed until complete replay. The synthetic path supports only one missing rate and no linked returns/non-sale outflows; production remains blocked by unreconciled historical stock/finance cutoff.
- Linked FC22 profile: **65 passed in 3.25s**. All data used were synthetic or in pytest temporary SQLite; no live Ozon/Telegram requests or bot startup.
# 2026-11-08 — FIFO late-entry completion FL13

- FL13 добавил read-only parser отчёта «Управление остатками» для точного SKU с отдельными buckets, FBS-return subset, сверкой листа «Товар-склад» и отдельным `removed_from_sale`. Представления «Товары», warehouse detail и cluster views не складываются; `reserved` и отсутствующий removed bucket остаются unknown, общий total — только диагностика.
- Синтетическая матрица подтверждает `available=1191` (`1182 + 9 FBS return`), `preparing=18`, `checking=5`, `removed_from_sale=41`; warehouse totals совпадают независимо. Неверный числовой product-feature отклоняется.
- Кодовый commit FL13: `52a5b9fb3b3cf605b8c500003d48d254f1453337`. Оба parser modules — **35 passed**; связанный FIFO/Telegram FIFO профиль — **423 passed in 17.90s**; compileall, `git diff --check`, `git diff --exit-code -- data` PASS. Использовались synthetic in-memory XLSX; пользовательский файл не использовался тестами, `data/` не менялась.
- Parser остаётся read-only: XLSX ещё не сохраняется в evidence и не подключён к Telegram; FIFO, фактическая прибыль, БД и режим расчёта не менялись. `IMPLEMENTATION_VERIFIED: нет`, `OWNER_CASE_VERIFIED: нет`.
- Следующий этап FL14 — контекстный XLSX import в выбранный case с bounded worker, preview и отдельным подтверждением.

# 2026-11-08 — FIFO late-entry completion FL12

- FL00–FL12 VERIFIED в коде исполнения, но не в production и не на owner case. Добавлен `FifoCostReportImportService.parse_turnover_workbook`: строго читает лист «Оборотная ведомость» и выдаёт нормализованные read-only evidence только для выбранного SKU.
- Parser различает `redeemed_units=775` и `non_sale_expense_units=5`, сверяет opening 4492 + receipts 0 − expenses 780 − closing 3712 = 0 и сохраняет buckets доставки покупателю/возврата отдельно. 3712 остаётся отчётным closing total и не подменяет доступный/физический stock.
- FL12 commit `1f209a23`; focused synthetic profile **21 passed**, полный FIFO/Telegram FIFO профиль **409 passed in 17.21s**. `compileall`, `git diff --check`, `git diff --exit-code -- data` PASS. Владелец XLSX не использовался тестами, API/UI/persistence ещё не подключены.
- FL13 добавил 1 security regression к общему XLSX preflight: скрытые sheets отклоняются до parsing. Текущая повторная проверка: FL12 parser **22 passed**, FL13 parser **13 passed**, связанный профиль **423 passed**. Следующий этап FL14 описан выше.
# 2026-11-08 — FIFO FL25: возобновляемый мастер поздней партии

- В карточке уже можно начать или открыть сохранённое FIFO-дело. Новый runtime мастер последовательно подтверждает прежнюю себестоимость, новую стоимость TOTAL_LANDED/COMPONENTS, дату первой отправки, старые остатки дома/в пути и известный общий объём новой партии. Каждый подтверждённый блок сохраняется как новая CAS revision; новое количество, оставшееся дома, не спрашивается и остаётся неизвестным.
- Можно добавить типизированные номера заявки/поставки с количеством или пропустить этот этап, а также начать контекстный выбор оборотной ведомости/отчёта остатков. Callback короткий и opaque; переход между магазинами прекращает ввод. После перезапуска пользователь возобновляет case из durable списка. Сохранение мастера не меняет FIFO, стоимость отчётов или фактическую прибыль.
- FL25 code SHA `6be4485eca93bfd94e903bc3576913a2e0d86b2a`; linked FIFO/Telegram/Period Profit profile **537 passed**; `compileall`, `git diff --check`, `git diff --exit-code -- data` PASS. Все тестовые данные синтетические. Реальный case владельца не применён и не подтверждён.

# 2026-11-08 — FIFO FL24: переход к поздней партии до настройки очереди

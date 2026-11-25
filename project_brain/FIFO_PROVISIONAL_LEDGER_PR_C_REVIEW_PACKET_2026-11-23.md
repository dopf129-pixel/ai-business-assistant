# PR C independent review packet — saved provisional FIFO estimates

## PR dependency and revision

- PR: **#743**, branch `codex/fifo-provisional-saved-estimates`.
- Target: PR B #742, branch `codex/fifo-provisional-timeline`, updated dependency head `fd287b736a00b958a78ddea45b71f6e10294df1b`. PR B includes updated PR A #741 head `30e6d735a666d97fd670fae0b1b011a4f9c5950b`; PR A is based on specification PR #740 at `49dbbd77ffa10ac0493b1bb4e83acf123b3005cf`.
- Local implementation/test SHA: `61480ae48e75e3ffedce87c62d23bb0363b3ad5b`. Documentation and this review packet are packaged in a descendant commit; the published PR head is authoritative for final review and CI.
- PR A and PR B are open, unmerged, and their exact-head CI is green: A run [45142413339](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/45142413339), B run [45172484489](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/45172484489). PR C package head `5ec77fa3e7c94535e288d5a6c04134688d6ce07c` passed hosted Windows/full-verification run [45193059919](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/45193059919); duplicate exact-head run [45192990093](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/45192990093) also passed. Check the latest PR head after any follow-up documentation commit.
- Change class: **Architecture Review Required — minor architectural extension**. Adds FIFO-owned append-only estimate persistence and hooks into the existing FIFO Telegram transition experience. It does not replace the factual FIFO/event pipeline.

## Scope

PR C implements PF20–PF26 on top of the provisional aggregate model in PR A and gated timeline model in PR B:

- FIFO schema v20 stores immutable, separately scoped provisional previews; migration is additive and leaves Planning metadata/version untouched.
- The ordinary FIFO screen can save a fresh model, reopen saved estimates after a new session, browse a bounded history, and compare only compatible model/profit perimeters.
- The owner may explicitly enter and confirm a financial base for a **conditional pre-tax profit range**. The value is not inferred from store-wide profit or another period.
- Save callbacks re-read/recalculate the current source, bind to exact user/store/SKU/case revision and model evidence, and append only to the estimate repository. Stale callbacks, unsupported payloads, quota excess, and conflicting idempotency retries fail closed.
- Synthetic Telegram tests cover the estimate → owner base → explicit confirmation → save → reopen journey and verify zero writes to factual FIFO/COGS/Period Profit.

## Review focus

1. **Data boundary:** review all save/history routes and repository writes. Only `fifo_cost_provisional_previews` may be appended. Verify no factual transition, layer, allocation, cost-history, Return COGS, finance, or Period Profit writer is reachable.
2. **Freshness and tenancy:** verify owner/tenant/store/product/offer/SKU/case revision, selected model, period, redeemed units, evidence fingerprint and profit perimeter are checked on every write/read/comparison. Inspect stale and cross-identity tests.
3. **Append-only and retries:** identical idempotency retries must return the same estimate; a different payload under the same key must conflict; history cannot be edited or promoted; limits remain 100 records per case and 64 KiB per payload.
4. **Migration and backup:** v19→v20 is additive. Existing FIFO transition data, Planning version, SQLite `user_version`, and estimate records survive backup/dry-run/full restore. Fresh v20 schema and legacy v1 saved payload compatibility are covered.
5. **Conditional profit:** formula is `owner_confirmed_base − gross_COGS`; interval endpoints reverse correctly; negative base is allowed. No tax calculation or financial return-reversal adjustment is implied. The base is an owner assertion and is not independently matched to an external finance report.
6. **Comparison:** interval subtraction is allowed only when perimeter, currency, period, redeemed-unit count, tax stage and return-reversal rule match. Differing source coverage is disclosed; incompatible dimensions suppress a combined delta.
7. **Telegram safety:** inspect callback freshness, message size, privacy masking and navigation after session restart. Confirm raw files, free text, IDs, fingerprints and secrets are not included in the saved user-facing history.

## Acceptance matrix C01–C09

| ID | Evidence in PR C | Review note |
| --- | --- | --- |
| C01 | `test_regular_transition_flow_saves_only_fresh_provisional_preview`, `test_saved_preview_rejects_stale_case_revision_and_cross_identity`, idempotency repository tests | Verifies fresh save, stale revision rejection, and idempotent append/conflicting replay. |
| C02 | `test_pf20_v19_upgrade_adds_append_only_preview_table_without_touching_planning`, `test_backup_archive_restore_preserves_fifo_provisional_preview_and_planning_versions` | Additive migration, backup, dry-run/full restore, Planning and SQLite versions. |
| C03 | `test_saved_estimate_history_is_ordered_paginated_and_scope_bound`, `test_regular_transition_flow_saves_only_fresh_provisional_preview` | Saved estimates are reopened from scoped history in a new session; they remain historical scenarios. |
| C04 | `test_saved_preview_validates_manual_conditional_profit_formula`, Telegram profit confirmation journey | Confirms the agreed 130,000 ₽ input and conditional interval 19,596.80–19,812.70 ₽ for the §4.3 case. |
| C05 | `test_saved_preview_rejects_stale_case_revision_and_cross_identity`, `test_saved_preview_requires_complete_model_contract_and_iso_dates`, UI no-base/provenance guard regressions | Missing or incompatible base/scope is withheld with an explanation; user-entered base is explicitly not cross-validated against a finance document. |
| C06 | `test_conditional_profit_allows_negative_owner_confirmed_base`, `test_conditional_profit_comparison_withholds_different_financial_perimeter` | Negative numeric result remains valid; differing financial perimeter suppresses comparison. |
| C07 | Repository validation, atomic/idempotent append and quota tests, migration/backup regressions | Covers 64 KiB and 100-record limits, schema compatibility and failed-write preservation; review transaction boundaries. |
| C08 | `test_regular_transition_flow_saves_only_fresh_provisional_preview` | Synthetic ordinary Telegram screens are bounded below Telegram message size and stale callbacks are rejected. |
| C09 | `test_owner_movements_csv_and_timeline_gap_are_presented_without_promoting_summary`, PF13 FBO/turnover delta test, `test_regular_transition_flow_saves_only_fresh_provisional_preview` | Synthetic incomplete-history and +1 comparison behavior is covered, and no factual-apply action is exposed. Real owner reports and live source behavior were intentionally not used. |

## Verification

- PF23/PF24 linked profile: **76 passed in 5.02s**; compile and tracked-data checks passed.
- Focused schema/checkpoint regression after PF26 corrections: **29 passed in 2.48s**.
- Full isolated Windows/Python 3.12 suite at code/test SHA `61480ae48e75e3ffedce87c62d23bb0363b3ad5b`: **5,579 passed in 97.95s**, exit 0. Disposable checkout excluded `.env` and owner `data/`; only a synthetic tax policy was used. `compileall -q app tests`, test database initialization, `git diff --check`, and tracked `data/` equality passed.
- An earlier full run exposed 14 stale schema-v19 test expectations and four environment-fixture mismatches. These were corrected in tests/fixture setup, then the full suite passed at the exact implementation SHA above; the earlier failed result is retained in the progress journal.
- Hosted PR C CI must be checked on the final published head SHA. Do not treat local tests or PR A/B checks as PR C hosted CI.

## Preserved components and known limitations

- Factual FIFO posting/event/layer/allocation history and apply path, cost history, Return COGS, financial summaries and canonical Period Profit are intentionally unchanged.
- Legacy operational cost-import and cross-docking flows remain separate. Planning schema/version remains unchanged.
- All test data is synthetic. No owner XLSX/CSV, credentials, production API calls, Telegram sends, bot launch, merge or deployment were used.
- The actual owner case is not validated. Incomplete movement/return evidence remains a timeline gap; the aggregate summary may only be presented as a separately labeled provisional range.
- The owner-confirmed financial base is not independently checked against Ozon’s finance report. No tax recalculation or financial reversal for returns is implemented. Never interpret a saved preview or conditional profit as a factual accounting result.

## Final release gate

Before considering this PR ready for independent review, confirm PR C is open against PR B, then inspect **all required CI checks on PR C’s exact current head SHA**. PRs #741 and #742 must remain the dependencies in the stated order. No PR is merged or deployed by this task.

## Follow-up review fix — 2026-11-24

- History-only actions now use one preservation path for timeline evidence fingerprints, the owner-confirmed conditional-profit basis, and saved-preview markers. This covers list, pagination, detail, comparison, cancel/back, and returning to the calculator. Non-history changes still invalidate dependent values.
- Regression traverses that full path and keeps the conditional profit visible, then removes a selected report and proves a callback cannot append an estimate from stale evidence. C-focused provisional/transition/repository profile: **72 passed**; full merged A+B+C linked profile: **152 passed**. `compileall`, `git diff --check`, and unchanged tracked `data/` passed. Exact-head hosted CI must be confirmed after publishing the updated branch.


## Follow-up review findings — 2026-11-25

- P2 — Saved estimate history was only reachable while the case was editable and a transient calculator flow existed. Fixed by adding a read-only history entry to READY_TO_CONFIRM, APPLIED and CANCELLED cards/previews; initializing a minimal case-scoped history session when no calculator flow exists; and returning from read-only history to the case card. The regression covers all three states, detail, back navigation, and a stale session revision refresh. No estimates or case data are written by this route.
- PR B follow-up fixes are integrated as a parent in the C branch: timeline and aggregate old-sold contradiction, wider containing FBO coverage, optional article scope, and aligned 32 MiB FBO output cap.
- PR B exact-head hosted Verify: https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/45571794948 passed. PR C exact-head hosted Verify is pending on the new integrated commit; retain this PR as not ready to merge until that run is green.


## Final review verification — 2026-11-25 (supersedes earlier pending notes)

- PR B dependency head 1248617c70d95de92b37129157abae138153160e passed Verify run [45571794948](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/45571794948), including Windows, Linux, Docker build and runtime smoke.
- PR C implementation/test head 989f0520ae4d803e1ce628c72048742082df0603 passed Verify run [45575002866](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/45575002866): Windows **5,588 passed in 281.55s**, Linux **5,588 passed in 62.66s**, Docker build and runtime smoke succeeded. An initial Windows attempt failed only because a random callback token coincidentally contained the test's checked digit string; the same-SHA retry passed.
- This packet update is documentation-only and creates a new SHA. Require the fresh exact-head run to pass before merge. No merge, deployment, live API request, or bot start occurred.


## Additional review corrections — 2026-11-25

- PR C now exposes saved provisional estimate history from the regular FIFO SKU card and the APPLIED/CANCELLED transition list. The production route is exercised through `TelegramFifoCostHistoryService`, `SellerCostTelegramAdapter`, and `TelegramFifoCostTransitionRuntimeService` with no transient calculator session.
- Case callbacks carry and revalidate the listed case revision; stale cards are rejected. The route only reads the case and estimate ledger; the regression asserts zero transition writes.
- PR B's actual old-layer closing check, layer-origin classification, and typed-input invalidation are included as dependencies and covered by C's focused regression profile.
- Exact-head hosted CI for the C integration commit is required before merge; PR remains open.


## CI correction note — 2026-11-25

- Exact-head run 45589577824 на `f80757a57663beafc1d23a082aa0354b6539b20a` остановился на collection из-за синтаксиса генератора в новой интеграционной регрессии. Исправление добавляет явные скобки; повторный прогон нужен на следующем SHA.

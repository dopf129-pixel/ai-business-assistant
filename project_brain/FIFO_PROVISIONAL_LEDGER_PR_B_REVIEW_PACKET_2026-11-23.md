# PR B independent review packet — provisional FIFO timeline

## Scope and dependency

- PR: provisional FIFO event timeline (PF11–PF19), branch `codex/fifo-provisional-timeline`.
- Target base: PR A #741 branch `codex/fifo-provisional-summary`, updated head `30e6d735a666d97fd670fae0b1b011a4f9c5950b`; PR A itself is based on specification PR #740 at `49dbbd77ffa10ac0493b1bb4e83acf123b3005cf`.
- Local code/documentation verification SHA: `520eed936328793bd62fda3df621ad06b965cea4`. PR packaging adds this packet and the PF19 verification checkpoint; use the published final PR head for final review and CI.
- Change class: **Architecture Review Required**. Adds the independent timeline gate, event replay integration, owner CSV worker route, and normal Telegram presenter. It does not replace factual FIFO or finance services.

## Review focus

1. `FifoCostProvisionalTimelineService` publishes `TIMELINE_MODEL` only after explicit owner coverage confirmation, exact FBO coverage for the chosen report interval, complete normalized replay, exact opening transit links, event-to-report total matching, and reconciliation of all eight ending stock buckets.
2. A replay gap returns only safe event progress counts. The Telegram presenter suppresses partial timeline COGS and sold-unit amounts. A `SUMMARY_RANGE`, when available, remains visibly separate and is not presented as a continuation of the event prefix.
3. The owner movements CSV uses the allowlisted bounded worker/parser. Its parent revalidates the returned manifest. Session state is bound to user/store/SKU/case revision, expires, and is not persisted. Identifiers/free-text references are hashed or suppressed before presentation.
4. Replacing/reconfirming either FBO or movements CSV clears prior source-coverage confirmation and timeline output.
5. No request path invokes factual FIFO readiness/prepare/apply, cost history mutation, Return COGS, Period Profit write, or a persistent estimate-ledger write.

## Key changed files

- `app/services/fifo_cost_provisional_timeline_service.py`: final read-only source/replay/reconciliation gate and result projection.
- `app/services/telegram_fifo_cost_provisional_service.py`: optional owner movement upload, coverage confirmation, calculation and safe presenters on the standard FIFO Telegram screen.
- `app/services/fifo_cost_report_import_worker.py` and `..._client.py`: allowlisted, resource-bounded subprocess parsing and parent-side result validation.
- `app/services/fifo_cost_provisional_movements_import_service.py`: minimal hashed worker summary for movement events and stable event sorting.
- `app/services/telegram_fifo_cost_transition_runtime_service.py` and `app/telegram_app_layer/seller_cost_telegram_adapter.py`: routing the provisional upload without changing the existing factual import routes.
- `tests/test_fifo_cost_provisional_timeline_service.py`, `tests/test_fifo_cost_provisional_fbo_telegram_flow.py`, `tests/test_fifo_cost_report_import_worker_client.py`: synthetic model, ordinary Telegram, reset-on-replacement, worker-boundary and privacy regressions.
- Owner guide and project state/decision/test map record behavior and limitations.

## Verification

- PF18 linked profile: **97 passed in 12.81s** across final gate, replay, normalizer, movement/FBO parsers, evidence reader, ordinary Telegram flow, worker client, and existing transition evidence/workflow.
- Full isolated Windows/Python 3.12 suite on `520eed936328793bd62fda3df621ad06b965cea4`: **5,565 passed in 95.75s**. The disposable copy was built from tracked Git files without `.env` or repository `data/`; one synthetic tax configuration file was added only in that copy.
- `compileall -q app tests`, `git diff --check`, tracked data equality and PF00 blob hashes: passed.
- PR A exact-head predecessor verification: run [45142413339](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/45142413339), Windows verification, Linux full verification, Docker build and runtime smoke all succeeded.
- PR B hosted CI: pending publication of the final PR B head; do not treat local tests as hosted CI.

## Preservation and limitations

- All five tracked PF00 `data/` blobs are unchanged. Tests are synthetic; no owner XLSX/CSV or production account data was used.
- No factual FIFO/COGS/finance/Period Profit mutation, real Telegram/Ozon request, production bot launch, merge, or deployment was performed.
- The owner’s current incomplete historical event set must remain `TIMELINE_GAP`; an owner completeness confirmation cannot manufacture missing timestamps, receipts, return links or source evidence. Real-world model readiness still requires complete source history and exact report reconciliation.
- Saved estimate history, persistence/migration/backup, comparison and conditional profit belong to dependent PR C and are not implemented by PR B.

## Follow-up review fixes — 2026-11-24

- `SUPPLY_RECEIVED` can no longer inject quantity into `buyer_delivery`, through either the CSV parser or direct typed event construction.
- The timeline now uses the selected movement report's inclusive `period_to` as its model cutoff. Later owner events and physical-sale rows cannot enter the replay; post-cutoff delivery leaves an in-window FBO dispatch reserved. Opening delivery units lacking an exact posting key are kept as an untouched closing reserve, never as available stock or buyout supply, and still must reconcile with all closing buckets.
- The shared worker accepts up to 32 MiB for the already bounded 50,000-row owner-movement result; parser and parent validate the same limit.
- Updated linked profile: **111 passed** across timeline, normalizer, replay, movement/FBO import, evidence reader, Telegram and worker. Compileall, diff check and unchanged tracked data passed. Hosted CI must be checked on the published current head.
- With PR A's updated report-selection changes integrated, the combined A+B linked profile passed **140 tests**. `compileall`, `git diff --check`, and unchanged tracked `data/` passed on that integrated working tree. Exact-head hosted CI remains pending publication.


## Follow-up review fixes — 2026-11-25

- The old/new timeline sales split must fit the owner-confirmed aggregate old-sold range. A conflict withholds every timeline money result.
- A wider owner-confirmed FBO CSV period is accepted only when it contains the full selected movement statement. Event replay is still cut off at the statement window.
- An optional seller-article/offer_id CSV column is checked against the active case offer ID for selected-SKU rows; a mismatch fails closed.
- The worker and parent both allow 32 MiB for the maximum 50,000-row FBO result; a regression asserts the valid manifest exceeds the previous 16 MiB cap.
- Four focused regressions cover these rules; exact-head test and CI results are pending.


## Review corrections — 2026-11-25 (follow-up)

- Old/new sold units now follow layer provenance IDs; identical unit costs do not collapse party identity.
- The timeline compares actual old-layer closing units, including held stock and open dispatch reserves, with the same owner-confirmed closing range used by the summary model. A mismatch blocks result money.
- Valid typed exact/range input invalidates prior timeline output, and invalid text preserves the prior assumptions/results.
- Regressions cover a returned old unit where the summary sold range alone still passes, equal-price layers, and text-input invalidation. Exact-head hosted CI is authoritative for this PR update.

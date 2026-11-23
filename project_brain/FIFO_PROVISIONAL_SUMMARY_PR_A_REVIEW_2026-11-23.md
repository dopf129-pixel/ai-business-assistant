# PR A — Provisional FIFO summary: independent review packet

## Revision and scope

- PR branch: `codex/fifo-provisional-summary`.
- Target/base: PR #740 branch `codex/fifo-provisional-ledger-spec-20261122`, published specification SHA `49dbbd77ffa10ac0493b1bb4e83acf123b3005cf`.
- Implementation commit with full local verification: `63f60c2a3fe3b00268be1be8a124d7e90cb7f893` (`Cover provisional FIFO evidence edge cases`, following implementation commit `f967f7aa`). The final PR head is authoritative if this packet is carried by a later documentation-only commit.
- Scope: typed provisional contracts, exact-case read-only report selection, aggregate summary formula and ordinary FIFO Telegram transition callback screen. Timeline replay (PR B) and saved scenarios/conditional profit (PR C) are intentionally outside this PR.

## Architecture impact

**Architecture review required — minor architectural extension.** Adds `FifoCostProvisionalSummaryService`, `FifoCostProvisionalEvidenceReader`, `TelegramFifoCostProvisionalService`, workflow composition and a callback branch in the existing transition runtime. Decision 068 records the separation from factual FIFO.

The reader only rehydrates confirmed evidence for the exact case scope. The pure calculation service has no storage or network dependency. The Telegram draft is held in the existing expiring owner/case/revision-bound session and tickets are opaque. The new flow does not call `FifoCostTransitionEvidenceService.load`, factual readiness, prepare/apply, FIFO mutation, cost-history mutation, Return COGS or Period Profit.

## Synthetic Telegram path

The regression `tests/test_telegram_fifo_cost_provisional_service.py::test_regular_transition_callback_runs_summary_preview_without_persisting_fifo` traverses the production transition runtime callback contract with synthetic reports and the §4.3 rates `21.00 / 14.65 ₽`:

```text
Предварительная оценка FIFO — только сценарий
Снимок: 2026-11-05; движения: 2026-11-06 — 2026-11-20
Сценарное предположение о старом остатке: 21 шт.
Старые выкупы: 3,669–3,703; новые: 2,228–2,262
Себестоимость выкупов до сторно возвратов: 110,187.30–110,403.20 ₽
Значения не являются FIFO фактом; история FIFO и прибыль не меняются.
```

The test presses the normal `fifo_transition:*` buttons, supplies both owner assumptions, types the closing-stock hypothesis, calculates, retries an old callback (rejected stale), and asserts zero factual writes and no apply button. No Telegram network call or real report is used.

## Regression matrix

| Cases | Coverage in PR A | Result |
| --- | --- | --- |
| A01, A05, A07 | Eight opening/closing buckets, total `3,712`, available `1,988` not double-counted, §4.3 `[21,21]` exact ranges | Covered by summary control case and Telegram route. |
| A02 | Same total with bucket movement at the boundary | Covered; returns `SOURCE_CONFLICT` with no money. |
| A03 | Exact scope, owner-confirmed period, adjacent window; filename candidate rejected | Covered by summary/evidence-reader tests. |
| A04 | Unbalanced report control | Covered; no estimate. |
| A06 | Unsupported receipt/expense columns; S/AA compensation excluded | Covered; compensation is shown separately and does not change the range. |
| A08–A10 | Residual `[31,31]`, unknown residual, higher/equal rates | Covered against numeric matrix. |
| A11 | Empty integer distribution intersection | Covered by exhaustive range helper regression. |
| A12 | Partial order CSV delta `+1` and old deliveries after cutoff | Deferred to PR B PF11–PF13, which adds the dedicated CSV reader and comparison screen. PR A does not imply this comparison exists. |
| A13 | Small exhaustive integer allocations | Covered by property-style exhaustive matrix test. |

## Verification

- Linked affected profile: `pytest` over provisional summary/evidence/Telegram, production transition workflow, transition runtime/contracts and both existing report importers — **113 passed in 16.53s**.
- Full configured suite, disposable detached worktree at implementation SHA `63f60c2a3fe3b00268be1be8a124d7e90cb7f893`, repository `data/` removed and replaced only with synthetic `USN_INCOME 6%` tax policy: **5,491 passed in 110.55s**, no skips/deselections.
- `python -m compileall -q app tests` — passed.
- `git diff --check` — passed. `git diff --exit-code -- data` — passed; tracked user/runtime data unchanged.
- Exact-head hosted CI: pending publication of this PR. Use the current PR checks page for the exact final head; do not rely on earlier PR #740 baseline checks.

## Files changed

- New provisional service/contract/evidence-reader modules and synthetic tests.
- Small injection/callback additions to `app/services/telegram_fifo_cost_transition_runtime_service.py`, `app/telegram_assistant_factory.py`, and the production-workflow wiring test.
- New owner guide and Decision 068; updated CHANGELOG, CURRENT_STATE, TEST_MAP and progress journal.

## Preserved components and limits

- Factual FIFO contracts, event/layer/allocation writers, readiness, prepare/apply, current cost history, Period Profit, Return COGS, operational CSV cost import and Planning Workspace schema are unchanged.
- The aggregate model cannot recover intra-window order or exact sale-to-layer lineage. Unknown ending old stock remains a wide range. Report dates must be owner-confirmed, reports complete and all eight buckets continuous.
- No durable scenario store, event replay, CSV comparison, conditional profit, live API, real owner data, bot launch, merge or deployment is part of PR A.
- Independent review should focus on case/revision binding, the exact bucket and balance gates, the formula edge cases, and the invariant that provisional results never enter factual FIFO/COGS.


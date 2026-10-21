# Cross-docking unit economics — independent review packet

Date: 2026-10-21

Pull request: [#712 — Add cross-docking cost to unit economics and saved plans](https://github.com/dopf129-pixel/ai-business-assistant/pull/712)

Base: `main` / `7e6eabdeba34a822434e5ef417a135995628cc41`

Code head verified by full CI: `4f77cfef6e6725929a4b6539e376a258407e8305`

Branch: `codex/cross-docking-x00-x01`

## Scope and implementation

The change completes task X00–X06: collect Ozon cross-docking costs and actually accepted supply quantities, derive a 56-day per-supplied-unit rate, use that rate in unit-economics and planning, and preserve evidence in saved plans.

| Evidence | Ozon Seller API method | Role in the calculation |
|---|---|---|
| Financial accrual pages | `POST /v1/finance/accrual/by-day` | Signed classified leaf amounts by accrual date, including positive corrections/refunds. Parent totals and estimated tariffs are excluded. |
| Accrual type dictionary | `POST /v1/finance/accrual/types` | Resolves labels used by the shared cross-docking fee classifier. |
| Completed supply-order pages | `POST /v3/supply-order/list` | Enumerates completed orders with cursor pagination. |
| Order details | `POST /v3/supply-order/get` | Verifies completed order, nested supplies and cross-docking type. `state_updated_date` is used only for the verified single nested supply shape. |
| Acceptance act summary | `POST /v1/supply-order/act/summary/get` | Confirms the matching acceptance act for the supply/order. |
| Acceptance act product rows | `POST /v1/supply-order/act/product/get` | Reads SKU line `fact_quantity`; declared/approved quantities, summary totals, sales and supply counts are not used as the denominator. |

Date window: 56 completed calendar days, ending yesterday in `Europe/Moscow`. The financial numerator includes signed matching cross-docking leaves and corrections on their finance accrual dates. If expense leaves are attributable to one SKU, divide that SKU's amount by that SKU's accepted `fact_quantity`. For unattributed seller/container expense, use a separate store estimate divided by all accepted cross-dock units; do not add store and SKU rates together. A full source window without a usable denominator/rate remains a complete collection but an unavailable rate, never a numeric zero.

The historical denominator is actual delivered cross-dock units. In the sales-mix planner, the frozen per-supplied-unit rate is multiplied by planned successful sales `Q` to estimate the scenario expense. A missing rate for a SKU with positive `Q` makes the aggregate profit/margin partial. The factual side of plan/fact reconciliation is unchanged.

## Bounds, cache and persistence

- At most 64 HTTP attempts and 60 seconds per explicit calculation slice; attempts join the existing operation trace budget.
- Continuation checkpoint is process-local and scoped to tenant/store, exact date window and model version. Partial pages cannot yield a numeric rate.
- Complete evidence cache is tenant/store/window/model scoped with a 10-minute TTL. The current request's existing finance cache may cover the overlapping 28 days.
- No raw Ozon response or external supply/act/order identifier is persisted in the cross-docking evidence object. SKU identity remains only in the normal saved-plan identity fields.
- No SQL schema migration. Saved-plan payload/schema v2 is additive; v1 plans keep legacy calculations, do not read current Ozon supply evidence, and remain viewable.
- Rollback note: existing SQLite records are not deleted or rewritten. An older binary that only understands saved-plan v1 may not open newly written v2 plans until the new code is restored; retain the normal database backup before rollback.

## Verification

- X03 bounded Windows profile: 146 passed in 2.76s.
- X04 bounded Windows profile: 256 passed in 5.54s.
- X05 bounded Windows profile after the final unavailable-rate regression: 126 passed in 3.29s across 8 related modules.
- Changed-Python AST parse and `git diff --check` passed.
- Full local pytest was intentionally not run because of the task's recorded ACL/shared-storage incident. The PR workflow runs full tests and compilation on Windows/Linux and builds/smoke-tests production Docker on Linux.
- Initial full CI on `cec03f41a498e72d69365fab05ca488489d9afb9` found five v1/v2 plan/fact version regressions. They were fixed with a compatibility adapter and covered by a follow-up 52-test Windows profile.
- Exact code-head Verify [run 39591125957 (#3161)](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/39591125957) passed on `4f77cfef6e6725929a4b6539e376a258407e8305`: Linux **3,640 passed**, Windows **3,640 passed**, compile succeeded on both, and Linux production Docker build/runtime smoke succeeded. The PR may receive documentation-only updates for this handoff; review the latest PR head and its exact-head checks.
- No live Ozon API calls, Telegram bot run, merge, or deployment were performed.

## Review focus

Architecture review is required: the PR changes the collection pipeline, calculation projections, saved-plan schema/version compatibility, Telegram presentation and exports (60 files total).

1. Confirm official API semantics and the conservative single-nested-supply date rule; multi-supply ambiguity must remain excluded.
2. Confirm that only signed leaf accruals are summed and shared store expense is not double-counted with SKU-attributed fees.
3. Verify the 56-day window, exact `fact_quantity` denominator, request/time limits, checkpoint scoping, resume behavior and no partial-rate publication.
4. Verify that v1 snapshots do not acquire current rates, v2 snapshots are immutable, and explicit refresh writes only a new revision/copy after identity/CAS validation.
5. Verify rate × planned successful sales `Q` is deducted once in planning and never added to the factual plan/fact leg.
6. Confirm export/readiness/Telegram output does not expose external IDs or claim an unavailable rate is zero.

## Commit order

`0d9bc23f` supply evidence source → `3abab19c` signed expense and rate → `74c9ff7b` bounded production collector → `cf0dd2da` current and unit-economics integration → `4661cc3b` versioned saved plans → `cec03f41` complete-window/unavailable-rate fix and regression → `4f77cfef` v1/v2 plan-fact compatibility.

No merge or deployment is authorized by this handoff.

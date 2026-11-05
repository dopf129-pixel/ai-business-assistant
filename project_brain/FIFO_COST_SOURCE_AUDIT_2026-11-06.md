# FIFO cost history source audit

Date: 2026-11-06  
Audited code base: `main` `68aa6db09649bdbb4be406d423c6315a8961697b`, plus documentation-only FIFO task commits through implementation baseline `b971eedc`.  
Runtime files were not changed during this audit. All reproductions used temporary SQLite files under the OS temporary directory; no Ozon/Telegram calls were made.

## 1. Ownership and stored evidence

| Concern | Current authority and behavior | Audit result |
|---|---|---|
| Legacy mutable cost | `app/services/cost_service.py` (`ProductCostService`) and `app/services/base_cost_service.py`; `product_costs` stores `cost_price REAL`, currency, and `updated_at`. | A current projection only; it has no effective date or FIFO layer meaning of its own. |
| Direct legacy write | `ProductCostService.set_cost(...)` upserts only `product_costs`; does not append `product_cost_history` or `product_cost_switch_history`. The root `set_product_cost.py` is a direct/manual caller. | Preserve as legacy behavior only where explicitly supported; it cannot establish FIFO or historical inventory. |
| Bounded history | `record_historical_cost(...)` appends to `product_cost_history`; `get_historical_cost_evidence(...)` checks an explicit interval. | Append-only evidence. Period Profit rejects open-ended history and does not use a mutable current value as earlier-period evidence. |
| Operational switch | `PeriodProfitEffectiveCostService.record_cost_switch(...)` appends a dated switch and unconditionally upserts that same amount to `product_costs` in the same transaction. | Confirmed temporal projection defect for future and late backdated records; see reproductions below. |
| CSV batch switch | `record_cost_switches(...)` validates and writes atomically, accepts exact idempotent replay, then chooses the row with the greatest `effective_from` for `product_costs`. It does not cap that lookup at today. | Confirmed future-date defect. New/changed rows can cause the projection to jump forward before their effective date. |
| CSV entry flow | `SellerCostTableService.import_csv(...)` is read-only preview; first value without date defaults to today, existing value requires a date; “whole history” for initial entries uses `date.min` after a separate confirmation. Commit delegates to `record_cost_switches`. | Keep preview/confirm and the explicitly confirmed whole-history branch. CSV needs the same effective-date projection rules as the single-entry flow. |
| Telegram single-entry flow | `TelegramSellerCostUpdateService` displays a draft and does not write before confirmation. First cost defaults to today; subsequent cost changes default to tomorrow; “apply to whole history” is a separate confirmation. Commit delegates to `record_cost_switch`. | User-facing date behavior is intentional; storage currently violates the future-date promise. |
| Seller text correction | `PeriodProfitCostConfirmationRuntimeService` parses an amount and explicit effective date, resolves one current product identity, and delegates to `record_cost_switch`. | Can create late/backdated switch; therefore must share the corrected projection path and never bypass FIFO once a product is activated in that mode. |
| Legacy current timestamp fallback | `ProductCostService.get_historical_cost_evidence(...)` may use a mutable `product_costs.updated_at` as seller-entered legacy evidence from that date through today. | Existing compatibility evidence, not a switch history. A future switch currently overwrites it and moves its apparent cost/effective start to the write timestamp. FC05 must keep provenance distinct and fail closed where a version cannot be established. |
| Cost history CLI | Root `record_product_cost_history.py` writes explicit historical evidence. | No current projection mutation was observed in this path. |

## 2. Readers and calculation paths

| Reader | Current cost selection | Consequence / constraint |
|---|---|---|
| Period Profit sale COGS | `PeriodProfitEffectiveCostService.get_effective_cost_evidence(at_date, identity)` selects the latest switch with `effective_from <= at_date`, then bounded history; quantity service passes finance accrual date after its existing physical quantity authority/dedup chain. | Date resolver is the intended historical boundary, but fallback to mutable-row timestamp is vulnerable to a switch write having overwritten the row. Finance date remains a finance recognition date, not proof of physical shipment timestamp. |
| Return COGS | Existing origin-sale evidence resolves cost at the matched originating sale date. Inventory recovery, accounting attribution/recognition, authorization and commit are separate gates. | Preserve every monetary gate; a FIFO allocation cannot by itself authorize return-profit correction. |
| Current unit economics | `ProductUnitEconomicsQueryService._current_cost(...)` calls `get_cost(product_id)`; its optional cache is keyed by tenant and offer/SKU, not cost revision. TTL defaults to zero at the service boundary but can be configured; explicit `refresh(...)` bypasses it. | No date-aware authority or immediate revision-based invalidation. |
| Price calculator source | `UnitPriceScenarioSource._load_cost(...)` calls `get_cost(product_id)` and stores the complete source snapshot in a 600-second scoped cache; `force_refresh` is available. Key includes tenant/user/SKU and exact product identity when supplied, but no cost revision. | Cost update may remain invisible until cache expiration or explicit force refresh. Frozen plans should retain their captured value and gain explicit basis/revision rather than silently reprice. |
| Legacy store period profit | `StorePeriodProfitService.calculate_period_profit(...)` calls `get_cost(product_id)` once for the requested interval. `telegram_core_factory.py` wires this service. | A multi-date range can be costed at one mutable current amount; FC05/FC17 must route supported historical calculations through the dated authority or explicitly preserve/fail-close an unsupported legacy path. |
| Assistant runner | `app/assistant_runner.py` uses `get_cost(product_id)` for its current finance/profit display. | Current-only presentation; should use the same as-of-current adapter when FIFO is introduced. |
| Product-cost menu/import support | `TelegramSellerCostUpdateService` and `SellerCostTableService` enumerate `get_all_costs()` to decide whether a SKU is initialized and to export current values. | These screens read projection state, not a resolved event timeline. A future switch currently looks like the current price. |

The explicit production `get_cost(...)` calls found by repository search are in `assistant_runner.py`, `product_unit_economics_query_service.py`, `store_period_profit_service.py`, and `unit_price_scenario_source.py`. No `delete_cost(...)` production caller was found. Existing plan snapshots and observation/experiment records are immutable/versioned data owners; do not re-resolve their prior basis on read.

## 3. Isolated reproduction of confirmed defects

The audit used `PeriodProfitEffectiveCostService` with `get_connection()` redirected to three fresh temporary SQLite files. The effective test date was the environment date `2026-11-06`.

| Case | Synthetic actions | Observed result | Expected behavior |
|---|---|---|---|
| Future single change | `set_cost=20`; `record_cost_switch=25` effective `2026-11-07`; read today | `get_cost` returned **25**. `get_effective_cost_evidence(2026-11-06)` also returned **25**, provenance `SELLER_CONFIRMED_LEGACY_CURRENT_TIMESTAMP`, because the switch write overwrote the current row and timestamp today. | Today remains 20; 25 becomes current only on its effective date. A future switch must not become legacy evidence for today. |
| Late old single row | Switches `20` from `2026-10-27` and `25` from `2026-11-16`; then late insert `18` from `2026-10-17`; read today | Current projection returned **18**, while the dated resolver returned **20**. | A late older event must not roll back today’s projection; historical dates resolve from their effective timeline. |
| Future batch | Atomic batch `20` from today plus `25` tomorrow; read today | Current projection returned **25** while date resolver returned **20**. | Batch and single writes choose the latest effective version not later than the as-of date, never simply the maximum date. |

These reproduce the confirmed FC01 defects without touching owner data. Existing tests already cover historical version lookup, current-row timestamp boundaries, dated switch precedence, and CSV replay/idempotency, but do not assert future single/batch projection, late-old projection, and no accidental legacy fallback after a future switch.

## 4. Confirmed invariants to preserve

- Ozon remains read-only. Product stock/order/act calls are candidate evidence only and must not be changed by cost entry.
- Period Profit’s physical quantity source and duplicate-accrual handling remain authoritative; an accrual line or order is not an extra physical sale.
- Historical cost evidence is bounded unless an operational switch has an explicit effective date. The legacy timestamp fallback must remain distinguishable from seller-confirmed FIFO layers.
- Existing cost callbacks are scoped to user/store and draft identity; preview/cancel does not write.
- Price-planning snapshots are frozen artifacts; corrections create new revisions and do not rewrite old saved plans or observations.
- Return inventory/accounting evidence and its authorization/application chain stay separate from quantity layer replay.

## 5. FC02 source questions (not yet resolved)

- Exact current official contract and production response shape for FBO inventory at `/v4/product/info/stocks`, including present/reserved meaning, inventory scope, timestamp, pagination, and whether the response is a coherent point-in-time cutoff.
- Whether an Ozon “available” aggregate duplicates warehouse rows or is a separate summary; how to avoid adding aggregate and detail twice.
- Which supply/act fields prove a supply belongs to a selected cost transition, how partial acceptance maps to SKU quantity, and whether status/created/slot dates can prove the physical acceptance boundary. They are not interchangeable by assumption.
- Whether old goods in transit can be read without overlap with current Ozon stock and with a bounded completeness watermark.
- Stable physical-sale identity for realization/FBO/FBS records and a watermark that bridges stock snapshots to delayed finance accruals without double-consuming old quantity.
- Historical inventory movement evidence needed for late correction. Current stock plus finance sales alone is not sufficient proof if other movements are omitted.

No owner decision is needed for this audit. FC02 must use official documentation and existing sanitized fixtures/diagnostics only; if exact semantics cannot be proven without live owner validation, mark that source/flow blocked rather than inventing a field meaning.


# FIFO cost history source audit

Date: 2026-11-06  
Audited code base: `main` `68aa6db09649bdbb4be406d423c6315a8961697b`, plus documentation-only FIFO task commits through implementation audit SHA `5a70ccbbf2053920fe4c5efdf7dd7c48d25c1a1b`.
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

## 6. FC02 evidence matrix and decision

FC02 was completed as a source proof, not as a claim that every source is sufficient. The key result is that current Seller API paths do not establish one shared stock/finance cutoff. No live request was made.

| Source | Locally used fields / behavior | Official evidence and supported use | FC02 status for factual FIFO |
|---|---|---|---|
| `/v4/product/info/stocks` | `get_product_stocks(product_id)` sends a product filter and `limit=100`. `MetricsService` reads `items[].product_id`, `stocks[].type`, `present`, `reserved`; it sums `present` and `reserved` for `type=fbo` and calculates available as `present-reserved`. It does not retain a server `as_of`, cursor/watermark, or source revision. | Ozon's current notice says `/v4/product/info/stocks` is changing from `total` to `total_items` on 23 Nov 2026. The current interactive API reference is JavaScript-rendered and the schema could not be extracted. The official FAQ explains `present`/`reserved` on an older `/v3` contract only; that is explicitly not evidence for the current v4 contract. [Ozon v4 field change](https://dev.ozon.ru/news/801-Otkaz-ot-polia-total-v-metodakh-Seller-API/), [older FAQ, not v4 proof](https://dev.ozon.ru/start/257-FAQ-spravochnik-oshibok-i-sposobov-ikh-resheniia). | Request adapter can be reused after a current sanitized response validates fields and paging; field semantics and server cutoff remain **OWNER_VALIDATION_REQUIRED**. Local receipt time is `captured_at`, not an Ozon server snapshot time. Do not derive a fact anchor from it without explicit owner confirmation and cutoff status. |
| `/v1/analytics/stocks` | No FIFO adapter is currently wired. | Ozon's official notice adds live inventory status fields including `inbound_replenishment` (goods in transit), returns-in-motion states, and `stock_not_being_sold`. It does not establish whether these quantities overlap the v4 `present`/`reserved` values or exactly which accepted supply is represented. [Ozon stock status fields](https://dev.ozon.ru/news/792-Izmeneniia-v-metodakh-analitiki-po-stokam-v-Seller-API/). | Candidate for a transit diagnostic only. Do not add `inbound_replenishment` to FBO present or supply-act quantity until the seller response proves disjoint scope and stable SKU identity. |
| `/v3/supply-order/list`, `/v3/supply-order/get`, acceptance summary and product methods | Existing normalizer filters completed orders/supplies, checks exact act ID and agreement, reconciles SKU `fact_quantity` to accepted summary, rejects unidentified units and ambiguous/multiple SKU. | Ozon says v2 supply methods may return incorrect statuses and recommends v3. For cross-docking, Ozon says `storage_warehouse.arrival_date` will always be `null`; `warehouse_id` is no longer relevant. [Ozon supply API versions](https://dev.ozon.ru/news/643-Izmeneniia-v-metodakh-dlia-zaiavok-na-postavku-v-Seller-API/), [cross-docking supply fields](https://dev.ozon.ru/news/647-Izmeneniia-v-metodakh-Seller-API-pri-rabote-s-postavkami-FBO/). The supplied bot diagnostics and tests support accepted `fact_quantity` as a quantity when act identity/reconciliation pass, not a physical receipt timestamp. | Accepted quantity can be a **count** with confirmed provenance. `state_updated_date`, act `created_date`, planned slot, and shipment date are not accepted as actual receipt time. Historical effective boundary remains **UNPROVEN** for crossdock. |
| Finance accruals `/v1/finance/accrual/by-day` and `/v1/finance/accrual/postings` | Current Period Profit deduplicates by `posting_number + SKU`, reconciles positive quantities, but groups records on `accrual_date`; it does not carry a proven physical stock-exit timestamp into FIFO. | Ozon retired old transaction-list endpoints in favor of these accrual endpoints, instructs callers to send requests sequentially, and cautions that returned data can differ from Seller Cabinet. [Ozon finance API change](https://dev.ozon.ru/news/783-Izmeneniia-v-metodakh-dlia-raboty-s-finansovymi-otchetami-v-Seller-API/). | Stable identity/quantity can feed existing financial COGS only with current reconciliation. `accrual_date` is financial recognition evidence, not independently proven physical stock-exit time or a watermark against an inventory snapshot. **No factual cutoff bridge yet.** |
| FBO/FBS postings and `/v1/returns/list` | Used by current quantity/return evidence paths for posting identity, line quantity, status and return type. Return COGS separately requires sale lineage, saleable-restored inventory evidence, recognition period and authorization. | Ozon describes returns and inventory state separately; project Decision 040 already rejects current stock or return visual status alone as proof of saleable inventory recovery. | Posting/return identity is not a complete inventory movement ledger. Cancelled, unredeemed, damaged, lost and returned quantities cannot be implicitly interpreted as FIFO replenishment or physical sale. |

### Negative cutoff fixture

`tests/fixtures_fifo_cutoff_gap_v1.json` is an intentionally synthetic counterexample, not a captured API response and not owner data. It demonstrates two different cases: a sale physically removed before the stock anchor whose finance accrual appears later must consume **zero additional** anchor units; a proven post-anchor sale consumes once. The current FIFO path cannot establish the physical exit timestamp or shared watermark, so the exact current behavior for either event is `INVENTORY_CUTOFF_UNRECONCILED`; factual FIFO COGS must fail closed. The fixture is retained for FC16/FC17 regression coverage.

### FC02 outcome

- Supported in implementation planning: bounded source adapters and identity validation; accepted supply quantity only when act/summary/product evidence reconciles; inventory observations tagged with client capture interval; seller-confirmed anchors clearly labeled as owner evidence; deterministic FIFO replay of already accepted facts.
- Not supported as an accounting fact yet: crossdock effective receipt time; v4 present/reserved meaning until validated against a sanitized current response; whether transit and FBO quantities are disjoint; stock-to-finance watermark; physical sale timestamp/late accrual bridge; complete historic movement replay.
- Consequence for FC03 onward: implement a guarded `INVENTORY_CUTOFF_UNRECONCILED` status. Do not inject synthetic allocations into factual Period Profit. Provide an explicit model/simulation path only if distinctly labeled and isolated from saved financial results. Keep the implementation PR's owner-acceptance checklist for safe read-only validation outside this development run.

## 7. Official references

- [Ozon: replacement of `total` by `total_items` in v4 product stocks](https://dev.ozon.ru/news/801-Otkaz-ot-polia-total-v-metodakh-Seller-API/) (24 Sep 2026; announced effective date 23 Nov 2026).
- [Ozon: live FBO stock status fields, including `inbound_replenishment`](https://dev.ozon.ru/news/792-Izmeneniia-v-metodakh-analitiki-po-stokam-v-Seller-API/) (11 Sep 2026).
- [Ozon: crossdock `arrival_date` always null in supply methods](https://dev.ozon.ru/news/647-Izmeneniia-v-metodakh-Seller-API-pri-rabote-s-postavkami-FBO/) (19 Jan 2026).
- [Ozon: switch supply order integrations to v3 because old versions can return incorrect statuses](https://dev.ozon.ru/news/643-Izmeneniia-v-metodakh-dlia-zaiavok-na-postavku-v-Seller-API/) (20 Nov 2025).
- [Ozon: current finance accrual endpoints, sequential calls, possible mismatch from Seller Cabinet](https://dev.ozon.ru/news/783-Izmeneniia-v-metodakh-dlia-raboty-s-finansovymi-otchetami-v-Seller-API/) (24 Aug 2026).

No owner decision was needed for FC02. It used official documentation and existing sanitized diagnostics only. Exact semantics that cannot be proven without live owner validation remain explicitly blocked rather than inferred.

## FC08 normalization boundary

`app/services/fifo_cost_source_normalizer.py` is a pure normalizer; it is not connected to an Ozon client and does not prove the current fields' business semantics. It requires the caller to supply explicit page completeness, capture time and a catalog identity `(product_id, offer_id, sku)`. A returned stock `total_items` greater than the rows received marks the snapshot partial; fewer items than returned rows is a conflict. The normalizer does not invent `source_as_of`.

`present` is kept as the FBO layer quantity and `reserved` as its subset; `available_units` is an auxiliary `present - reserved` value only when field semantics are explicitly confirmed. Transit remains unknown unless both its source read is complete and non-overlap is explicitly confirmed. Even then `anchor_eligible` remains false because FC02 has not validated a shared physical-sale cutoff.

Supply act SKU `fact_quantity` lines are reconciled against the accepted-act summary. Identical repeated representations are deduplicated by stable SHA-256 references; conflicting duplicates, unmatched accepted acts, unidentified units, incomplete reads and multi-SKU supplies fail closed. Act `created_date`, parent `state_updated_date`, local capture time and crossdock `arrival_date` are not written as physical receipt time. Synthetic verification is in `tests/test_fifo_cost_source_normalizer.py`; no live responses were used.

## FC09 bounded collection

`app/services/fifo_cost_source_collection_service.py` is an explicit read-only adapter over `OzonClient`; it does not run on a schedule and does not write facts. It passes the existing parent operation trace into all calls, limits retries to one per client method, enforces per-request timeouts, counts actual attempts through the transport observer and stops child calls on parent cancellation/deadline/budget exhaustion. Concurrent calls for the same owner/store/SKU/source are single-flight. Supply lookup has finite page/row limits and an opaque, expiring, single-use continuation tied to owner/store/SKU/supply scope; page/order references are fingerprinted instead of retained in raw form. A failed/partial read cannot become a complete negative search.

Synthetic FC09 regression profile: `tests/test_fifo_cost_client_contract.py` and `tests/test_fifo_cost_source_collection_service.py`, linked with FIFO normalizer/kernel/repository and existing supply/act tests — **117 passed**. No live Ozon/Telegram calls were made. The physical stock-to-sale cutoff gap described above remains unchanged.

## FC10 owner-confirmed opening anchor

`FifoCostAnchorService` accepts only explicit manual owner evidence: a date-only cutoff, one or more finite old cost layers in an explicit oldest-to-newest order, and separate Ozon/transit/home integer quantities per layer. Ozon present (including reserved units) and non-overlap of transit must each be explicitly confirmed. A zero in any zone is retained as an opaque source reference; a missing field is not zero. The preview does not write; the confirmed repository command creates per-zone anchor events and one projection atomically. The projection's operational queue is ready, but its factual Period Profit cutoff remains `INVENTORY_CUTOFF_UNRECONCILED`. This flow does not use an unvalidated API snapshot as owner confirmation and does not change legacy histories.

FC10 synthetic profile: `tests/test_fifo_cost_anchor_service.py` plus repository/kernel and FC08/FC09 regressions — **113 passed**. All stateful checks use temporary SQLite; no live source or owner data.

The FC10 write boundary requires a normalized store/SKU identity plus at least one stable product identifier; any malformed supplied identifier is rejected instead of being silently discarded. Persisted anchor events require the exact owner-confirmation source method, capture timestamp, matching date-only cutoff/effective date, and no fabricated `effective_at`. This remains owner evidence and does not resolve the physical stock-to-sale source gap.


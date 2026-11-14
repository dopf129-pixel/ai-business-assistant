# FIFO automatic batch supply source contract

Checked: 2026-11-13. This note separates official Ozon claims from existing client adapters and synthetic test data. It does not establish complete historical supply or inventory-movement coverage.

## Officially confirmed

| Operation / fact | Confirmed information | Source |
|---|---|---|
| `POST /v3/supply-order/list` | Ozon's guide calls this the method for listing available supplies/orders. The guide does not expose the complete request/response JSON or a complete raw state enum in readable text. | [FBO Seller API scanner guide](https://dev.ozon.ru/start/526-Gaid-integratsiia-metodov-Seller-API-FBO-so-skanerom/) |
| `POST /v3/supply-order/get` | The guide says it obtains data for a known `supply_id`; a separate Ozon notice says this v3 method replaces v2. No full schema is visible in the public page rendering used for this check. | [FBO Seller API scanner guide](https://dev.ozon.ru/start/526-Gaid-integratsiia-metodov-Seller-API-FBO-so-skanerom/), [v2 to v3 migration notice](https://dev.ozon.ru/news/643-Izmeneniia-v-metodakh-dlia-zaiavok-na-postavku-v-Seller-API/) |
| `POST /v1/supply-order/bundle` | Ozon's guide explicitly says its request uses `supply_id` and `bundle_id`, and its result contains product SKUs and quantities (also barcodes and cargo restrictions). This does not reveal the complete JSON keys, types, relation of `bundle_id` to nested supplies, or a pagination contract. | [FBO Seller API scanner guide](https://dev.ozon.ru/start/526-Gaid-integratsiia-metodov-Seller-API-FBO-so-skanerom/) |
| Cross-docking `arrival_date` | From 2026-02-16, `storage_warehouse.arrival_date` is returned as null for the affected cross-docking methods. It cannot prove dispatch or receipt date. The notice also introduces `macrolocal_cluster_id` and says `warehouse_id` loses relevance for cross-docking. | [FBO supply API change notice](https://dev.ozon.ru/news/647-Izmeneniia-v-metodakh-Seller-API-pri-rabote-s-postavkami-FBO/) |

The official API reference `https://docs.ozon.ru/api/seller/` rendered without readable operation schemas in this review. No live seller request was made. No user credentials or seller responses were used.

## Existing local adapter contract (verified in code, not a claim about undocumented raw JSON)

`app/api/ozon_client.py` currently exposes read-only wrappers:

- `get_supply_orders_list(states, last_id=None, limit<=100, sort_by, sort_dir, ...)` posts to `/v3/supply-order/list` with `filter.states`, `limit`, `sort_by`, `sort_dir`, and optional `last_id`. The adapter currently normalizes the response to `order_ids` and `last_id`.
- `get_supply_orders_details(order_ids<=50, ...)` posts to `/v3/supply-order/get` with `order_ids`. The adapter returns an `orders` collection to callers.
- Existing code consumers inspect nested order `supplies` containing `supply_id`, `state`, and sometimes `is_crossdock`. Existing cross-docking logic deliberately scopes to `COMPLETED`; its narrower status/window semantics must not be reused as proof of general batch coverage.
- Existing act methods and normalizers can reconcile acceptance; tested product fields include `sku_info.sku`, `declared_quantity`, `approved_quantity`, and `fact_quantity`. Missing `fact_quantity` is not zero.

These are the current application's validated interfaces and synthetic test shapes. They do not prove the authoritative raw Seller API schema, completeness of a list cursor over history, or actual dispatch timing.

FB12 implementation uses the wrapper contract only: list pages are requested at no more than 100 IDs; detail calls contain at most 50 orders; each order must match exactly one requested ID and expose a nested supplies list before its supply references are counted. A shorter page with no `last_id` is terminal only for this local wrapper; a full page without a cursor stays partial. Overlapping order IDs are deduplicated and flagged. This does not verify raw response semantics or full historical coverage. The current continuation is a bounded process-local transport checkpoint, not durable scan evidence.

## Unverified fields / safe adapter behavior

| Needed fact | Status | Required behavior until proven |
|---|---|---|
| Complete supported `state` enum for all list/get orders and nested supplies | `NOT_VERIFIED` | Use only an explicit tested allowlist; any new or missing enum is `UNKNOWN` and makes coverage partial. |
| Raw list cursor field and proof of terminal page | `NOT_VERIFIED` beyond current application's `last_id` wrapper | Do not call a full page complete without reliable terminal-page proof; repeated cursor is partial/conflict. |
| Exact raw details response keys and nested supply bundle linkage | `NOT_VERIFIED` beyond current application's synthetic adapter shape | Require a strict normalizer; malformed/missing linkage is unknown. |
| Exact bundle request and response JSON, pagination, per-SKU quantity key/type | Only `supply_id`, `bundle_id`, SKU+quantity concept confirmed by Ozon guide | Do not send an invented body or read a guessed quantity key. Keep a normalized adapter interface and return `UNKNOWN` until a documented or owner-supplied anonymized fixture establishes the concrete mapping. |
| Actual dispatch date/time | `NOT_VERIFIED` | Do not substitute order creation/update, timeslot, act date, or numeric IDs. Use unknown-date grouped owner confirmation. |
| Actual physical receipt timestamp | `NOT_VERIFIED` by this supply list/detail contract | Keep accepted quantity separate; do not infer historic physical stock movements. R1 remains open. |

## Synthetic fixtures

The fixture files under `tests/fixtures/fifo_cost_batch_source/` are explicitly synthetic, redacted, and adapter-level. They illustrate only fields already consumed by this repository's local wrapper. They must not be treated as raw Ozon payload samples or expanded with guessed bundle fields.

## Evidence reviewed

- Ozon for Developers, “Гайд: интеграция методов Seller API FBO со сканером”, published 2026-06-10; confirms list/get use and the `supply_id` + `bundle_id` bundle request concept and SKU/quantity result.
- Ozon for Developers, “Изменения в методах Seller API при работе с поставками FBO”, published 2026-01-19; cross-dock `storage_warehouse.arrival_date` is null from 2026-02-16.
- Ozon for Developers, “Изменения в методах Seller API для работы с заявками на поставку”, published 2025-11-20; v2 list/get were to be replaced by v3.
- Existing adapter and synthetic tests: `app/api/ozon_client.py`, `tests/test_experimental_supply_act_diagnostic.py`, `tests/test_cross_docking_supply_source.py`, and `app/services/fifo_cost_source_collection_service.py`.

The source gap is a real implementation limitation, not a reason to invent an API contract. Independent rule, storage, and UI work may proceed behind the strict adapter boundary.

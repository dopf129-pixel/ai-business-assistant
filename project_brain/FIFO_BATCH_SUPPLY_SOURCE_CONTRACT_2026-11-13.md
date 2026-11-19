# FIFO automatic batch supply source contract

Checked: 2026-11-17, incorporating the owner's pasted Ozon Seller API operation descriptions for `/v1/supply-order/bundle`, `/v3/supply-order/list`, and `/v3/supply-order/get`, plus the owner's single read-only Seller API response showing HTTP 400 for filter state `UNSPECIFIED`. This note separates documented schema, observed seller response, and synthetic test data. It does not establish complete historical supply or inventory-movement coverage.

## Officially confirmed

| Operation / fact | Confirmed information | Source |
|---|---|---|
| `POST /v3/supply-order/list` | Official operation description: required `filter` object; optional `last_id` string, `limit` integer (1-100), `sort_by`, `sort_dir`. Response has `order_ids`, `last_id`. | Owner-provided Ozon Seller API operation description, received 2026-11-14 |
| `POST /v3/supply-order/list` filter value | The owner's read-only request was rejected with HTTP 400 because `filter.states[11]` was `UNSPECIFIED`, a zero/unknown enum value that Ozon does not allow as a filter. This confirms rejection of that value only; it does not confirm acceptance of every other state. | Owner-provided terminal response, received 2026-11-17 |
| `POST /v3/supply-order/get` | Official operation description: `order_ids` is an array of integer ID strings, up to 50. Response includes `orders` with `order_id`, `state`, `state_updated_date`, and nested `supplies` including `supply_id`, `state`, `is_crossdock`, `bundle_id`, and warehouse/timeslot fields. The documented enum below is for the parent order's `state`; the excerpt does not define a separate nested supply `state` enum. | Owner-provided Ozon Seller API operation description, received 2026-11-15 |
| `POST /v1/supply-order/bundle` request | Official operation description: `bundle_ids` is an array of strings (1-100); `last_id` is an optional string; `limit` is an integer (1-100). | Owner-provided Ozon Seller API operation description, received 2026-11-14 |
| `POST /v1/supply-order/bundle` response | Pasted operation docs specify `items` array, `total_count` integer, `has_next` boolean, and `last_id` string. Item fields include `sku` integer, `quantity` integer, `offer_id` string, `product_id` integer, `name` string, and `barcode` string. Returned item rows do not expose a parent `bundle_id`. | Owner-provided Ozon Seller API operation description, received 2026-11-14 |
| Bundle quantity semantics | `items[].quantity` is bundle composition. The documentation does not establish physical dispatch or accepted warehouse quantity. | Owner-provided Ozon Seller API operation description, received 2026-11-14 |
| Nested supply link | Pasted `/v3/supply-order/get` docs include `supplies[].bundle_id`; because bundle result items do not echo their parent ID, request exactly one bundle ID at a time when binding rows to a supply. | Owner-provided Ozon Seller API operation descriptions, received 2026-11-14 |

The pasted `/v3/supply-order/get` description documents these parent `orders[].state` values and meanings: `UNSPECIFIED`, `DATA_FILLING`, `READY_TO_SUPPLY`, `ACCEPTED_AT_SUPPLY_WAREHOUSE`, `IN_TRANSIT`, `ACCEPTANCE_AT_STORAGE_WAREHOUSE`, `REPORTS_CONFIRMATION_AWAITING`, `REPORT_REJECTED`, `COMPLETED`, `REJECTED_AT_SUPPLY_WAREHOUSE`, `CANCELLED`, and `OVERDUE`. This response enum is not the list-filter allowlist: the owner's seller-specific HTTP 400 confirms `UNSPECIFIED` is rejected in `filter.states`. The local filter therefore sends the other 11 documented values. Their seller-specific acceptance remains unverified. This does not establish the nested `supplies[].state` enum, actual seller payload profile, or completeness of historical list pagination.

The operation schema was supplied from the owner's Ozon Seller API documentation text. It is documentation evidence, not a seller-specific API response. No live seller request was made and no credentials were used.

## Existing local adapter contract (verified in code, not a claim about undocumented raw JSON)

`items[].quantity` is the bundle composition quantity. The docs do not establish that it proves physical dispatch or accepted warehouse quantity. Therefore quantity from this endpoint may populate planned/declared composition only; shipped and accepted quantities remain unknown.

- `get_supply_orders_list(states, last_id=None, limit<=100, sort_by, sort_dir, ...)` posts to `/v3/supply-order/list` with `filter.states`, `limit`, `sort_by`, `sort_dir`, and optional `last_id`. The adapter currently normalizes the response to `order_ids` and `last_id`.
- `get_supply_orders_details(order_ids<=50, ...)` posts to `/v3/supply-order/get` with `order_ids`. The adapter returns an `orders` collection to callers.
- `get_supply_order_bundle(bundle_ids, last_id=None, limit<=100, ...)` posts to `/v1/supply-order/bundle`; callers must request one bundle ID at a time to retain the parent-supply binding. Pagination and row interpretation remain the source service’s responsibility.
- Existing code consumers inspect nested order `supplies` containing `supply_id`, `state`, and sometimes `is_crossdock`. Existing cross-docking logic deliberately scopes to `COMPLETED`; its narrower status/window semantics must not be reused as proof of general batch coverage.
- Existing act methods and normalizers can reconcile acceptance; tested product fields include `sku_info.sku`, `declared_quantity`, `approved_quantity`, and `fact_quantity`. Missing `fact_quantity` is not zero. The existing reconciler deduplicates repeated cumulative snapshots, sums distinct acts, preserves a last known accepted amount beneath a newer partial read, and requires review for a decrease.
- An act `created_date` and an API capture timestamp are not physical receipt timestamps; the normalized `FifoSupplyActSnapshot.effective_at` is deliberately unset. FB14 revalidated these existing semantics, but did not wire act acquisition into the new automatic batch source.

These are the current application's validated interfaces and synthetic test shapes. They do not prove the authoritative raw Seller API schema, completeness of a list cursor over history, or actual dispatch timing.

FB12 implementation uses the wrapper contract only: list pages are requested at no more than 100 IDs; detail calls contain at most 50 orders; each order must match exactly one requested ID and expose a nested supplies list before its supply references are counted. A shorter page with no `last_id` is terminal only for this local wrapper; a full page without a cursor stays partial. Overlapping order IDs are deduplicated and flagged. This does not verify raw response semantics or full historical coverage. The current continuation is a bounded process-local transport checkpoint, not durable scan evidence.

FB13 implementation adds `FifoCostBatchBundleNormalizer` as a typed boundary over the existing `SupplySkuObservation` contract. It only maps exact owner/store/SKU observations sharing one supply and order digest, rejects duplicate SKU/record mappings, and keeps planned and shipped composition quantities separate. It requires explicit-zero provenance for zero quantities and preserves partial quantities as `PARTIAL`. This normalizer never parses a raw bundle dictionary.

FB22 now implements a strict raw parser for the owner-provided documented wrapper body and JSON key/type contract, per-bundle pagination, exact parent-supply binding by issuing one `bundle_id` per request, scoped observation persistence, and encrypted durable continuation. `items[].quantity` may populate only planned/declared composition; shipped and accepted quantities remain unknown. The parser rejects unexpected types, inconsistent `total_count`, malformed continuation, repeated/non-advancing cursors, and incomplete pages instead of treating them as zero or complete.

## Unverified fields / safe adapter behavior

| Needed fact | Status | Required behavior until proven |
|---|---|---|
| Parent `orders[].state` documented enum | `CONFIRMED_DOCUMENTED` | The enum describes response values, not accepted filter values. Keep list/source coverage partial until the seller payload and pagination profile are verified. |
| `filter.states` acceptance | `UNSPECIFIED_REJECTED_BY_SELLER_RESPONSE`; all remaining values `NOT_VERIFIED` | Exclude `UNSPECIFIED` from list filters. The other 11 documented values remain the current request profile but must not be described as seller-verified. |
| Nested `supplies[].state` enum | `NOT_VERIFIED` | Use only the current tested nested-state allowlist; an unsupported or missing nested status makes coverage partial. Do not infer nested state or filter acceptance from the parent enum. |
| Raw list cursor field and proof of terminal page | `NOT_VERIFIED` beyond current application's `last_id` wrapper | Do not call a full page complete without reliable terminal-page proof; repeated cursor is partial/conflict. |
| Exact raw details response keys and nested supply bundle linkage | `NOT_VERIFIED` beyond current application's synthetic adapter shape | Require a strict normalizer; malformed/missing linkage is unknown. |
| Exact bundle request/response JSON, pagination, per-SKU quantity key/type | Confirmed by owner-pasted official operation docs; raw parser and synthetic pagination tests implemented in FB22 | Use documented fields/types only. Process one bundle per request; paginate using `has_next`/`last_id` under the shared action budget. Owner text is not a seller-specific response. |
| Actual dispatch date/time | `NOT_VERIFIED` | Do not substitute order creation/update, timeslot, act date, or numeric IDs. Use unknown-date grouped owner confirmation. |
| Actual physical receipt timestamp | `NOT_VERIFIED` by this supply list/detail contract | Keep accepted quantity separate; do not infer historic physical stock movements. R1 remains open. |

## Synthetic fixtures

The fixtures under `tests/fixtures/fifo_cost_batch_source/` remain synthetic and must not be presented as seller-specific responses. They may use documented bundle fields with clearly synthetic values, and must not infer shipment or receipt semantics.

## Evidence reviewed

- Owner-provided official operation descriptions for `/v1/supply-order/bundle`, `/v3/supply-order/list`, and `/v3/supply-order/get`, received 2026-11-14 and 2026-11-15; they establish the request/response fields and parent-order enum recorded above, but do not prove seller-specific payloads, dispatch or physical receipt semantics.
- Owner-provided read-only terminal output for `/v3/supply-order/list`, received 2026-11-17: seller response HTTP 400 rejects `UNSPECIFIED` in `filter.states`. No further live seller call was made for this fix; acceptance of other filter values remains unverified.
- Ozon for Developers, “Изменения в методах Seller API при работе с поставками FBO”, published 2026-01-19; cross-dock `storage_warehouse.arrival_date` is null from 2026-02-16.
- Ozon for Developers, “Изменения в методах Seller API для работы с заявками на поставку”, published 2025-11-20; v2 list/get were to be replaced by v3.
- Existing adapter and synthetic tests: `app/api/ozon_client.py`, `tests/test_experimental_supply_act_diagnostic.py`, `tests/test_cross_docking_supply_source.py`, and `app/services/fifo_cost_source_collection_service.py`.

The source gap is a real implementation limitation, not a reason to invent an API contract. Independent rule, storage, and UI work may proceed behind the strict adapter boundary.

## 2026-11-19 — supply-list request-order compatibility

Both FIFO order-list paths use sort_by=ORDER_CREATION and sort_dir=DESC. The status filter remains the existing 11 non-zero states. The owner supplied a live comparison for the same shop/request: ASC returned HTTP 400 with “Ascending sort direction is not supported for archive order states.”; DESC returned HTTP success and 10 order IDs. This confirms that the first page is readable with DESC for that shop and request.

A successful first page does not prove pagination/history completeness, physical dispatch or acceptance, or FIFO readiness. Continuation tokens are bound to source contract OZON_SUPPLY_BUNDLE_V1_ORDER_LIST_DESC_V2; a saved continuation from the former ASC contract is left in storage as historical evidence but is not resumed. Refresh begins a new scan at page one.

## FB19 — source capability matrix at PR B checkpoint

| Source area | Local implementation/test status | Safe claim at this checkpoint |
|---|---|---|
| `/v3/supply-order/list` | Existing allowlisted wrapper is used with page limit ≤100, opaque continuation, shared HTTP/time budgets, repeated-cursor and overlapping-page checks. | Local wrapper transport is exercised; raw cursor meaning, raw state coverage, and complete historical enumeration are **NOT_VERIFIED**. Full pages without terminal proof remain partial. |
| `/v3/supply-order/get` | Existing allowlisted details wrapper batches at ≤50 orders and validates one exact returned order per requested order; nested supplies are collected without using the cross-docking-only `COMPLETED` filter. | Local normalized details shape is exercised; Ozon raw details schema and all nested state values are **NOT_VERIFIED**. Unsupported states remain visible as a gap. |
| Nested `supplies` | Exact `supply_id`, state, and optional strict boolean `is_crossdock` are validated; supply identity is opaque and scoped to owner/store/product/offer/SKU. | IDs are not exposed in public summaries or callbacks. The local shape is not proof of an undocumented raw response schema. |
| Per-SKU bundle `/v1/supply-order/bundle` | Documented wrapper, strict parser, bounded pagination, durable scoped observations, and owner selection implemented in FB22. | Exact documented composition schema is exercised synthetically; shipment, acceptance, raw state coverage, actual dispatch date, and historical completeness remain **NOT_VERIFIED**. |
| Acceptance acts | Existing act normalizer/reconciler is reused in tests for cumulative snapshots, multiple acts, explicit zero vs missing, partial reads, and downward-correction review. | New automatic batch collection does not acquire or publish acts yet. Act creation/capture dates do not prove physical receipt time. |
| Full inventory movement / R1 | No supported complete movement source has been established by this PR. | A complete supply manifest cannot satisfy R1 or factual FIFO apply readiness. |

The nested `supplies[].state` raw-to-normalized mapping is deliberately not promoted to an Ozon-supported profile: `DATA_FILLING`/`READY_TO_SUPPLY` map to `DECLARED`; `ACCEPTED_AT_SUPPLY_WAREHOUSE` to `AT_DROPOFF`; `IN_TRANSIT` to `IN_TRANSIT`; `ACCEPTANCE_AT_STORAGE_WAREHOUSE` to `RECEIVING`; `COMPLETED` to `ACCEPTED`; `CANCELLED` to `CANCELLED`. Any unrecognized raw nested state stays unsupported. The source service also carries `FIFO_BATCH_SUPPLY_STATE_PROFILE_UNVERIFIED`, so documented parent-order states do not by themselves establish complete Ozon supply coverage.

## FB16 — owner/API supply deduplication boundary

`FifoCostBatchSupplyDeduplicator` is a pure linker over typed, already-normalized evidence. One canonical record is keyed by exact owner/store/product/offer/SKU scope plus the opaque supply digest. Seller API observations retain their `OZON_API` provenance, owner declarations retain `OWNER_INPUT` provenance and declaration revisions, and matching values are compared rather than summed. ORDER declarations remain separate parent controls; if child supplies are not linked, the control stays unresolved or unverifiable and never becomes an extra supply.

The layer deduplicates repeated observations by source fingerprint, uses the latest captured content only for a stable canonical supply identity, and preserves cumulative accepted quantity without treating a repeated older snapshot as a new decrease. A novel decrease, fingerprint/content conflict, mapping conflict, wrong scope, declared-versus-shipped quantity conflict, or proven dispatch-date conflict requires review. An `API_ONLY` or `OWNER_ONLY` record is not evidence that the source set is complete. This result is not a scan-coverage or readiness claim; FB17 owns totals and coverage. No rows are persisted and no FIFO/accounting state is changed.

## FB17 — manifest totals and dated controls

`FifoCostBatchManifestBuilder` is a pure consumer of the exact transition case, confirmed rule, scan coverage, FB16 deduplication result, current membership classifications, and typed dated controls. It returns separate found composition, included shipped composition, accepted, pending, and planned quantities. An incomplete accepted set is not exposed as a complete `accepted_units`; the known accepted subtotal and missing count remain partial evidence. A planned quantity is never included in shipped or accepted totals. Empty input reports `UNKNOWN` and carries `FIFO_BATCH_SOURCE_EMPTY_NOT_ZERO`, rather than making a zero claim.

A dated owner control is compared only when its measurement kind and both inclusive dates exactly match the scan request. A different window is returned as `WINDOW_NOT_COMPARABLE`, not applied as a permanent cap. The legacy transition-case total is returned separately as `UNBOUNDED_LEGACY_CONTROL`, with no inferred date and no influence on automatic totals. The frozen manifest currently has one inline control slot; multiple exact-window controls are retained in the build result but prevent a CURRENT manifest until the contract can seal all of them. `current_through` uses only `source_as_of`; capture time and act date never establish dispatch or physical receipt. FB17 has no persistence, production source publishing, readiness wiring, or FIFO/COGS side effect.

## FB18 — negative source and evidence regressions

The linked synthetic profile verifies unavailable list access stays partial and does not leak the client error or raw payload; no source scan/observation staging rows or FIFO event/layer/allocation rows are written for that failure. Empty act evidence remains `None`, distinct from a documented zero; incomplete SKU composition remains incomplete; an unverified raw state is unsupported rather than defaulted. Bool/invalid quantities and aggregate overflow fail closed. Duplicate page keys, repeated cursors, overlapping mutable pages, and source-profile changes cannot establish current complete coverage. Existing checkpoint tests cover resume/restart and exact binding. These checks do not verify Ozon's raw bundle schema, state enum, cursor semantics, or actual dispatch-time source; successful transport remains insufficient for production-complete coverage.

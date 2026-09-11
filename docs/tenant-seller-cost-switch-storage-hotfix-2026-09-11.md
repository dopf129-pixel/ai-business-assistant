# Tenant seller cost switch storage hotfix — 2026-09-11

## Scope

This reconciliation records the production fix for the Telegram seller-cost flow where selecting article `hook-2` (SKU `3921245627`) and entering cost `21` returned `Не удалось сохранить новую себестоимость. Изменений не применено.`

Ozon remains strictly READ-ONLY. The change only affects local seller cost persistence.

## Root cause

`PeriodProfitEffectiveCostService` was constructed during application startup before a Telegram request had bound a tenant. At that time `product_cost_switch_history` was initialized in the non-tenant database.

After multi-tenant storage isolation, request-time `get_connection()` resolves to the tenant-local `ozon_assistant.db`. Its base cost schema initialized `product_costs` and `product_cost_history`, but not `product_cost_switch_history`. Therefore `record_cost_switch()` attempted to insert into a table that did not exist in the active tenant database and failed closed as `PRODUCT_COST_SWITCH_STORAGE_UNAVAILABLE`.

The pre-existing seller-cost unit test used one fixed temporary database for both service construction and request execution, so it could not reproduce the startup-without-tenant / request-with-tenant boundary.

## Production fix

Production main `acce332a5d35db9f1f574df96ea4f0f249192bec` initializes `product_cost_switch_history` and its SKU/offer effective-date indexes as part of the tenant-local cost schema setup. Every tenant cost connection can therefore create the switch schema in the same database that receives the write.

A regression test reproduces the production sequence:

1. construct `PeriodProfitEffectiveCostService` before tenant binding;
2. bind a Telegram tenant;
3. select article `hook-2`, SKU `3921245627`;
4. enter cost `21`;
5. assert local persistence succeeds with effective date `2026-09-12` when the confirmation date is `2026-09-11`;
6. assert the saved row exists in that tenant's `product_cost_switch_history`;
7. assert the seller-facing result remains `read_only_ozon = True`.

No Ozon write API is introduced or called by this flow.

## Verification evidence

Feature head `4d3c66403b9ea684f73365e99a672a8435a905b0`:

- Verify run `34589831193`: `completed` / `success`;
- artifact `verification-4d3c66403b9ea684f73365e99a672a8435a905b0`;
- digest `sha256:6dc9558105a28c39d83deb0c178c7e00ac5f63e1d25184003ba475a9419d59c9`.

PR #525 synthetic merge `35c4b78be25b2f8d0fcc3ba309a01419e1181fc7`:

- Verify run `34589920953`: `completed` / `success`;
- artifact `verification-35c4b78be25b2f8d0fcc3ba309a01419e1181fc7`;
- digest `sha256:96b38572cdbc33fab2be96da3a76789611c94b4e5a83b078a5f5af3d67b36856`.

Production main `acce332a5d35db9f1f574df96ea4f0f249192bec`:

- Verify run `34590000063`: `completed` / `success`;
- artifact `verification-acce332a5d35db9f1f574df96ea4f0f249192bec`;
- digest `sha256:7a42454b93ad03c15805b2393755b1990c031e3635b7451c1dc2fc102a5c07ae`.

## Preserved invariants

- Ozon remains READ-ONLY; no automatic Ozon write operation is added.
- Seller cost confirmation only writes local tenant storage.
- A new cost becomes effective on the next calendar date, preserving already-accrued same-day history.
- Historical Period Profit authority remains seller-confirmed effective-dated evidence rather than mutable current cost.
- Existing Return COGS, accounting, commit-readiness, and inventory-recovery gates are unchanged.

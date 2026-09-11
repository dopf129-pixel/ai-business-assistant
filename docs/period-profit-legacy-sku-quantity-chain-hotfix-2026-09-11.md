# Period Profit legacy SKU quantity chain hotfix — 2026-09-11

## Scope

Live Telegram Period Profit for `hook-2` failed after historical SKU identity recovery with:

`Данные о количестве проданных товаров недоступны`

The affected identity chain is:

- seller offer: `hook-2`
- historical Ozon finance SKU: `3398133813`
- current Ozon catalog/FBO SKU: `3921245627`
- current seller cost: `21 ₽`

The current `21 ₽` cost must never be applied retroactively to historical sales.

## Root cause

The finance-SKU scope layer already proved that historical finance SKU `3398133813` belongs to the stable `hook-2` product through READ-ONLY posting identity evidence. The next sale-quantity layer nevertheless discarded that stable identity and reconciled physical quantity only by exact `(posting_number, sku)`.

Ozon finance can retain the retired SKU while current FBO posting evidence exposes the replacement SKU. Therefore the exact legacy-SKU lookup failed even after the product itself had been identified correctly.

## Production fix

`PeriodProfitEffectiveCostSaleQuantitySummaryService` now keeps distinct responsibilities through the chain:

1. finance SKU remains the monetary scope key used for historical Ozon finance;
2. stable `product_id` / `offer_id` proven by the SKU-scope layer is preserved into the physical-quantity stage;
3. quantity evidence prefers exact finance-SKU matching, then accepts the same exact posting matched by the already-proven stable seller `offer_id`;
4. exact posting-detail fallback uses the same stable identity rules;
5. duplicate or conflicting identity evidence fails closed;
6. dated seller-confirmed historical/effective cost remains the only COGS authority for each historical sale date.

No current mutable cost is used as historical authority.

## Regression coverage

The regression test reproduces the live identity split:

- finance sale record uses SKU `3398133813`;
- current FBO posting uses SKU `3921245627` and offer `hook-2`;
- quantity is greater than one;
- the same posting contains an unrelated second product;
- historical cost differs from the current `21 ₽` value;
- the calculation uses the dated historical cost and the correct physical quantity;
- duplicate offer identity within a posting remains fail-closed.

Existing full-suite coverage continues to exercise reaccrual handling, effective-cost timelines, return COGS evidence/accounting, authorization, recognition, commit integrity, inventory recovery, and Ozon FBO v3 cursor pagination.

## Ozon safety

Ozon remains strictly READ-ONLY. This change adds no Ozon write endpoint and does not weaken return/accounting gates.

## Verification evidence

### Feature head

- SHA: `11067edf975293baf908aec70b2aebedf5a7ea24`
- Verify run: `34612513818`
- result: success
- artifact: `verification-11067edf975293baf908aec70b2aebedf5a7ea24`
- digest: `sha256:fd7a58b6cdb8415ff72c1b021154042ccf7cdef39caf630d1dccdd47082604e1`

### Production PR synthetic merge

- PR: `#533`
- synthetic merge SHA: `29c240e76dfd13b3e86141422e2cbdbf38a2cad8`
- Verify run: `34612609122`
- result: success
- artifact: `verification-29c240e76dfd13b3e86141422e2cbdbf38a2cad8`
- digest: `sha256:1e2d3d4bcb3eef98227f685d446eddb345011fc2d7520b3fc9bb8a1cfa3b9557`

### Production main

- squash-merge SHA: `b13d261d5dc5cf55e29a9bd05fd66373033134c2`
- Verify run: `34612705092`
- result: success
- artifact: `verification-b13d261d5dc5cf55e29a9bd05fd66373033134c2`
- digest: `sha256:26586f89aaf6947db73ccfa2daf6136ae973b39b7d822ad79f6331dbaaf2f6d4`

## Invariants

- Ozon access remains READ-ONLY.
- Historical finance identity and current catalog identity are not treated as interchangeable SKUs.
- Stable product/offer identity may bridge an Ozon SKU replacement only when already proven by exact posting evidence.
- Ambiguous identity or quantity evidence fails closed.
- Historical COGS requires dated seller-confirmed evidence.
- Current cost `21 ₽` is not backfilled into dates before its effective date.
- Return COGS accounting, recognition, application authorization, commit integrity, and inventory-recovery gates are unchanged.

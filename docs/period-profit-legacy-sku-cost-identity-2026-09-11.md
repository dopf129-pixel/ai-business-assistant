# Period Profit legacy SKU historical cost identity fix — 2026-09-11

## Scope

The live Telegram Period Profit flow failed closed with:

`Не найдена подтвержденная себестоимость для SKU из финансов Ozon: 3398133813`

The affected seller offer is `hook-2`. Ozon finance still references retired SKU `3398133813`, while the current Ozon catalog exposes SKU `3921245627` for that offer.

## Root cause

`PeriodProfitFinanceSkuScopeService` scoped the calculation to SKUs present in Ozon finance. When a finance SKU was absent from the current catalog, its recovery path only searched cost evidence by the exact SKU. That was correct for preventing accidental cost substitution but could not bridge a legitimate Ozon SKU replacement for the same seller offer.

The effective-cost layer already has the safer authority model required for historical profit: dated operational cost switches and seller-confirmed bounded cost history. Current mutable cost is not historical authority.

## Production fix

Production PR #529 adds an identity-only recovery adapter for missing finance SKUs.

The recovery sequence is:

1. Keep direct exact-SKU recovery as the first choice.
2. If it fails, read FBO posting evidence through the existing READ-ONLY Ozon client for the requested period plus a bounded evidence window.
3. Require the historical finance SKU to resolve to exactly one FBO `offer_id`.
4. Require that `offer_id` to resolve to exactly one current catalog `product_id`.
5. Preserve the historical finance SKU in the scoped row while carrying the proven stable `offer_id` and `product_id` identity into downstream calculation.
6. Do not inject `cost` or `cost_price` during identity recovery.
7. Let the existing effective-cost reconciler resolve seller-confirmed cost evidence independently for every sale date.

For the exact regression, this allows the historical finance SKU `3398133813` to be recognized as the same stable seller offer `hook-2` now exposed as SKU `3921245627`, without treating the current SKU or current cost as historical evidence.

## Safety and fail-closed behavior

The current `21 ₽` seller cost is **not** copied backward into historical periods. Its existing effective-date semantics remain unchanged.

If the FBO evidence maps the legacy SKU to multiple offers, omits `offer_id`, cannot be read completely enough to prove identity, or the offer maps ambiguously in the current catalog, Period Profit still fails closed.

Even after identity recovery, if a requested historical sale date has no seller-confirmed bounded cost history or effective operational cost switch, the dated effective-cost reconciler remains responsible for rejecting the calculation. Identity recovery does not weaken historical cost authority.

Ozon remains strictly READ-ONLY. No Ozon write endpoint or mutation capability was added.

Return COGS accounting attribution, readiness, recognition eligibility, accounting recognition, profit-application authorization, commit readiness, commit integrity, final application, final integrity, and inventory-recovery gates are unchanged.

## Regression coverage

`app/tests/test_period_profit_legacy_sku_identity_recovery.py` covers:

- the exact live identity transition `3398133813` → `hook-2` → current SKU `3921245627`;
- successful recovery of stable `product_id` and `offer_id` without injecting a historical cost;
- conflicting historical offer identity staying fail-closed;
- missing seller-known product cost identity staying fail-closed.

The full existing test suite, production Docker build, and production runtime smoke checks also remain green.

## Verification evidence

Feature head:

- SHA: `3d586eec062ac8d72c045d9d23976954767565ec`
- Verify run: `34593735306`
- artifact: `verification-3d586eec062ac8d72c045d9d23976954767565ec`
- digest: `sha256:b4b999b80b82c79fdb8c07ae0ffddd1a2d69006b189613b633799e8bf36d743f`

Production PR #529 synthetic merge:

- synthetic SHA: `c5a3282c1e5427df8573c189eaf4b81a894e9b15`
- Verify run: `34593803431`
- artifact: `verification-c5a3282c1e5427df8573c189eaf4b81a894e9b15`
- digest: `sha256:3e6c8a00e1f495f0d409a300fb016d31c9cb6a35a402354aa5ef9d4d4b371b10`

Production main after squash merge:

- SHA: `df28ac12663e4c56b116f508219dcf601b2f7e9b`
- Verify run: `34593903832`
- artifact: `verification-df28ac12663e4c56b116f508219dcf601b2f7e9b`
- digest: `sha256:f650148c1e660356c308d60736ccc6e2323a31c2267037eeeb27d35b1a07dbf1`

## Operational expectation

After updating and restarting the bot, requesting Period Profit for a range containing finance records under legacy SKU `3398133813` should no longer stop at the catalog/cost identity coverage gate when Ozon READ-ONLY FBO evidence proves the same stable `hook-2` offer.

Historical profit will only be produced when the separate dated effective-cost evidence gate is also satisfied. If historical seller-confirmed cost evidence is genuinely absent, the bot must continue to fail closed rather than estimate past COGS using the current `21 ₽` value.

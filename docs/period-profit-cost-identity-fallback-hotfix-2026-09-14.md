# Period Profit historical cost identity fallback hotfix — 2026-09-14

## Live blocker

Period Profit failed closed with:

`Не найдена подтвержденная себестоимость для SKU из финансов Ozon: 3398133813`

The affected live product identity is:

- stable seller offer: `hook-2`
- legacy finance SKU: `3398133813`
- current SKU: `3921245627`
- current seller-confirmed cost: `21.00 RUB`

The historical finance event can carry the old SKU while the current Ozon product id/SKU has already changed.

## Root cause

`PeriodProfitEffectiveCostService.get_effective_cost_evidence()` received all known identities at once. The resolver gave `product_id` precedence. If the current product id did not exist in historical cost storage, the lookup returned missing and never retried the stable seller `offer_id`.

That made valid bounded historical seller-cost evidence unreachable after an Ozon identity transition.

## Fix

Period Profit now resolves evidence in ordered identity strength:

1. `product_id`
2. `offer_id`
3. `sku`

Fallback occurs only when the stronger identity is genuinely missing. Ambiguous, unavailable, unbounded, or not-effective evidence still fails closed and is never bypassed by a weaker identifier.

Every candidate is evaluated against the original historical sale date. The later current cost (`21.00 RUB`) is not retroactively substituted into older sales.

## Regression coverage

`app/tests/test_period_profit_effective_cost_identity_fallback.py` covers the live identity shape:

- historical bounded cost stored under a legacy product id, finance SKU `3398133813`, and offer `hook-2`;
- later current switch under a new product id, current SKU `3921245627`, offer `hook-2`, cost `21.00`;
- historical query starts with the current product id plus legacy finance SKU;
- resolver falls back through `hook-2` and returns the bounded historical cost, not `21.00`;
- a stronger identity with an explicit not-effective historical timeline does not fall through, preserving fail-closed semantics.

## Safety invariants

- Ozon remains strictly READ-ONLY.
- No Ozon write endpoint was added or changed.
- Mutable current cost rows remain non-authoritative for historical Period Profit.
- Historical date bounds, ambiguity checks, and accounting evidence gates remain fail closed.

## Verification evidence

### Feature branch

- branch: `fix/period-profit-cost-identity-fallback`
- head: `2e62495454552797f052f48595af8fc11dbef6e5`
- Verify run: `34786018790` — success
- artifact: `verification-2e62495454552797f052f48595af8fc11dbef6e5`
- digest: `sha256:ccb0ceac387288530d6eb8a4068bc5f6dbb69a44aeb6778a496d0e2cc6037395`

### Production PR #535 synthetic merge

- synthetic merge SHA: `76d400a62fbb0529d6be84e12603abf2ea1114cd`
- Verify run: `34786103569` — success
- artifact: `verification-76d400a62fbb0529d6be84e12603abf2ea1114cd`
- digest: `sha256:afbbc06411a98c776359c6e7bd65a8409f217107a0c95bf79a7b7daa1616dff2`

### Production main after squash merge

- main SHA: `f54672ae8cb161ac05240099cc21ebbdad241c75`
- Verify run: `34786159697` — success
- artifact: `verification-f54672ae8cb161ac05240099cc21ebbdad241c75`
- digest: `sha256:5f8ae11280358c43512c50182c0e1aad0b0e46b4d1c00a3c7fd1f90f5616a8fe`

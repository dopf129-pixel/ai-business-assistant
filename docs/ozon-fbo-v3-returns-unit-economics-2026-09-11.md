# Ozon FBO v3 returns unit-economics hotfix — 2026-09-11

## Symptom

Telegram unit economics for `hook-2` could resolve current price, fees, tax, and seller-confirmed cost, but rendered `Возвраты и невыкупы: —` and intentionally suppressed estimated profit with `Данные возвратов недоступны; прибыль не рассчитана.`

## Root cause

The returns/buyout facts flow depends on the READ-ONLY FBO posting list. The runtime Ozon facade still inherited the legacy `/v2/posting/fbo/list` implementation. Ozon retired that endpoint on 2026-08-31 in favor of `/v3/posting/fbo/list`. The replacement endpoint uses cursor pagination and returns `postings` at the top level, so the old request failed and the analytics source correctly failed closed.

## Production fix

PR #527 (`7b1acbc7b8157b93bd1f18e2f9798bba4c629d4d`) overrides FBO listing in the tenant-aware Ozon facade to:

- call `POST /v3/posting/fbo/list` only;
- follow the v3 cursor contract;
- cap each wire request to the v3 page size;
- preserve the existing analytics-facing offset window and `result.postings` response shape;
- fail closed on malformed responses, repeated/missing cursors, invalid sort/pagination input, or page-limit exhaustion;
- keep the operation explicitly READ-ONLY.

No Ozon mutation endpoint was added or enabled.

## Regression coverage

`app/tests/test_ozon_fbo_v3_returns_unit_economics.py` covers:

- v3 endpoint/payload and cursor progression;
- absence of legacy `offset` / `dir` fields on the Ozon wire request;
- normalization to the existing analytics response contract;
- exact `hook-2` / SKU `3921245627` returns-facts path;
- cancellation classification from FBO cancel-reason evidence;
- repeated cursor fail-closed behavior.

## Verification

Feature head `5b442df3d4d4d39d9c38ecf3f439467b769cc459` passed Verify run `34592069935` with artifact `verification-5b442df3d4d4d39d9c38ecf3f439467b769cc459` and digest `sha256:4fa66e4226a201e9690010a4a056c2e1f0859d4189d2010aaf2e5fc841ed9f9b`.

PR #527 synthetic merge Verify run `34592152607` passed with artifact `verification-ad5883b02b2ee284a23204cab9dafb63f3753256` and digest `sha256:547073109df1feb86f5d4b4914e9e24a3e27186939708baab154ace2a56e94c3`.

Production main `7b1acbc7b8157b93bd1f18e2f9798bba4c629d4d` passed Verify run `34592215558` with artifact `verification-7b1acbc7b8157b93bd1f18e2f9798bba4c629d4d` and digest `sha256:d814d0520097728000d93fce2212ec04fed0cd777492eb91adf89647c51121e8`.

## Preserved invariants

- Ozon remains READ-ONLY.
- Seller-confirmed cost persistence and next-calendar-date activation are unchanged.
- Return COGS accounting, authorization, commit, recognition, and inventory-recovery gates are unchanged.
- Returns analytics continues to fail closed when evidence is incomplete or unavailable; this hotfix restores the retired transport dependency rather than weakening evidence requirements.

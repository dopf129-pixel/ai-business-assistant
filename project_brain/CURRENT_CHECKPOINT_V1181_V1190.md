# CURRENT_CHECKPOINT_V1181_V1190

Date: 2026-09-03

## Tax Policy Production Availability

Production package:

`v1181-v1190: Tax Policy Production Availability`

Goal:

Restore validated production tax-policy availability for current Telegram unit economics so clean deployments can calculate tax and base unit profit without weakening unknown-tax fail-closed semantics.

## Root cause

`TaxConfigurationService` defaults to `data/tax_configuration.json`, but the repository did not contain this file.

As a result, a clean deployment returned an unconfigured tax policy even though Project Brain had already validated production USN Income 6%. Current unit economics therefore showed `Налог: —` and withheld base profit.

## Verified behavior

- repository production policy is explicit `USN_INCOME / 6%`;
- default Telegram core receives that policy;
- if the persisted file is genuinely absent, an explicitly configured environment policy may be used;
- env fallback requires a real `TAX_MODE`; config defaults are not treated as evidence;
- invalid env policy fails closed;
- persisted policy takes precedence over env;
- malformed persisted policy does not silently fall back to env;
- missing tax policy still remains unknown rather than zero;
- hook-2-like current economics at 100 ₽ calculates tax 6.00 ₽;
- hook-2-like base net profit before return-risk adjustment is 35.83 ₽.

## Seller-facing evidence boundary

Returns/non-buyout evidence is separate from tax availability.

A known tax and known base unit profit do not authorize pretending missing return cost is zero. Telegram should distinguish:

- base profit before return-risk adjustment;
- confirmed or estimated return-adjusted profit when sufficient evidence exists.

That presentation refinement is the next concrete seller-facing gap.

## Product boundary

Decision 036 remains active and unchanged.

AI Business Assistant is a read-only Ozon analyst and advisor.

No Ozon mutation or execution capability is introduced.

## SHA-bound verification evidence

- entering exact main `8ca28c36249a052fdf83cfd5ab86a13d986cbb1c`: Verify #896, 2081 passed / 0 failed, artifact 9884443694, digest `sha256:a5d997dde52609adc1511d794a654e5af5d30dfdad1193bb4398d9c5f11117e3`;
- final feature `1d0df2799fb87b57d916843a96a080389e2ac07b`: Verify #900, 2091 passed / 0 failed, artifact 9884824274, digest `sha256:8a54d841f9b6b18c7e0184365da0995bee4b09c57ffffe464acb17df41c6f0b0`;
- PR #373 synthetic `a6493407f0bb915f366573404fcffd220e6757a1`: Verify #901, 2091 passed / 0 failed, artifact 9884854745, digest `sha256:3327e51b96a4c4ad376e21f524b578caa6709d20336b52c430adef277603f8b0`;
- squash main `9c9d379e36edf2123a466ad2b3cd1d000d81bae3`: Verify #902, 2091 passed / 0 failed, artifact 9884888892, digest `sha256:f50357c3d1ef309fc7be702b6807406677a733fe7a5102aff67b3c7405676d60`;
- no failed production SHA occurred in this package.

GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.

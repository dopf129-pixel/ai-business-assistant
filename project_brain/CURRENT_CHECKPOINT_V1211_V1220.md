# CURRENT_CHECKPOINT_V1211_V1220

Date: 2026-09-03

## Period Profit Tax Rate Unit Integrity

Production package:

`v1211-v1220: Period Profit Tax Rate Unit Integrity`

Goal:

Fix the live Period Profit result where a 6% tax policy was applied as multiplier 6.0 rather than fraction 0.06.

## Root cause

TaxConfigurationService stores tax rates in percentage units:

`6.0 = 6%`

PeriodProfitSummaryService historically expects a fractional multiplier:

`0.06 = 6%`

The production Period Profit factory passed the percentage value without conversion.

## Verified behavior

- production Period Profit reads validated tax policy through TaxConfigurationService;
- `USN_INCOME 6.0%` converts to `0.06`;
- `NONE` converts to `0.0`;
- unsupported tax modes fail closed;
- invalid and non-finite rates fail closed;
- PeriodProfitSummaryService rejects tax multipliers above `1.0`;
- seller live sample regression:
  - revenue 1 348 371.10 ₽;
  - net Ozon accrual 752 971.82 ₽;
  - product cost 361 368.00 ₽;
  - tax 80 902.27 ₽;
  - operational profit 310 701.55 ₽;
  - margin 23.04%.

## Product boundary

Decision 036 remains active and unchanged.

No Ozon mutation, execution permission, return-cost inference or advertising/storage inference is introduced.

## SHA-bound verification

- entering exact main `590b068ef46f58e56509ac038759f465975c9a8a`: Verify #949, 2111 passed / 0 failed, artifact 9886812170, digest `sha256:83cdf8fe62a670cacee5ab69cf07e2baaab324d7c6437d3c65175d3dc6102bf5`;
- failed `a7d5cead4c7c49907d6d045b54a3cec30d48efad`: Verify #953, 2110 passed / 1 failed, artifact 9887077119, digest `sha256:51184585e794907d4c730305e2af0cfb98e895ed6153babb75ec997a803c0809`;
- failed `ee463cd1000113998ae5b895da02334bb5a5f495`: Verify #954, 2120 passed / 1 failed, artifact 9887087702, digest `sha256:118d2dad053f08adabe6605aa1790a2600628b9a9ece50c53b62f012ac2e0689`;
- final feature `4c50429bc4c2f6515d80b497b85fe8c9663e24eb`: Verify #955, 2121 passed / 0 failed, artifact 9887122511, digest `sha256:ea8eeeb352ab0309dda2fca54573b6211c052dbbf51996699084edfc68811a58`;
- PR #379 synthetic `68c0f7360dd93738377f7111f5f4732d0b4d48af`: Verify #956, 2121 passed / 0 failed, artifact 9887163034, digest `sha256:5f6b8d4487c21eee14d87b245881dfe8686ac4467514b84e750da4851cb81f69`;
- squash main `2f438bd6bb739938cee4fe56b83af8f4a563f942`: Verify #957, 2121 passed / 0 failed, artifact 9887195049, digest `sha256:414836b82a65d5a73a08ad2622e5b7b579262361319c384272f0863cbd45b976`.

Failed SHA evidence is not transferable.

## Next seller-requested package

Add percent-of-revenue in parentheses to every monetary Period Profit line.

Expected presentation pattern:

- Revenue: amount (100.00%);
- Ozon net accrual: amount (share of revenue);
- Commission / logistics / acquiring / other fees: amount (share of revenue);
- Product cost: amount (share of revenue);
- Tax: amount (share of revenue);
- Profit: amount (share of revenue).

When revenue is zero, percentages must be omitted rather than invented.

GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.

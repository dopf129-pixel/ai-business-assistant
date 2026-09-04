# Verification Status

Date: 2026-09-04

## Latest verified product baseline

`767b3e99d4439d1cbbe7b441a19914a366e62e22`

Package: `v1381-v1390: Final Period Profit Application`

### Failed intermediate evidence

- SHA `f6e9d9af0e93dec0f9d425b6666f99f2d736d0ca` — Verify #1230 failed;
- this SHA remains failed permanently and receives no transferred success claim.

### Exact feature head

- SHA `986d9ffed2b348890a57bac37362388d08be8780`;
- Verify #1233 succeeded;
- artifact `9940720378`;
- digest `sha256:03e7d16f62eee2af88130b68f09952e4549098eff7f086bd11f69c75a943fe71`.

### PR integration checkout

- PR #413;
- synthetic merge SHA `8ac09b60672bd4f8823547d542f274a4cf609d13`;
- Verify #1234 succeeded;
- artifact `9940750283`;
- digest `sha256:730d36be4d902331838213dc6464a5ca7a3c7b22aa2eeb2d422c4af40fde6697`;
- artifact name is SHA-bound to the synthetic merge revision.

### Exact production main

- squash SHA `767b3e99d4439d1cbbe7b441a19914a366e62e22`;
- Verify #1235 succeeded;
- artifact `9940791251`;
- digest `sha256:c9f3a9e84c37cb9792dec169d3ca50632784d54ecdd9837b4c891f1b6d1d4b9b`;
- artifact name is SHA-bound to exact main.

## Current Period Profit boundary

Seller-facing Period Profit may now consume Return COGS only from an exact durable commit whose recognition/application eligibility remains valid at query time. The adjustment is read-only and recomputed from the unadjusted account summary on every query, so repeated reads do not accumulate the same recovery twice.

Missing or uncommitted Return COGS remains unapplied with monetary adjustment `None`; unknown is not zero.

Tax is explicit for all supported configured modes: `NONE`, `USN_INCOME`, and `USN_INCOME_MINUS_EXPENSES`. Revenue tax remains revenue-based for `USN_INCOME`; income-minus-expenses tax is recalculated after committed Return COGS and still applies the configured minimum revenue tax.

The response text is rebuilt after final application, so the Telegram Period Profit runtime receives the final seller-facing summary.

## Verification policy

Exact branch verification proves only that branch head. PR verification proves only the synthetic integration checkout. Every squash-main SHA requires its own exact verification. Failed SHAs remain failed permanently. Missing evidence is unknown, not zero. Ozon mutation remains prohibited. `externally_verified=False`.

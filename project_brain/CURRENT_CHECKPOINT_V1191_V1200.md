# CURRENT_CHECKPOINT_V1191_V1200

Date: 2026-09-03

## Period Profit Returns Protobuf Timestamp Compatibility

Production package:

`v1191-v1200: Period Profit Returns Protobuf Timestamp Compatibility`

Goal:

Fix live Period Profit failure caused by sending date-only values to Ozon Returns API protobuf Timestamp fields.

## Root cause

Period Profit loads read-only return evidence through `POST /v1/returns/list`.

The filter `visual_status_change_moment.time_from/time_to` received values such as `2026-09-03`, while Ozon requires RFC3339/protobuf Timestamp values.

## Verified behavior

- date-only start normalizes to `YYYY-MM-DDT00:00:00Z`;
- date-only end normalizes to `YYYY-MM-DDT23:59:59.999999999Z`;
- the full requested final calendar day remains included;
- existing RFC3339 timestamps remain unchanged;
- custom Period Profit ranges use normalized Returns API timestamps;
- preset Period Profit ranges use normalized Returns API timestamps;
- Returns API filter, pagination and timeout behavior remain unchanged;
- return evidence remains descriptive/read-only;
- `financial_impact_supported=False`;
- `returns_profit_adjustment_allowed=False`;
- `executed=False`.

## Product boundary

Decision 036 remains active and unchanged.

AI Business Assistant remains a read-only Ozon analyst and advisor.

No Ozon mutation or execution capability is introduced.

## SHA-bound verification evidence

- entering exact main `d3f32e2ca2e30192a59c4551cf5633dfa0941ec6`: Verify #912, 2091 passed / 0 failed, artifact 9885058169, digest `sha256:bf3cdceb80d889184a9e856b301cc6cf17a4dabe0a74b7f27402be987a4b8071`;
- final feature `9e2c5b27a1df9f32c8e950766abc809ba93f7976`: Verify #918, 2101 passed / 0 failed, artifact 9885588430, digest `sha256:b4d51f1a5df4889e9f068732ed744a98660ae15fb45900827acb1679990e2e6c`;
- PR #375 synthetic `86bc4a07477e910fcaf56a1a1b908fa28a4a68f5`: Verify #919, 2101 passed / 0 failed, artifact 9885621112, digest `sha256:10cb2f8e871457a75fcd666b4f873c6fc45746d5efe95f463d93ac9f18d07973`;
- squash main `c1c3da7cb69d6ce2af550e57bc6c5e38a0bb8a89`: Verify #920, 2101 passed / 0 failed, artifact 9885660481, digest `sha256:bc16fce014476d23c6ead3d2435b199ae2ce48af108dfa64501eed3ba82c7dc6`;
- no failed production SHA occurred.

GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.

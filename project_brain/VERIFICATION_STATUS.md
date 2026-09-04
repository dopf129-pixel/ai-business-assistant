# Verification Status

Date: 2026-09-04

## Latest verified product baseline

`9d8824d3847ed80575f0b7ac126316dff77b42d9`

Package: `v1371-v1380: Return COGS Profit Application Commit Readiness`

### Exact feature head

- SHA `481ec0830163b2dee965afd58bd72fd9f52c6dea`;
- Verify #1214;
- full-verification succeeded.

### PR integration checkout

- PR #411;
- synthetic merge SHA `460ba8512b755306b3d4b5cdd84c49e4bc233a23`;
- Verify #1215 succeeded;
- artifact `9939537819`;
- digest `sha256:15cd33a80d92c63e442526f2d63afddd0efedab2cbc64e4a60ed75ca54bd98cd`;
- artifact name is SHA-bound to the synthetic merge revision.

### Exact production main

- squash SHA `9d8824d3847ed80575f0b7ac126316dff77b42d9`;
- Verify #1216 succeeded;
- artifact `9939566781`;
- digest `sha256:a596fff205f62f924a1d22fda1cfca5d7bd85a04ceb7462fe8b1846794169aa2`;
- artifact name is SHA-bound to exact main.

## Current accounting boundary

The application-eligibility package remains authoritative for no-double-count proof. v1371-v1380 adds a separate exact-once commit-readiness layer and append-only commit ledger.

A commit is keyed by exact `recognition_history_id`, binds the exact Return COGS identity, accounting date, RUB amount and authorization-history version, and is first-writer-wins. UPDATE and DELETE are prohibited.

Even confirmed commit evidence does not change seller-facing Period Profit. `return_cogs_profit_applied=False`, `return_cogs_profit_application_amount=None`, `profit_adjustment_allowed=False`, and `automatic_recovery_allowed=False` remain required.

## Verification policy

Exact branch verification proves only that branch head. PR verification proves only the synthetic integration checkout. Every squash-main SHA requires its own exact verification. Failed SHAs remain failed permanently. Missing evidence is unknown, not zero. Ozon mutation remains prohibited. `externally_verified=False`.

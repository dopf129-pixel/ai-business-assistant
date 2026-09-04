# Current Checkpoint v1321-v1330

Date: 2026-09-04

Package: `Return COGS Accounting Readiness`

## Status

Production lifecycle complete and exact-main verified.

Exact production main:

`ea92d314b81b80878d5127ed261b448b7cf7abd0`

GitHub Actions push Verify #1168: 2238 passed / 0 failed.

## Entering baseline

Exact docs-reconciled predecessor:

`54a38e4650d5c6952c202b6ca866892ecc20fdc6`

No verification evidence is transferred between SHAs.

## Objective

Promote independently proven Return COGS source evidence into an explicit accounting-readiness contract without yet creating a monetary recovery amount or changing Period Profit.

## Readiness contract

Readiness requires candidates plus all foundation facts:

- complete return sample;
- originating sale period confirmed;
- historical cost basis confirmed;
- saleable inventory recovery confirmed.

It also requires the source-evidence gates introduced by v1301-v1320:

- originating sale quantity evidence confirmed;
- recovery accounting period attributed to the requested period;
- compensation accounting treatment explicitly known;
- compensation double-count clearance true;
- accounting-attribution evidence confirmed.

Only then may `return_cogs_accounting_readiness_confirmed=True`.

## Gate promotion

The new readiness service promotes source evidence to these accounting readiness flags:

- `originating_sale_quantity_confirmed`;
- `originating_sale_quantity_gate_promoted`;
- `recovery_period_attribution_confirmed`;
- `compensation_accounting_treatment_confirmed`.

Missing or ambiguous evidence remains false and receives deterministic readiness blockers.

## Monetary boundary remains closed

This package deliberately keeps:

- `period_cogs_recovery_confirmed=False`;
- `accounting_cogs_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0.0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- `compensation_profit_adjustment_allowed=False`.

No amount is inferred merely because readiness is true.

## Production changes

Added:

- `app/services/period_profit_return_cogs_accounting_readiness_service.py`;
- `tests/test_return_cogs_accounting_readiness_v1321_v1330.py`.

Updated:

- `app/period_profit_factory.py`;
- `tests/test_period_profit_factory.py`.

Production composition now wraps the accounting-attribution evidence service with the readiness service.

## Verification evidence

No failed production SHA occurred in v1321-v1330.

### Exact feature head

- SHA: `137940e12eb9b3671f580b091a26bf45101aee8c`;
- Verify #1166;
- 2238 passed / 0 failed;
- artifact 9932839687;
- digest `sha256:a89bcb223c2f34dbea2e6f47d2b03d45de4bff176bb38c54f1e2883e0d36cd06`.

### Pull-request synthetic integration

- PR #401;
- synthetic SHA: `adc169fc389fda629bd0f923f2ddb05400aa8993`;
- Verify #1167;
- 2238 passed / 0 failed;
- artifact 9933152845;
- digest `sha256:a1db974d7671e94e3c86cb1263da1b96342c20661dc1e1e94349cd5e599cbd59`.

### Exact squash-main

- SHA: `ea92d314b81b80878d5127ed261b448b7cf7abd0`;
- Verify #1168;
- 2238 passed / 0 failed;
- artifact 9933178755;
- digest `sha256:5a0fc7d1f42b4ac4f23af1fa0a89e9279beea45dac4caf72ccd91f4df9df6021`.

## Preserved boundaries

- permanent read-only Ozon boundary;
- account-level Ozon monetary authority;
- external expense coverage contract;
- historical cost evidence contract;
- explicit inventory recovery evidence contract;
- explicit accounting-attribution persistence contract;
- no Period Profit formula change;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Next accounting gap

Construct a candidate-level monetary recovery evidence contract from historical cost and quantity only after accounting readiness is confirmed. Stage that amount separately and keep Period Profit adjustment disabled until amount ownership and no-double-count semantics are explicitly verified.

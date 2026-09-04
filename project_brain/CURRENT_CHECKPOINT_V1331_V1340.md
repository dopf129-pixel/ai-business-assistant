# Current Checkpoint v1331-v1340

Date: 2026-09-04

Package: `Return COGS Recovery Amount Evidence`

## Status

Production lifecycle complete and exact-main verified.

Exact production main:

`2213e693fc1c99dde853e41c6145c227c411a21a`

Verify #1178: 2248 passed / 0 failed.

## Entering baseline

Exact docs-reconciled predecessor:

`6c3836b15d0cc54f258aee1f40d6c36d31126375`

No verification evidence is transferred between SHAs.

## Objective

Stage a deterministic Return COGS monetary evidence amount only after the candidate set passes the complete accounting-readiness contract, without yet recognizing that amount in Period Profit.

## Amount contract

For every accounting-ready candidate:

1. exact `return_id + posting_number + SKU` identity must be present;
2. return quantity must be an explicit positive integer;
3. effective-dated `historical_cost_per_unit` must be explicit, finite and non-negative;
4. existing `candidate_value_at_historical_cost` must be explicit, finite and non-negative;
5. `historical_cost_per_unit * return quantity` must reconcile to the supplied candidate historical value within 0.01 RUB;
6. every candidate must pass or the aggregate amount remains unknown;
7. explicit zero historical cost is a valid zero-value fact;
8. missing or malformed amount evidence is never interpreted as zero.

The confirmed source-evidence field is:

`return_cogs_recovery_amount_evidence_amount`

with basis:

`HISTORICAL_COST_PER_UNIT_X_RETURN_QUANTITY`.

## Recognition remains closed

Even when monetary evidence is confirmed:

- `period_cogs_recovery_confirmed=False`;
- `accounting_cogs_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0.0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- `compensation_profit_adjustment_allowed=False`.

## Production changes

Added:

- `app/services/period_profit_return_cogs_recovery_amount_evidence_service.py`;
- `tests/test_return_cogs_recovery_amount_evidence_v1331_v1340.py`.

Updated:

- `app/period_profit_factory.py`;
- `tests/test_period_profit_factory.py`.

## Verification evidence

No failed production SHA occurred in v1331-v1340.

### Exact feature head

- SHA `fad2903b3b28a2f2edb270d33a0d327ca3fd42d7`;
- Verify #1176;
- 2248 passed / 0 failed;
- artifact 9933505069;
- digest `sha256:3eeeeb6a3b4bd7dffd6b75136bcd5a74cfdcc639ab5336caa1a2ba9b1a9b6b68`.

### PR synthetic integration

- PR #403;
- synthetic SHA `0be4583b0e9248cd7e497e4e3419063abeb7fd19`;
- Verify #1177;
- 2248 passed / 0 failed;
- artifact 9933534778;
- digest `sha256:42d7cecc82a0278e6238f8a21f766b545f5395ce7e61dd54e62219cbb237c7b9`.

### Exact squash-main

- SHA `2213e693fc1c99dde853e41c6145c227c411a21a`;
- Verify #1178;
- 2248 passed / 0 failed;
- artifact 9933562627;
- digest `sha256:03d474d8ca625593d52f4cd2943d0ec92e293666a26f9287331e00a10010f216`.

## Preserved boundaries

- permanent read-only Ozon product boundary;
- account-level Ozon monetary authority;
- external expense coverage remains separate;
- historical cost, inventory recovery, quantity, accounting attribution and readiness remain independent prerequisites;
- no Period Profit formula change;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Next accounting gap

Define a separate recognition-eligibility contract for the staged amount. Do not apply the amount to Period Profit until recognition ownership, selected-period scope and no-double-count behavior are explicitly proven at the monetary boundary.

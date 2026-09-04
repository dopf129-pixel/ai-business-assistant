# Current Project State

Date: 2026-09-04

## Product

AI Business Assistant is a read-only Ozon seller analyst and advisor. Decision 036 permanently blocks Ozon business mutations unless explicitly superseded by a future product decision.

## Current checkpoint

`v1321-v1330: Return COGS Accounting Readiness`

Exact production main:

`ea92d314b81b80878d5127ed261b448b7cf7abd0`

Verify #1168: 2238 passed / 0 failed.

See:

- `PROJECT_STATE.md`;
- `project_brain/CURRENT_CHECKPOINT_V1321_V1330.md`;
- `project_brain/VERIFICATION_STATUS.md`.

## Current accounting model

Period Profit keeps account-level Ozon finance as monetary authority:

`period_profit = account_net_accrual - product_cost - configured_tax`

External operating expenses remain a separate evidence-bound adjustment.

Return COGS now has independently established source evidence for sale lineage, historical cost, saleable inventory recovery, originating-sale quantity, recovery accounting date and compensation treatment/double-count clearance.

v1321-v1330 adds an explicit readiness layer. When every prerequisite is proven, quantity, period-attribution and compensation gates may become confirmed and `return_cogs_accounting_readiness_confirmed=True`.

The readiness layer does not yet recognize money. `confirmed_cogs_recovery_amount` remains 0.0 and Period Profit adjustment remains disabled.

## Safety boundaries

- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- unknown evidence never becomes zero/clean;
- account-level Ozon monetary operations are never subtracted twice;
- compensation is never inferred from missing operational markers;
- accounting recognition date is never inferred from evidence confirmation date;
- current stock or stock delta never proves inventory recovery;
- historical cost is never backfilled from current cost;
- failed SHA evidence remains failed permanently;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Next development target

Define a candidate-level Return COGS monetary recovery evidence contract from already-ready accounting candidates. The next package should stage a recoverable amount from explicit historical cost and candidate quantity, prove period ownership and no-double-count semantics, and keep Period Profit adjustment disabled until a later explicit recognition contract.

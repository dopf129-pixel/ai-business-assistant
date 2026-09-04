# Current Checkpoint v1371-v1380

## Scope

This package closes the race/repeat gap between Return COGS profit-application eligibility and any future seller-facing application.

## Added boundary

`ReturnCogsProfitApplicationCommitRepository` provides an append-only exact-once commitment ledger.

Key rules:

- one commit per exact `recognition_history_id`;
- first writer wins under `BEGIN IMMEDIATE`;
- later writers receive the existing committed evidence;
- UPDATE and DELETE are prohibited;
- commit evidence binds `return_id + posting_number + sku`, accounting date, RUB amount and exact `authorization_history_id`;
- malformed or unavailable evidence fails closed.

`PeriodProfitReturnCogsApplicationCommitReadinessService` wraps application eligibility and exposes whether exact commit evidence is absent, confirmed, or conflicting.

## Non-application guarantee

The package does not consume the committed amount in Period Profit. It preserves:

- `return_cogs_profit_applied=False`;
- `return_cogs_profit_application_amount=None`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- `read_only=True`;
- `executed=False`.

Canonical formula remains:

`period_profit = account_net_accrual - product_cost - configured_tax`

## Verification

- feature `481ec0830163b2dee965afd58bd72fd9f52c6dea` — Verify #1214 succeeded;
- PR #411 synthetic merge `460ba8512b755306b3d4b5cdd84c49e4bc233a23` — Verify #1215 succeeded;
- production main `9d8824d3847ed80575f0b7ac126316dff77b42d9` — Verify #1216 succeeded.

## Next package

Before any actual Period Profit application, prove a one-time consumption contract that revalidates the still-active recognition and exact authorization/commit at read time, resolves selected-period ownership, and defines tax treatment explicitly. A commit alone is not an application.

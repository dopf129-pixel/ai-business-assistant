# AI Assistant Project State

## Current product state

AI Business Assistant remains a read-only Ozon business analyst and advisor. Ozon business mutations remain prohibited.

## Current verified checkpoint

Package: `v1371-v1380: Return COGS Profit Application Commit Readiness`

Exact production main: `9d8824d3847ed80575f0b7ac126316dff77b42d9`

Verify #1216: success.

Artifact: `9939566781`.

Digest: `sha256:a596fff205f62f924a1d22fda1cfca5d7bd85a04ceb7462fe8b1846794169aa2`.

## Period Profit accounting boundary

Canonical formula remains unchanged:

`period_profit = account_net_accrual - product_cost - configured_tax`

The Return COGS chain is now:

`evidence -> readiness -> staged amount -> recognition eligibility -> accounting recognition -> profit application eligibility -> application commit readiness`

The new package adds an append-only exact-once commit ledger keyed by exact `recognition_history_id`. The first successful writer wins; later attempts for that recognition version return the already-committed evidence instead of creating another commit.

Commit readiness and commit evidence still do not change Period Profit:

- `return_cogs_profit_applied=False`;
- `return_cogs_profit_application_amount=None`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- `read_only=True`;
- `executed=False`.

A committed record must reconcile the exact recognition identity, accounting date, RUB amount and exact authorization-history version. Missing, conflicting or malformed evidence fails closed. Unknown money remains `None`, never inferred zero.

## Exact-once boundary

`ReturnCogsProfitApplicationCommitRepository` uses an append-only SQLite ledger with a unique `recognition_history_id`, transactional `BEGIN IMMEDIATE`, and no UPDATE/DELETE semantics. This resolves first-writer-wins/no-repeat commitment evidence, but it does not yet authorize seller-facing Period Profit arithmetic.

## Verification lifecycle

- feature head `481ec0830163b2dee965afd58bd72fd9f52c6dea` — Verify #1214 succeeded;
- PR #411 synthetic merge `460ba8512b755306b3d4b5cdd84c49e4bc233a23` — Verify #1215 succeeded; artifact `9939537819`, digest `sha256:15cd33a80d92c63e442526f2d63afddd0efedab2cbc64e4a60ed75ca54bd98cd`;
- squash production main `9d8824d3847ed80575f0b7ac126316dff77b42d9` — Verify #1216 succeeded; artifact `9939566781`, digest `sha256:a596fff205f62f924a1d22fda1cfca5d7bd85a04ceb7462fe8b1846794169aa2`.

Historical failed SHAs remain failed evidence permanently and receive no transferred success claims.

## Preserved boundaries

- account-level Ozon finance remains the monetary authority;
- no Ozon mutation;
- no compensation double counting;
- no account-level monetary-authority double counting;
- no Period Profit formula change;
- application eligibility, commitment and application remain separate states;
- `externally_verified=False`.

## Next accounting package

The next package may design actual one-time Period Profit consumption only after proving atomic binding between the still-active recognition, its exact authorization, its exact commit, selected-period ownership, and explicit tax treatment. Until then `profit_adjustment_allowed` must remain false.

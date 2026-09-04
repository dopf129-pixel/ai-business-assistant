# Current Checkpoint v1351-v1360

Package: `Return COGS Accounting Recognition`

Date: 2026-09-04

## Production baseline

Exact verified main: `08d407f045e588b83b1c2096c5f652e663781b2d`

Verify #1195: 2268 passed / 0 failed.

## What this checkpoint proves

Return COGS recovery can now become an accounting-recognized fact only from explicit append-only seller accounting evidence after recognition eligibility has already passed.

Required exact coverage:

- identity `return_id + posting_number + SKU`;
- explicit accounting recognition date matching accounting attribution;
- explicit recognized RUB amount matching the staged and eligible recovery amount;
- explicit `COGS_RECOVERY_RECOGNIZED` state;
- append-only confirmation version.

A later `COGS_RECOVERY_RECOGNITION_REVOKED` version supersedes recognition and fails closed.

## Runtime outcome

On complete exact evidence:

- `period_cogs_recovery_confirmed=True`;
- `accounting_cogs_recovery_confirmed=True`;
- `confirmed_cogs_recovery_amount=<recognized eligible RUB amount>`.

This package deliberately does not alter Period Profit:

- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- canonical formula remains `period_profit = account_net_accrual - product_cost - configured_tax`.

## Verification chain

Failed precursor (permanently failed evidence):

- `5ec279e5da0581af8fb79b726476324ac3309cb8` — Verify #1192 — 2267 passed / 1 failed.

Successful lifecycle:

- feature `e311c2faec20d4236cb5ee5bf6e1799cbdbad7e3` — Verify #1193 — 2268/0 — artifact 9936817042 — `sha256:fdedfbf5bcaf5aca554bd052fc99d6b2377325fab31558c841eebc2a663d3e56`;
- PR #407 synthetic `555c977d64d0a3613a820e7efe8b2eaabb8114d8` — Verify #1194 — 2268/0 — artifact 9936855181 — `sha256:5fa6954544b93fa3ca8da3814df524a93cc80eb7a04881a16470bbaef64613e0`;
- production main `08d407f045e588b83b1c2096c5f652e663781b2d` — Verify #1195 — 2268/0 — artifact 9936912356 — `sha256:bbe069338654fcfac72ad782de2e14d07e8e9d370835d738f5f332d0adf1aa90`.

## Safety boundaries

- Ozon remains read-only;
- unknown is not zero;
- compensation double counting remains blocked;
- failed SHA evidence is never promoted;
- no automatic business execution;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Next package

`v1361+`: explicit fail-closed Period Profit application of an already-recognized Return COGS amount.

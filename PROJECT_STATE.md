# AI Assistant Project State

## Current product state

AI Business Assistant is a read-only Ozon business analyst and advisor. Ozon business mutations remain prohibited by Decision 036.

## Current verified checkpoint

Package: `v1351-v1360: Return COGS Accounting Recognition`

Exact production main: `08d407f045e588b83b1c2096c5f652e663781b2d`

GitHub Actions push Verify #1195: 2268 passed / 0 failed.

## Period Profit accounting boundary

Decision 037 account-level Ozon finance remains the monetary authority.

Base formula remains unchanged:

`period_profit = account_net_accrual - product_cost - configured_tax`

Return COGS now has an explicit append-only accounting-recognition layer after recognition eligibility. Recognition is accepted only when seller accounting evidence exactly reconciles `return_id + posting_number + SKU`, accounting date, RUB amount, and recognition state with the already-eligible candidate set.

A later append-only revocation supersedes earlier recognition and fails closed.

## Recognition is not yet profit application

When all recognition evidence is exact:

- `period_cogs_recovery_confirmed=True`;
- `accounting_cogs_recovery_confirmed=True`;
- `confirmed_cogs_recovery_amount` may equal the recognized eligible RUB amount.

In v1351-v1360 this still does not change seller-facing Period Profit:

- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- the canonical Period Profit formula remains unchanged.

## Production verification

The first feature candidate `5ec279e5da0581af8fb79b726476324ac3309cb8` failed Verify #1192 with one package-test assertion outside the intended one-cent reconciliation contract. That SHA remains failed evidence permanently and no success evidence is transferred from it.

Successful lifecycle:

- feature `e311c2faec20d4236cb5ee5bf6e1799cbdbad7e3` — Verify #1193 — 2268 passed / 0 failed — artifact 9936817042 — digest `sha256:fdedfbf5bcaf5aca554bd052fc99d6b2377325fab31558c841eebc2a663d3e56`;
- PR #407 synthetic `555c977d64d0a3613a820e7efe8b2eaabb8114d8` — Verify #1194 — 2268 passed / 0 failed — artifact 9936855181 — digest `sha256:5fa6954544b93fa3ca8da3814df524a93cc80eb7a04881a16470bbaef64613e0`;
- squash main `08d407f045e588b83b1c2096c5f652e663781b2d` — Verify #1195 — 2268 passed / 0 failed — artifact 9936912356 — digest `sha256:bbe069338654fcfac72ad782de2e14d07e8e9d370835d738f5f332d0adf1aa90`.

## Preserved boundaries

- Decisions 036-040 remain historical baseline contracts;
- additive `project_brain/DECISIONS_041_045.md` records Return COGS accounting gates through explicit recognition;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- no Period Profit formula change in this package;
- no compensation double counting;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Next accounting package

Apply an already-accounting-recognized Return COGS amount to Period Profit only through an explicit fail-closed application contract, preserving all existing evidence and no-double-counting gates.

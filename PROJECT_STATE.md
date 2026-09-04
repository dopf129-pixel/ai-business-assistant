# AI Assistant Project State

## Current product state

AI Business Assistant is a read-only Ozon business analyst and advisor. Ozon business mutations remain prohibited by Decision 036.

## Current verified checkpoint

Package: `v1331-v1340: Return COGS Recovery Amount Evidence`

Exact production main: `2213e693fc1c99dde853e41c6145c227c411a21a`

GitHub Actions push Verify #1178: 2248 passed / 0 failed.

## Period Profit accounting boundary

Decision 037 account-level Ozon finance remains the monetary authority.

Base formula remains unchanged:

`period_profit = account_net_accrual - product_cost - configured_tax`

Return COGS evidence now supports a staged monetary evidence amount after the full accounting-readiness contract passes.

The staged amount is derived only from each accounting-ready candidate's explicit effective-dated historical cost multiplied by explicit return quantity. The service cross-checks that value against the existing candidate historical-cost value and fails closed on missing, malformed, negative, non-finite, boolean or mismatched evidence.

Explicit historical cost zero may prove a zero staged amount. Missing cost or amount remains unknown and is never converted to zero.

## Monetary evidence versus recognition

`return_cogs_recovery_amount_evidence_confirmed=True` means the candidate set has a finite, internally consistent historical-cost recovery amount supported by already-confirmed accounting readiness.

It does not recognize the amount in Period Profit.

In v1331-v1340:

- `return_cogs_recovery_amount_evidence_amount` may be a confirmed staged RUB amount;
- `period_cogs_recovery_confirmed=False`;
- `accounting_cogs_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0.0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`.

## Production verification

No failed production SHA occurred in v1331-v1340.

- feature `fad2903b3b28a2f2edb270d33a0d327ca3fd42d7` — Verify #1176 — 2248 passed / 0 failed — artifact 9933505069 — digest `sha256:3eeeeb6a3b4bd7dffd6b75136bcd5a74cfdcc639ab5336caa1a2ba9b1a9b6b68`;
- PR #403 synthetic `0be4583b0e9248cd7e497e4e3419063abeb7fd19` — Verify #1177 — 2248 passed / 0 failed — artifact 9933534778 — digest `sha256:42d7cecc82a0278e6238f8a21f766b545f5395ce7e61dd54e62219cbb237c7b9`;
- squash main `2213e693fc1c99dde853e41c6145c227c411a21a` — Verify #1178 — 2248 passed / 0 failed — artifact 9933562627 — digest `sha256:03d474d8ca625593d52f4cd2943d0ec92e293666a26f9287331e00a10010f216`.

## Preserved boundaries

- Decisions 036-042 remain unchanged;
- Decision 043 records the staged monetary-evidence boundary;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- no Period Profit formula change;
- no recognized Return COGS recovery amount;
- no compensation double counting;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Next accounting package

Define recognition eligibility for a staged Return COGS amount as a separate contract. Recognition must remain period-bound, evidence-complete and no-double-count safe before any later package can consider changing Period Profit output.

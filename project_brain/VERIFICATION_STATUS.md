# Verification Status

Date: 2026-09-04

## Latest verified product baseline

`2213e693fc1c99dde853e41c6145c227c411a21a`

Latest merged production batch:

`v1331-v1340: Return COGS Recovery Amount Evidence`

### Entering exact docs-reconciled main

- exact main: `6c3836b15d0cc54f258aee1f40d6c36d31126375`;
- no verification evidence is transferred from this predecessor to later revisions.

### Failed intermediate evidence

No failed production SHA occurred in v1331-v1340. Failed SHAs from earlier packages remain failed evidence permanently.

### Exact feature-head verification

- SHA `fad2903b3b28a2f2edb270d33a0d327ca3fd42d7`;
- Verify #1176;
- 2248 passed / 0 failed;
- artifact 9933505069;
- digest `sha256:3eeeeb6a3b4bd7dffd6b75136bcd5a74cfdcc639ab5336caa1a2ba9b1a9b6b68`.

### PR merge-ref integration verification

- PR #403;
- synthetic SHA `0be4583b0e9248cd7e497e4e3419063abeb7fd19`;
- Verify #1177;
- 2248 passed / 0 failed;
- artifact 9933534778;
- digest `sha256:42d7cecc82a0278e6238f8a21f766b545f5395ce7e61dd54e62219cbb237c7b9`.

### Post-merge exact-main verification

- exact main `2213e693fc1c99dde853e41c6145c227c411a21a`;
- Verify #1178;
- 2248 passed / 0 failed;
- artifact 9933562627;
- digest `sha256:03d474d8ca625593d52f4cd2943d0ec92e293666a26f9287331e00a10010f216`.

## Current Return COGS monetary-evidence boundary

A staged recovery amount may be exposed only when the full candidate set is accounting-ready and each candidate has explicit valid historical cost, explicit positive return quantity, exact identity, and a reconciled historical candidate value.

`return_cogs_recovery_amount_evidence_confirmed=True` is monetary source evidence only.

Recognition remains closed:

- `period_cogs_recovery_confirmed=False`;
- `accounting_cogs_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0.0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`.

Period Profit formula is unchanged. No Ozon mutation is authorized or performed.

## Verification policy

Exact branch push verification proves only that exact branch head. Pull-request verification proves only the synthetic merge ref. Every squash-main SHA requires its own exact push verification. Failed SHAs remain failed evidence permanently. Cancelled/pending SHAs carry no transferable success claim. Missing evidence remains unknown and is never interpreted as zero or clean. Workflow evidence is project CI evidence only; `externally_verified=False`.

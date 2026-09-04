# Verification Status

Date: 2026-09-04

## Latest verified product baseline

`539fb53cbdbea2295d5dfc29799bb93d08a6ddf6`

Latest merged production batch:

`v1361-v1370: Return COGS Period Profit Application Eligibility`

### Entering exact docs-reconciled main

- exact predecessor docs-main: `6c21ed593bd42183b8bf029245bdfaf683557e0e`;
- Verify #1199 succeeded for that exact SHA;
- artifact 9937084027;
- digest `sha256:8ddc8635e6a8e3476170c64cd3f7639d88a2d47978117218bd071828a136366a`;
- no verification evidence is transferred from this predecessor to later revisions.

### Failed intermediate evidence

- SHA `c5260a1e5f8ee043481ed04f923d4add8a54e725` — Verify #1201 — 2277 passed / 1 failed;
- artifact 9937610024;
- digest `sha256:28f286a17f975329afcb658e0e4d84fdc86bd18bdaef8d48ce0ea0d3dbffe000`;
- failure was the legacy `tests/test_period_profit_factory.py` assertion that still required `PeriodProfitReturnCogsAccountingRecognitionService` to be the terminal factory service;
- this SHA remains failed evidence permanently and no later success evidence is transferred to it.

Earlier failed SHA `5ec279e5da0581af8fb79b726476324ac3309cb8` from v1351-v1360 also remains failed evidence permanently.

### Exact feature-head verification

- SHA `d19476ce387d8e0a1855abd3167cfc4677cb76c2`;
- Verify #1202;
- 2278 passed / 0 failed;
- artifact 9937768191;
- digest `sha256:e26290a10f168ec74d6e01ae9e37a1655b1264f9fc0735c6c4db8e31014ead60`.

### PR merge-ref integration verification

- PR #409;
- synthetic SHA `adb63eb2ea2c3813f461b60ace604cd899277b42`;
- Verify #1203;
- 2278 passed / 0 failed;
- artifact 9937809222;
- digest `sha256:96b7247d2659f02fcbd834cbb5144fe785d8cff0db320cb8e2154a2dbc24197e`;
- CI artifact revision explicitly records `refs/pull/409/merge` at the synthetic SHA.

### Post-merge exact-main verification

- exact main `539fb53cbdbea2295d5dfc29799bb93d08a6ddf6`;
- Verify #1204;
- 2278 passed / 0 failed;
- artifact 9937835931;
- digest `sha256:ee36649698d29ea297144e763eb6f07a02662df0843c56c53a014ab435fc73f9`;
- CI artifact revision explicitly records `refs/heads/main` at the exact SHA.

## Current Return COGS application boundary

Accounting recognition remains a separate explicit layer and does not itself authorize Period Profit application.

The new application-eligibility layer requires exact coverage and reconciliation for:

- exact accounting-recognition history version;
- `return_id + posting_number + SKU`;
- recognized accounting date and selected requested period;
- recognized/authorized amount within the established monetary tolerance;
- RUB currency;
- explicit compensation non-overlap;
- explicit proof that the recovery is excluded from account-level Ozon `net_accrual`;
- append-only explicit application authorization;
- no prior `PROFIT_APPLICATION_APPLIED` state for the recognition version.

Missing, malformed, conflicting, mismatched, revoked, already-applied, or monetary-authority-ambiguous evidence fails closed.

Even when application eligibility is confirmed, v1361-v1370 deliberately keeps `return_cogs_profit_applied=False`, `return_cogs_profit_application_amount=None`, `profit_adjustment_allowed=False`, and `automatic_recovery_allowed=False`. The canonical Period Profit formula is unchanged.

## Verification policy

Exact branch push verification proves only that exact branch head. Pull-request verification proves only the actual synthetic merge checkout. Every squash-main SHA requires its own exact push verification. Failed SHAs remain failed evidence permanently. Cancelled/pending SHAs carry no transferable success claim. Missing evidence remains unknown and is never interpreted as zero or clean. Workflow evidence is project CI evidence only; `externally_verified=False`.

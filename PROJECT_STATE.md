# AI Assistant Project State

## Current product state

AI Business Assistant is a read-only Ozon business analyst and advisor. Ozon business mutations remain prohibited by Decision 036.

## Current verified checkpoint

Package: `v1361-v1370: Return COGS Period Profit Application Eligibility`

Exact production main: `539fb53cbdbea2295d5dfc29799bb93d08a6ddf6`

GitHub Actions push Verify #1204: 2278 passed / 0 failed.

Artifact: 9937835931.

Digest: `sha256:ee36649698d29ea297144e763eb6f07a02662df0843c56c53a014ab435fc73f9`.

## Period Profit accounting boundary

Decision 037 account-level Ozon finance remains the monetary authority.

Canonical formula remains unchanged:

`period_profit = account_net_accrual - product_cost - configured_tax`

The v1361-v1370 package adds a separate application-eligibility layer after Return COGS accounting recognition. It does not apply money to seller-facing Period Profit.

Application eligibility requires exact evidence that the already-recognized Return COGS amount is excluded from account-level `net_accrual`; absence of contrary evidence is not enough. It also requires exact recognition-version identity, requested accounting-period reconciliation, RUB amount reconciliation, compensation non-overlap, and an explicit append-only application authorization.

## Recognition is not application

The chain is now explicit:

`evidence -> readiness -> staged amount -> recognition eligibility -> accounting recognition -> profit application eligibility`

Successful accounting recognition can still expose:

- `period_cogs_recovery_confirmed=True`;
- `accounting_cogs_recovery_confirmed=True`;
- `confirmed_cogs_recovery_amount=<recognized eligible RUB amount>`.

Successful application eligibility may additionally expose an eligible RUB amount, but it still does not alter Period Profit:

- `return_cogs_profit_application_eligibility_confirmed` is a distinct gate;
- `return_cogs_profit_applied=False`;
- `return_cogs_profit_application_amount=None`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`.

Unknown monetary evidence remains `None`, never inferred zero.

## Application authorization and idempotency

`ReturnCogsProfitApplicationAuthorizationRepository` stores append-only seller/accounting application state keyed to the exact accounting-recognition history version and Return COGS identity.

An authorization is usable only when it explicitly confirms:

- exact `recognition_history_id + return_id + posting_number + SKU`;
- recognized accounting date;
- exact authorized RUB amount within the established monetary tolerance;
- `EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL` monetary-authority treatment;
- compensation non-overlap.

A later revocation fails closed. Once an exact recognition version has any `PROFIT_APPLICATION_APPLIED` evidence, that version is permanently blocked from re-eligibility, preserving no-repeat/idempotency semantics.

## Production verification

Failed precursor, permanently failed evidence:

- `c5260a1e5f8ee043481ed04f923d4add8a54e725` — Verify #1201 — 2277 passed / 1 failed — artifact 9937610024 — digest `sha256:28f286a17f975329afcb658e0e4d84fdc86bd18bdaef8d48ce0ea0d3dbffe000`;
- failure was the legacy factory regression still expecting accounting recognition to remain the terminal Return COGS service.

Successful lifecycle:

- feature `d19476ce387d8e0a1855abd3167cfc4677cb76c2` — Verify #1202 — 2278 passed / 0 failed — artifact 9937768191 — digest `sha256:e26290a10f168ec74d6e01ae9e37a1655b1264f9fc0735c6c4db8e31014ead60`;
- PR #409 synthetic `adb63eb2ea2c3813f461b60ace604cd899277b42` — Verify #1203 — 2278 passed / 0 failed — artifact 9937809222 — digest `sha256:96b7247d2659f02fcbd834cbb5144fe785d8cff0db320cb8e2154a2dbc24197e`; CI checkout explicitly used `refs/pull/409/merge`;
- squash main `539fb53cbdbea2295d5dfc29799bb93d08a6ddf6` — Verify #1204 — 2278 passed / 0 failed — artifact 9937835931 — digest `sha256:ee36649698d29ea297144e763eb6f07a02662df0843c56c53a014ab435fc73f9`; CI checkout explicitly used `refs/heads/main`.

The earlier failed v1351-v1360 precursor `5ec279e5da0581af8fb79b726476324ac3309cb8` also remains failed evidence permanently.

## Preserved boundaries

- Decisions 036-045 remain baseline accounting/safety contracts;
- Decision 046 records the new explicit application-eligibility/no-double-count contract;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- no Period Profit formula change in this package;
- no compensation double counting;
- no account-level monetary-authority double counting;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Next accounting package

Do not add the eligible Return COGS amount to Period Profit until the actual application semantics are separately designed and proven. The next package should resolve how a read-only Period Profit computation consumes append-only applied-state evidence without race/repeat ambiguity and how that applied state is reconciled atomically with the exact still-active recognition version. Tax treatment of any eventual adjustment must also remain explicit rather than inferred.

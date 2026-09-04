# Current Checkpoint v1361-v1370

Package: `Return COGS Period Profit Application Eligibility`

Date: 2026-09-04

## Production baseline

Exact verified production main: `539fb53cbdbea2295d5dfc29799bb93d08a6ddf6`

Verify #1204: 2278 passed / 0 failed.

Artifact: 9937835931.

Digest: `sha256:ee36649698d29ea297144e763eb6f07a02662df0843c56c53a014ab435fc73f9`.

## Architectural finding

The existing seller-facing Period Profit is based on account-level Ozon `net_accrual`, which remains the monetary authority under Decision 037. Existing Return COGS accounting-recognition evidence does not by itself prove that the recognized recovery amount is absent from that account-level monetary result.

Therefore applying a recognized Return COGS amount on top of Period Profit without further evidence could double count money. The package does not change the formula.

## What this checkpoint adds

A separate `PeriodProfitReturnCogsApplicationEligibilityService` now follows `PeriodProfitReturnCogsAccountingRecognitionService` in the factory chain.

It consumes only already-recognized evidence and requires explicit application authorization plus exact no-double-count proof before exposing an application-eligible amount.

Eligibility requires:

- active accounting recognition;
- exact recognition `history_id`;
- exact `return_id + posting_number + SKU` coverage;
- exact requested-period/accounting-date reconciliation;
- recognized and authorized RUB amount reconciliation using the existing one-cent tolerance convention;
- explicit compensation double-count clearance;
- explicit application-level compensation non-overlap;
- exact monetary-authority treatment `EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL`;
- explicit monetary-authority non-overlap confirmation;
- no previous applied state for the recognition version.

## Append-only application authorization

`ReturnCogsProfitApplicationAuthorizationRepository` adds append-only application state for an exact recognition version.

States are separated from accounting recognition:

- `PROFIT_APPLICATION_AUTHORIZED`;
- `PROFIT_APPLICATION_APPLIED`;
- `PROFIT_APPLICATION_AUTHORIZATION_REVOKED`.

Authorization/revocation is versioned evidence, not an Ozon mutation. A later revocation fails closed. Any existing `PROFIT_APPLICATION_APPLIED` state permanently blocks that recognition version from becoming eligible again, providing the no-repeat/idempotency boundary for a future application package.

## Runtime outcome

On complete exact evidence, the application service may expose:

- `return_cogs_profit_application_eligibility_confirmed=True`;
- `return_cogs_profit_application_eligible_amount=<recognized authorized RUB amount>`;
- `return_cogs_profit_application_eligible_currency=RUB`.

It deliberately still returns:

- `return_cogs_profit_applied=False`;
- `return_cogs_profit_application_amount=None`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- `read_only=True`;
- `executed=False`.

Unknown monetary data remains `None`, not zero.

Canonical formula remains:

`period_profit = account_net_accrual - product_cost - configured_tax`

## Verification chain

Permanently failed precursor:

- `c5260a1e5f8ee043481ed04f923d4add8a54e725` — Verify #1201 — 2277 passed / 1 failed — artifact 9937610024 — `sha256:28f286a17f975329afcb658e0e4d84fdc86bd18bdaef8d48ce0ea0d3dbffe000`.

Failure cause: the legacy factory regression still asserted that accounting recognition was the terminal factory service. The SHA remains failed evidence permanently.

Successful production lifecycle:

- feature `d19476ce387d8e0a1855abd3167cfc4677cb76c2` — Verify #1202 — 2278/0 — artifact 9937768191 — `sha256:e26290a10f168ec74d6e01ae9e37a1655b1264f9fc0735c6c4db8e31014ead60`;
- PR #409 synthetic `adb63eb2ea2c3813f461b60ace604cd899277b42` — Verify #1203 — 2278/0 — artifact 9937809222 — `sha256:96b7247d2659f02fcbd834cbb5144fe785d8cff0db320cb8e2154a2dbc24197e`; checkout `refs/pull/409/merge`;
- production main `539fb53cbdbea2295d5dfc29799bb93d08a6ddf6` — Verify #1204 — 2278/0 — artifact 9937835931 — `sha256:ee36649698d29ea297144e763eb6f07a02662df0843c56c53a014ab435fc73f9`; checkout `refs/heads/main`.

## Safety boundaries

- Ozon remains permanently read-only;
- recognized != eligible-to-apply != applied;
- unknown != zero;
- absence of monetary-authority evidence is not proof of exclusion;
- compensation overlap remains blocked;
- account-level Ozon finance remains monetary authority;
- no seller-facing Period Profit adjustment in this package;
- no Product Decision/Product Task Draft execution;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Decision

Decision 046 is accepted for this package: application eligibility requires explicit proof that the recognized recovery is excluded from account-level `net_accrual`, exact append-only application authorization, and a no-repeat boundary. Eligibility itself still cannot alter Period Profit.

## Next package

`v1371+` should not merely switch `profit_adjustment_allowed=True`. It must first resolve the actual application contract: how an applied-state fact is bound atomically to the exact still-active recognition version, how a read-only query avoids repeat/race ambiguity, how the selected Period Profit result consumes that fact exactly once, and how tax semantics of the adjustment are explicitly determined. If any of those ownership facts remain incomplete, seller-facing Period Profit must remain unchanged.

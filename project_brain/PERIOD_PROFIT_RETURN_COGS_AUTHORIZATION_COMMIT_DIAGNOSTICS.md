# Period Profit Return COGS authorization and commit diagnostics

Production basis: `27f1e3c5035f8ed9e007ce2b006837dad6821bf9`.

## Scope

This package extends seller-facing, read-only Return COGS observability across two downstream gates that were previously presented only as generic blockers:

1. profit-application authorization;
2. exact-once application commit.

The package does not create an authorization, perform a commit, write accounting evidence, mutate Ozon, or change Period Profit arithmetic.

## Gate ordering

The compact Period Profit response still stops at the first unproven gate in this order:

1. inventory recovery evidence;
2. accounting attribution / compensation double-count clearance;
3. accounting recognition;
4. profit-application authorization;
5. exact-once commit;
6. final seller-facing application.

A downstream diagnostic is never shown as proof that an upstream gate passed unless the existing evidence flags already prove that state.

## Exact authorization diagnostics

When accounting recognition is confirmed but `return_cogs_profit_application_eligibility_confirmed` is not true, compact Period Profit now binds authorization evidence to the exact `return_id / posting_number / sku` identity and reports the first applicable reason already present in read-only evidence.

The diagnostic can distinguish:

- no separate profit-application authorization;
- unavailable or invalid authorization evidence;
- authorization status not ready;
- missing explicit `application_authorization_confirmed`;
- missing `PROFIT_APPLICATION_AUTHORIZED` state;
- inability to prove that the application was not already applied;
- authorization identity mismatch;
- missing or mismatched recognition history version;
- missing/invalid authorized amount;
- authorized amount mismatch against the recognized amount;
- authorization currency not confirmed as RUB;
- accounting-date mismatch against the recognition record;
- missing `EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL` monetary-authority treatment;
- monetary-authority non-overlap not explicitly confirmed;
- compensation non-overlap not explicitly confirmed.

Unknown/non-true overlap facts stay blocked. They are not interpreted as zero, false-as-proof, or safe-by-default.

## Exact-once commit diagnostics

When authorization eligibility is confirmed but `return_cogs_profit_application_commit_confirmed` is not true, compact Period Profit now binds commit evidence to the exact candidate and the exact recognition/authorization versions.

The diagnostic can distinguish:

- missing/invalid recognition version for commit;
- missing/invalid authorization version for commit;
- missing commit record;
- commit-ready state with no commit record yet;
- unavailable or invalid commit evidence;
- commit record not explicitly confirmed;
- recognition-history mismatch;
- exact identity mismatch against the recognition row;
- accounting-date mismatch;
- missing/invalid committed amount;
- committed amount mismatch against the recognized amount;
- commit currency not confirmed as RUB;
- authorization-history mismatch.

`return_cogs_profit_application_commit_ready == True` is still readiness only. It is explicitly presented as not committed and the seller-facing response remains `read_only=True`, `executed=False`.

## Deterministic presentation

Authorization and commit blockers are sorted by exact identity before rendering. At most three exact candidate identities are expanded; larger sets use an `ещё N` suffix. This matches the bounded compact-response behavior already used for inventory, accounting attribution, and accounting recognition diagnostics.

Candidate quantity comes only from the exact candidate row. Missing quantity remains `неизвестно`; it is never rendered as zero.

## Financial invariants

- Ozon remains READ-ONLY.
- `ReturnedToOzon` still does not prove `SALEABLE_RESTORED`.
- `unknown != zero`.
- Accounting recognition remains a prerequisite for authorization.
- Authorization remains a prerequisite for commit.
- Commit readiness is not commit confirmation.
- No Return COGS amount is inferred from quantity × unit cost in presentation code.
- No accounting, authorization, or commit fact is auto-filled.
- No seller-facing write path was added for accounting recognition, authorization, or commit.
- Period Profit arithmetic is unchanged by these diagnostics.
- Seller-facing Period Profit remains read-only/non-executing.

## Regression coverage

Dedicated regression coverage proves that:

- missing authorization exposes the exact candidate identity;
- authorized-amount mismatch stays at the authorization gate and does not advance to commit;
- unknown monetary-authority non-overlap remains unconfirmed;
- commit-ready with no ledger record is explicitly shown as ready-but-not-committed;
- committed-amount mismatch exposes the exact candidate;
- authorization diagnostics are deterministically ordered and capped at three expanded identities;
- the response remains `read_only=True` and `executed=False`.

Existing regressions continue to prove the earlier inventory, attribution, recognition, and first-gate ordering semantics.

## SHA-bound verification evidence

Feature package:

- feature head `01186c952a03ef8df886d4617b5375f7bb959515` — Verify #1681 passed on the exact push SHA;
- PR #483 synthetic merge `19cfe78ae4c6f45f626e97cb152c90881bf8a97a` — Verify #1682 passed; artifact `verification-19cfe78ae4c6f45f626e97cb152c90881bf8a97a`;
- squash production main `27f1e3c5035f8ed9e007ce2b006837dad6821bf9` — Verify #1683 passed; artifact `verification-27f1e3c5035f8ed9e007ce2b006837dad6821bf9`.

Verification evidence is SHA-bound and is never transferred between revisions.

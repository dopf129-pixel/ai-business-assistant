# Period Profit Return COGS controlled commit integrity

Production basis: `2959fa0173d4a69757bd02092f0c765fcc1577ad`.

## Decision

Return COGS profit application has a controlled accounting-side commit boundary. It is not a seller-facing Telegram action and it does not mutate Ozon. The controlled path must revalidate durable recognition and authorization evidence in the same database transaction that appends the exact-once commit.

The production repository therefore exposes `commit_current_authorization(...)` as a controlled internal write primitive. It opens `BEGIN IMMEDIATE`, re-reads current recognition and authorization rows, validates their exact identity/version/state/date/amount/currency relationship, and only then appends the durable commitment.

## Controlled commit contract

The caller supplies only the exact recognition history ID, authorization history ID, return/posting/SKU identity, commit date and internal source. The controlled path does **not** accept a caller-supplied committed amount, accounting date, or currency.

Inside the same `BEGIN IMMEDIATE` transaction it requires:

- the supplied recognition history ID to still be the latest recognition version for the exact return identity;
- recognition state `COGS_RECOVERY_RECOGNIZED`;
- finite non-negative recognized amount;
- RUB recognition currency;
- a valid recovery accounting date;
- the supplied authorization history ID to still be the latest authorization for that recognition version;
- authorization state `PROFIT_APPLICATION_AUTHORIZED`;
- no historical `PROFIT_APPLICATION_APPLIED` state for that recognition;
- explicit monetary-authority treatment `EXCLUDED_FROM_ACCOUNT_NET_ACCRUAL`;
- required compensation/non-overlap evidence to remain present;
- exact recovery-accounting-date equality between recognition and authorization;
- exact monetary equality within the existing 0.01 RUB comparison tolerance.

Only after these checks pass does the repository derive the commit amount/date/currency from the current durable rows and append the ledger record.

Successful controlled writes expose read-back observability including:

- `controlled_commit_recognition_revalidated=True`;
- `controlled_commit_authorization_revalidated=True`;
- `controlled_commit_transaction_basis=BEGIN_IMMEDIATE_CURRENT_RECOGNITION_AND_AUTHORIZATION`.

These flags describe the write proof. They do not create seller-facing execution authority.

## Exact-once and retry semantics

The commit history remains append-only. Update and delete triggers continue to reject mutation of existing commit rows.

`recognition_history_id` remains unique. The repository additionally prevents an `authorization_history_id` from being reused to commit a second recognition version.

Retry semantics are now explicit:

- an exact semantic replay of the same recognition/authorization/identity/date/amount/currency/source is idempotent and returns the already durable commit;
- retry time itself is not treated as a business-semantic difference, so a process restart or timeout followed by a later retry can recover the already committed result;
- a replay that changes identity, accounting date, amount, currency, authorization history ID, or source fails closed with `RETURN_COGS_PROFIT_APPLICATION_COMMIT_REPLAY_CONFLICT`;
- the first durable row is never silently replaced by a changed replay.

This closes the former first-writer ambiguity where the same recognition ID could return the existing row even when the replay payload materially disagreed with it.

## Non-finite monetary evidence

`NaN`, positive infinity and negative infinity are invalid commit amounts. They cannot be persisted or treated as zero.

This preserves `unknown != zero` and prevents non-finite values from crossing the exact-once boundary.

## Read-only durable ledger audit

`ReturnCogsProfitApplicationCommitLedgerIntegrityService` provides a separate read-only audit over the append-only ledger. It does not create, update or delete commits.

For every durable commit it reconciles current upstream evidence and checks:

- unique recognition history binding;
- unique authorization history binding;
- exact return/posting/SKU identity;
- current recognition status and exact history version;
- current authorization status and exact history version;
- authorization has not subsequently become applied;
- monetary-authority and compensation non-overlap proof remains explicit;
- finite non-negative committed/recognized/authorized amounts;
- exact amount reconciliation;
- RUB currency across the chain;
- exact recovery accounting date across the chain.

The audit deliberately reports stale or revoked upstream state rather than rewriting history. A historical commit remains durable; an integrity issue is surfaced as operational evidence.

## Recovery and restart regression coverage

Collected tests cover:

- a valid controlled commit whose monetary facts are derived from current recognition/authorization rows;
- authorization becoming stale between readiness and commit;
- recognition version becoming stale before commit;
- exact retry after repository/process restart yielding one durable row;
- conflicting replay payload failing closed while the first row remains immutable;
- authorization history ID reuse across another recognition being blocked;
- NaN/Infinity rejection;
- a healthy read-only ledger audit;
- post-commit authorization revocation being surfaced by the ledger audit.

The test file lives under repository-root `tests/` because `pytest.ini` explicitly configures `testpaths = tests`. An earlier temporary copy under `app/tests` was removed because it was outside the collected test tree.

## Verification evidence

- final feature head `1397ebef0fcb1cda17ace6ffde4e2fe2053a1ff0` — Verify #1747 passed; 2400 tests passed; artifact `verification-1397ebef0fcb1cda17ace6ffde4e2fe2053a1ff0`, digest `sha256:ef97392731f368d39a2947bc57910034fd65ef693b7f826d94bfda67b7dd29d0`;
- PR #493 synthetic merge `76bc066c671ef33139eabf8728da03f72e0f6c1f` — Verify #1748 passed; 2400 tests passed; artifact `verification-76bc066c671ef33139eabf8728da03f72e0f6c1f`, digest `sha256:348b83724fa70eccaae433487bf34cccd89c3d316fbaac2e77bf773e0303cd4b`;
- squash production main `2959fa0173d4a69757bd02092f0c765fcc1577ad` — Verify #1749 passed; 2400 tests passed; artifact `verification-2959fa0173d4a69757bd02092f0c765fcc1577ad`, digest `sha256:3a0b8ca62ba264d7879d028b342ca5695aff55df29c00ef4d54b7a84d62ab588`.

Earlier intermediate feature SHAs that failed the legacy first-writer test remain failed evidence permanently and are not reused as proof for this package.

## Safety invariants

- Ozon remains READ-ONLY.
- No seller-facing commit button or accounting write path is introduced.
- `ReturnedToOzon` remains candidate evidence only, not proof of `SALEABLE_RESTORED`.
- `unknown != zero`.
- No Return COGS amount is inferred from `quantity × guessed unit cost`.
- Missing accounting/business facts are not auto-filled.
- Recognition does not imply authorization.
- Authorization does not imply commit.
- Commit does not bypass final candidate/chain integrity checks.
- Seller-facing Period Profit remains `read_only=True` and `executed=False`.

# Verification Status

Date: 2026-09-09

## Latest verified product baseline

`2959fa0173d4a69757bd02092f0c765fcc1577ad`

Package: `Return COGS controlled commit write and ledger integrity`.

### Exact feature head

- SHA `1397ebef0fcb1cda17ace6ffde4e2fe2053a1ff0`;
- Verify #1747 succeeded;
- full suite: 2400 passed;
- artifact `verification-1397ebef0fcb1cda17ace6ffde4e2fe2053a1ff0`;
- digest `sha256:ef97392731f368d39a2947bc57910034fd65ef693b7f826d94bfda67b7dd29d0`.

### PR integration checkout

- PR #493;
- synthetic merge SHA `76bc066c671ef33139eabf8728da03f72e0f6c1f`;
- Verify #1748 succeeded;
- full suite: 2400 passed;
- artifact `verification-76bc066c671ef33139eabf8728da03f72e0f6c1f`;
- digest `sha256:348b83724fa70eccaae433487bf34cccd89c3d316fbaac2e77bf773e0303cd4b`.

### Exact production main

- squash SHA `2959fa0173d4a69757bd02092f0c765fcc1577ad`;
- Verify #1749 succeeded;
- full suite: 2400 passed;
- artifact `verification-2959fa0173d4a69757bd02092f0c765fcc1577ad`;
- digest `sha256:3a0b8ca62ba264d7879d028b342ca5695aff55df29c00ef4d54b7a84d62ab588`.

## Product behavior verified

The seller-facing Return COGS chain remains fail-closed through inventory recovery, accounting attribution, recognition, authorization, exact-once commit and final read-only Period Profit application.

The controlled accounting-side commit boundary is now hardened as well. `commit_current_authorization(...)` opens `BEGIN IMMEDIATE`, re-reads the latest recognition and authorization evidence inside the same transaction, rejects stale/revoked/applied or mismatched evidence, derives amount/date/currency from those durable rows, and only then appends the commit ledger.

Exact semantic retries are idempotent. Materially changed replays fail closed instead of silently returning the first row. Authorization history IDs cannot be reused across another recognition. NaN and Infinity are invalid monetary evidence.

A separate read-only ledger audit reconciles durable commits against current recognition and authorization history and surfaces stale/revoked/orphan/mismatched evidence without mutating history.

The historical control warning of 8 unresolved units/returns remains distinct from the 785 exact raw Returns API records. Repository evidence still does not prove the identities of that historical set of 8 and no identity list is fabricated.

## Failed-revision evidence

Earlier intermediate feature revisions in this package failed the legacy first-writer replay test. Those SHAs remain failed permanently and are not reused as verification evidence. The verified package baseline starts at the final green feature head listed above.

## Safety invariants

- Ozon remains read-only.
- No seller-facing accounting/commit write control is introduced.
- `ReturnedToOzon` is candidate evidence only and is not `SALEABLE_RESTORED`.
- `unknown != zero`.
- No guessed `quantity × unit cost` Return COGS derivation is permitted.
- Missing accounting/business facts are not auto-filled.
- Recognition does not imply authorization; authorization does not imply commit; commit does not bypass downstream exact-chain and candidate-set reconciliation.
- Seller-facing Period Profit remains `read_only=True` and `executed=False`.

## Verification policy

Verification is SHA-bound. Exact branch verification proves only that branch head. PR verification proves only the synthetic integration checkout. Every squash-main SHA requires its own exact verification. Failed SHAs remain failed permanently and successful evidence is never transferred between revisions.

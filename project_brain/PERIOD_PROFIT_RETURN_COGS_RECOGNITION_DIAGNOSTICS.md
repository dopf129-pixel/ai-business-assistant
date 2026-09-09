# Period Profit Return COGS recognition diagnostics

Production basis: `67e31db1b51744b1584d848b133b9271fceaa10d`.

## Decision

The seller-facing compact Period Profit response remains read-only and fail-closed while explaining the first unproven Return COGS stage. After inventory recovery and accounting attribution are already proven, the accounting-recognition stage now exposes exact per-candidate blockers instead of collapsing all recognition failures into one generic sentence.

The diagnostic is keyed only by exact `return_id / posting_number / sku` identity already present in read evidence. Candidate quantity is reused only for presentation of the matching candidate; an absent or invalid quantity is rendered as `неизвестно`, never as zero.

## Recognition blockers

For each exact candidate identity, the compact response may report that:

- no separate accounting-recognition evidence exists;
- recognition evidence is unavailable or invalid;
- the recognition record is not ready;
- explicit accounting recognition is not confirmed;
- `COGS_RECOVERY_RECOGNIZED` is not confirmed;
- recognized amount is absent/invalid;
- the expected staged recovery amount is not independently confirmed;
- recognized amount does not match the staged recovery amount;
- recognition currency is not explicitly `RUB`;
- recognition accounting date is absent;
- attribution accounting date is not available;
- recognition date does not match the accounting-attribution date.

Rows are sorted by exact identity before presentation. At most three candidate identities are expanded; larger sets use an additional-count suffix.

## Fail-closed invariants

This package is observability only.

- Ozon remains READ-ONLY.
- No accounting-recognition, attribution, authorization, or commit repository is written by the diagnostic.
- A staged recovery amount is not treated as accounting recognition.
- Unknown recognition facts are not auto-filled and are not converted to zero.
- Amount and date mismatches remain blockers; they do not advance to profit-application authorization.
- Seller-facing Period Profit remains `read_only=True` and `executed=False`.
- No Return COGS amount is inferred from return quantity or product cost outside the established evidence chain.
- Recognition diagnostics do not change Period Profit arithmetic or authorize application.

## Regression coverage

Regression tests prove that missing recognition exposes the exact return/posting/SKU identity while preserving unknown quantity, amount mismatch remains at the recognition gate, accounting-date mismatch remains at the recognition gate, downstream authorization is not shown prematurely, and recognition diagnostics are deterministic and limited to three expanded candidate identities.

## SHA-bound verification evidence

Recognition diagnostics package:

- feature head `7b60bbb2ddd6ef3aa5ef3534eeaebde738651432` — Verify #1672 passed on the exact push SHA with compile, deterministic schema, full test suite, SHA-bound report, and artifact upload successful;
- actual PR #481 synthetic merge `102658787280a6ec1e24e74b3d50571e54ccaaf6` — Verify #1673 passed on the PR merge revision with the same full verification workflow;
- squash production main `67e31db1b51744b1584d848b133b9271fceaa10d` — Verify #1674 passed on the exact `main` push SHA with compile, deterministic schema, full test suite, SHA-bound report, and artifact upload successful.

Verification evidence is SHA-bound and is never transferred between revisions.

# Current Checkpoint v722-v730

Date: 2026-08-31

Package: Financial Telegram Result Integrity v1

## Verified implementation

The seller-facing read-only Unit Economics and Returns Finance Impact detail paths now reject malformed downstream payloads before formatting.

Verified behavior:

- Unit Economics requires explicit boolean error contract;
- successful Unit Economics requires explicit availability/source/SKU/missing-fields evidence;
- available=False remains a legitimate evidence-limited success;
- explicit Unit Economics failures retain their existing seller-facing error message;
- Returns Finance Impact requires explicit error, requested SKU, period, completeness, category, and missing-data shape;
- malformed category items stop before formatter access;
- explicit returns-finance failures remain failures;
- incomplete observed-return evidence remains non-error but keeps incomplete-warning semantics;
- no financial formula, tax/fee arithmetic, Product Decision rule, persistence, execution, or Ozon mutation changed;
- `data/users.json` remains untouched.

## Architecture Review

Architecture Review Required: Yes.

Reason:

- seller-facing financial result semantics changed at the Telegram presentation boundary;
- package exceeds 300 changed lines including tests.

Critical Review Required: No.

## SHA-bound verification evidence

- entering main `eafc9f19ba9865face765379396ca46ac0a919c3`: push Verify #404, 1622 passed / 0 failed, digest `sha256:56f8df7a744bb72a3ecbf7e32e34c72ff903d3a37a4b69bdc68bb56458f184f4`;
- failed intermediate `64d34b244f790065acb0a636542a5684bd598dec`: push Verify #405, 1627 passed / 4 failed, digest `sha256:145d4d39f1e4374f2386ceb2d00b9473181c932b1d2f1f065b99c94a8c52774e`;
- cancelled intermediate `fdd90ff6368178bf14896cc2d02f3aa57af90291`: push Verify #406, cancelled; no transferable verification claim;
- final feature `43404cf36f7753dc9701ba561443d7eb6160d037`: push Verify #407, 1631 passed / 0 failed, digest `sha256:b33b6f78e24da61d1b5475ad6aeef87551b8b1c4886440d5b8432aab7ebc7eed`;
- PR #280 synthetic merge `815f154470ad15a8b000fca072c806b6bf310d10`: Verify #408, 1631 passed / 0 failed, digest `sha256:325b6855603b80c8ecec817fd976cf6f05a7edb75c1645ed73bf6a69d475a069`;
- squash-main `5cf5a9cba19cc0efc171c1eb8d626868bf415d53`: push Verify #409, 1631 passed / 0 failed, digest `sha256:4c439270e095f5e3aab3ec576a45736b387d81720bfe07d73b9ebc94cf9a5070`.

## Verification semantics

- failed intermediate SHA remains failed evidence;
- cancelled intermediate SHA remains unknown/cancelled evidence;
- feature, synthetic merge-ref, and squash-main evidence remain distinct;
- no evidence is transferred between different SHAs;
- workflow/test-manifest evidence is not independent external verification;
- `externally_verified=False`.

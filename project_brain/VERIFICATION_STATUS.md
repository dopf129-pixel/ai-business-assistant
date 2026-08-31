# Verification Status

Date: 2026-08-31

## Latest verified product baseline

`5cf5a9cba19cc0efc171c1eb8d626868bf415d53`

Latest merged production-correctness batch:

`v722-v730: Financial Telegram Result Integrity`

### Entering exact-main verification

- exact main: `eafc9f19ba9865face765379396ca46ac0a919c3`
- push Verify #404
- conclusion: success
- tests: 1622 passed / 0 failed
- artifact: `verification-eafc9f19ba9865face765379396ca46ac0a919c3`
- artifact digest: `sha256:56f8df7a744bb72a3ecbf7e32e34c72ff903d3a37a4b69bdc68bb56458f184f4`

### Failed intermediate feature SHA

- exact SHA: `64d34b244f790065acb0a636542a5684bd598dec`
- push Verify #405
- conclusion: failure
- tests: 1627 passed / 4 failed
- artifact: `verification-64d34b244f790065acb0a636542a5684bd598dec`
- artifact digest: `sha256:145d4d39f1e4374f2386ceb2d00b9473181c932b1d2f1f065b99c94a8c52774e`

The failures were fixture-shape issues: a test sentinel and legacy returns-impact fixtures that omitted the already-guaranteed production missing_data field. Production validation was not weakened. This SHA remains failed evidence permanently.

### Cancelled intermediate feature SHA

- exact SHA: `fdd90ff6368178bf14896cc2d02f3aa57af90291`
- push Verify #406
- conclusion: cancelled

This SHA has no transferable verification claim. It was superseded by the next fixture-alignment commit.

### Exact final feature-head verification

- branch: `fix/financial-telegram-result-integrity-v722-v730`
- exact SHA: `43404cf36f7753dc9701ba561443d7eb6160d037`
- push Verify #407
- conclusion: success
- tests: 1631 passed / 0 failed
- artifact: `verification-43404cf36f7753dc9701ba561443d7eb6160d037`
- artifact digest: `sha256:b33b6f78e24da61d1b5475ad6aeef87551b8b1c4886440d5b8432aab7ebc7eed`

### PR merge-ref integration verification

- PR #280
- branch head: `43404cf36f7753dc9701ba561443d7eb6160d037`
- synthetic merge SHA: `815f154470ad15a8b000fca072c806b6bf310d10`
- pull_request Verify #408
- conclusion: success
- tests: 1631 passed / 0 failed
- artifact: `verification-815f154470ad15a8b000fca072c806b6bf310d10`
- artifact digest: `sha256:325b6855603b80c8ecec817fd976cf6f05a7edb75c1645ed73bf6a69d475a069`

This is synthetic merge-ref integration evidence only.

### Post-merge exact-main verification

- exact main: `5cf5a9cba19cc0efc171c1eb8d626868bf415d53`
- push Verify #409
- conclusion: success
- tests: 1631 passed / 0 failed
- artifact: `verification-5cf5a9cba19cc0efc171c1eb8d626868bf415d53`
- artifact digest: `sha256:4c439270e095f5e3aab3ec576a45736b387d81720bfe07d73b9ebc94cf9a5070`

## Financial Telegram Result Integrity

The seller-facing Unit Economics and Returns Finance Impact detail cards now validate downstream result contracts before formatting them.

Malformed financial payloads fail closed instead of becoming optimistic success or reaching formatter assumptions. Legitimate incomplete evidence remains visible as incomplete evidence; explicit downstream failures remain failures.

No financial formulas, tax/fee arithmetic, Product Decision rules, persistence owner/layer, Product Task Draft execution, business execution authorization, or Ozon mutation changed. Repository `data/users.json` was not modified.

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled SHAs remain unknown/cancelled evidence and carry no transferable claim.
Workflow/test-manifest evidence is not independent external verification;
`externally_verified=False`.

## Related implementation

- `app/services/assistant_button_handler_service.py`
- `tests/test_financial_telegram_result_integrity_v722_v730.py`
- `project_brain/CURRENT_CHECKPOINT_V722_V730.md`

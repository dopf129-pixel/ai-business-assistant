# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`e793ca7ab241d54a12af8b3b402b1dc862652bf2`

Latest merged production-correctness batch:

`v841-v850: Product Decision User Action Guidance Integrity`

### Entering exact-main verification

- exact main: `84691212706a05be29e31743bd5404277cb63fc2`
- push Verify #528
- conclusion: success
- tests: 1741 passed / 0 failed
- artifact: `verification-84691212706a05be29e31743bd5404277cb63fc2`
- artifact id: 9802404547
- artifact digest: `sha256:1bff07ab41348018ed9805c7e0a8d77dd943383863db46225309bd7f6200c2cf`

### Exact final feature-head verification

- branch: `fix/user-action-guidance-integrity-v841-v850`
- exact SHA: `c1ff6fb75736c24f160191c3397a7691edcb7d5e`
- push Verify #532
- conclusion: success
- tests: 1751 passed / 0 failed
- artifact: `verification-c1ff6fb75736c24f160191c3397a7691edcb7d5e`
- artifact id: 9802519561
- artifact digest: `sha256:edf2330616290278859f346a4de1dc44bd8e3194f5cbfb9ed99f37aa5a21f86b`

### PR merge-ref integration verification

- PR #304
- branch head: `c1ff6fb75736c24f160191c3397a7691edcb7d5e`
- synthetic merge SHA: `0fbb8f396a87abf7067207c76a072757246bc3cd`
- pull_request Verify #533
- conclusion: success
- tests: 1751 passed / 0 failed
- artifact: `verification-0fbb8f396a87abf7067207c76a072757246bc3cd`
- artifact id: 9802580352
- artifact digest: `sha256:440ade25286aa15a27f0f5a6f0a4ec0fcd6e9a8aefbc71c82aadf9658edb2c63`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification

- exact main: `e793ca7ab241d54a12af8b3b402b1dc862652bf2`
- push Verify #534
- conclusion: success
- tests: 1751 passed / 0 failed
- artifact: `verification-e793ca7ab241d54a12af8b3b402b1dc862652bf2`
- artifact id: 9802612102
- artifact digest: `sha256:afc68c56cd08fb90f2d9f9fc3830d8dd2fd965b1bdc0065833499362e07ba1da`

No failed intermediate production SHA occurred in v841-v850.

## Immediately preceding verified product package: v831-v840

- entering exact main `fe4d0c6012cac0d9e770373e0dedaf69b0df1b39`: push Verify #509, 1731 passed / 0 failed
- duplicate branch-creation push on the same entering SHA: Verify #514 cancelled; cancelled evidence only
- exact feature head `0f9faa6b55078bc9391d9ef19a8d7d2348cbf4ae`: push Verify #516, 1741 passed / 0 failed
- PR #302 synthetic merge `97c9f8432fbdd98c6d280226116f6bb2bee8b02d`: Verify #517, 1741 passed / 0 failed
- squash main `a3aa88f351985e8519f754923880165f96fb29ad`: push Verify #518, 1741 passed / 0 failed
- `externally_verified=False`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled SHAs remain cancelled/unknown evidence and carry no transferable claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow/test-manifest evidence is not independent external verification;
`externally_verified=False`.

## Related implementation

- `app/services/product_decision_persistence_verification_service.py`
- `app/product_decision_user_action_guidance.py`
- `tests/test_product_decision_persistence_verification_integrity_v831_v840.py`
- `tests/test_product_decision_user_action_guidance.py`
- `tests/test_product_decision_user_action_guidance_integrity_v841_v850.py`
- `project_brain/CURRENT_CHECKPOINT_V831_V840.md`
- `project_brain/CURRENT_CHECKPOINT_V841_V850.md`

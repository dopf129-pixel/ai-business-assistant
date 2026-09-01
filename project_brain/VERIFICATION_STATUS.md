# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`a3aa88f351985e8519f754923880165f96fb29ad`

Latest merged production-correctness batch:

`v831-v840: Product Decision Persistence Verification Integrity`

### Entering exact-main verification

- exact main: `fe4d0c6012cac0d9e770373e0dedaf69b0df1b39`
- push Verify #509
- conclusion: success
- tests: 1731 passed / 0 failed
- artifact: `verification-fe4d0c6012cac0d9e770373e0dedaf69b0df1b39`
- artifact id: 9801899188
- artifact digest: `sha256:1c9ba218be7c35aa20ae360dd973aa6fd6d43ec2b1bb46e7ddf580818ed03e55`

A later duplicate branch-creation push for this same SHA was cancelled as Verify #514. It remains cancelled evidence and is not used as a successful verification claim.

### Exact final feature-head verification

- branch: `fix/product-decision-persistence-verification-integrity-v831-v840`
- exact SHA: `0f9faa6b55078bc9391d9ef19a8d7d2348cbf4ae`
- push Verify #516
- conclusion: success
- tests: 1741 passed / 0 failed
- artifact: `verification-0f9faa6b55078bc9391d9ef19a8d7d2348cbf4ae`
- artifact id: 9802107650
- artifact digest: `sha256:fead67d0ad3c4389a44abcaab3f4fac8bd9330b3e04ab47c26127943c3d2e103`

### PR merge-ref integration verification

- PR #302
- branch head: `0f9faa6b55078bc9391d9ef19a8d7d2348cbf4ae`
- synthetic merge SHA: `97c9f8432fbdd98c6d280226116f6bb2bee8b02d`
- pull_request Verify #517
- conclusion: success
- tests: 1741 passed / 0 failed
- artifact: `verification-97c9f8432fbdd98c6d280226116f6bb2bee8b02d`
- artifact id: 9802117353
- artifact digest: `sha256:5d809c313b4160cfe74bb012b7bc939eaf23dd998c96adfc224d156e93f11f5e`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification

- exact main: `a3aa88f351985e8519f754923880165f96fb29ad`
- push Verify #518
- conclusion: success
- tests: 1741 passed / 0 failed
- artifact: `verification-a3aa88f351985e8519f754923880165f96fb29ad`
- artifact id: 9802190481
- artifact digest: `sha256:16f7f2a8f5dc96199b0cef399f94a916106fd173c5916a0ebf2dc17714220240`

No failed intermediate production SHA occurred in v831-v840.

## Immediately preceding verified product package: v821-v830

- entering exact main `cc485098da06834f31fcd09430d83bd96b96f1e1`: push Verify #496, 1721 passed / 0 failed
- failed intermediate `41c289221c100ce4dc1462603b42349434f2f406`: push Verify #498, 1730 passed / 1 failed; remains failed evidence
- exact feature head `a0e977595238dd256e9ae0d54e68ac337b04bb91`: push Verify #499, 1731 passed / 0 failed
- PR #299 synthetic merge `c77df0221826e27e444f3d68150419e4adf9bc8d`: Verify #500, 1731 passed / 0 failed
- squash main `c2f1bd3d26fc5e2be33d725b8ecd2898a7b1dbfa`: push Verify #501, 1731 passed / 0 failed
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
- `tests/test_product_decision_persistence_verification_service.py`
- `tests/test_product_decision_persistence_verification_integrity_v831_v840.py`
- `project_brain/CURRENT_CHECKPOINT_V821_V830.md`
- `project_brain/CURRENT_CHECKPOINT_V831_V840.md`

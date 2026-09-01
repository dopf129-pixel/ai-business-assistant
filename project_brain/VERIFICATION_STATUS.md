# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`c788760babc8b0c6becb886f37937f20d5d09028`

Latest merged production-correctness batch:

`v861-v870: Product Decision User Action Completion Evidence Integrity`

### Entering exact-main verification

- exact main: `16d7b3877a5fb2711b793f68a61263452084f49a`
- push Verify #560
- conclusion: success
- tests: 1761 passed / 0 failed
- artifact: `verification-16d7b3877a5fb2711b793f68a61263452084f49a`
- artifact id: 9803278631
- artifact digest: `sha256:3ab00b39a0d91918abb9092eee8c081cc59e0ef953703bfc70746a63733eb842`

### Exact final feature-head verification

- branch: `fix/user-action-completion-evidence-integrity-v861-v870`
- exact SHA: `8db239ac433d4e53ed1850e04275caeb3105ed68`
- push Verify #565
- conclusion: success
- tests: 1771 passed / 0 failed
- artifact: `verification-8db239ac433d4e53ed1850e04275caeb3105ed68`
- artifact id: 9803396100
- artifact digest: `sha256:d611a948c8b35731dd44e1a46a192142aa198171a2022a54c72234902ecefe9b`

### PR merge-ref integration verification

- PR #308
- branch head: `8db239ac433d4e53ed1850e04275caeb3105ed68`
- synthetic merge SHA: `948c653b686e7b794ee389c1f51085fb3545da38`
- pull_request Verify #566
- conclusion: success
- tests: 1771 passed / 0 failed
- artifact: `verification-948c653b686e7b794ee389c1f51085fb3545da38`
- artifact id: 9803428303
- artifact digest: `sha256:31ce08240519b894ea6052170d0c12ac278e00f91e982f09f9248bf6fe4cf61b`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification

- exact main: `c788760babc8b0c6becb886f37937f20d5d09028`
- push Verify #567
- conclusion: success
- tests: 1771 passed / 0 failed
- artifact: `verification-c788760babc8b0c6becb886f37937f20d5d09028`
- artifact id: 9803461966
- artifact digest: `sha256:01d6fc85c52f2e6783ccf9b073d3bf8bb2d0118affb762a713a5d68908919f2f`

No failed intermediate production SHA occurred in v861-v870.

## Immediately preceding verified product package: v851-v860

- entering exact main `4a8978f55739f652b86aa45ad314fa8c0a7f0422`: push Verify #544, 1751 passed / 0 failed
- exact feature head `349e441c659c2965195a3af4801af3050e8893ca`: push Verify #548, 1761 passed / 0 failed
- PR #306 synthetic merge `4c0ebaad1691332f9a44871ce1f4fc8cfa52449f`: Verify #549, 1761 passed / 0 failed
- squash main `405fdea64008e21173e7851e8b370b63eae7ef73`: push Verify #550, 1761 passed / 0 failed
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

- `app/product_decision_user_action_checklist.py`
- `app/product_decision_user_action_completion_evidence.py`
- `tests/test_product_decision_user_action_checklist_integrity_v851_v860.py`
- `tests/test_product_decision_user_action_completion_evidence.py`
- `tests/test_product_decision_user_action_completion_evidence_integrity_v861_v870.py`
- `project_brain/CURRENT_CHECKPOINT_V851_V860.md`
- `project_brain/CURRENT_CHECKPOINT_V861_V870.md`

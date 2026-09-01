# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`b492b655030791d5e703c8aa607d2763d455e486`

Latest merged production-correctness batch:

`v921-v930: Product Decision User Action Learning Summary Outcome Integrity`

### Entering exact-main verification

- exact main: `e2ef005467f19ac0132ec40e970df05b602e7d03`
- push Verify #638
- conclusion: success
- tests: 1821 passed / 0 failed
- artifact id: 9812332465
- digest: `sha256:739c516ee855755bfe6ecae094862b3d5fe3b753198b3afd7daaa729faf103ae`

### Failed intermediate feature SHA

- exact SHA: `21051b20acdfc0036a15d875d01b488283791ff3`
- push Verify #640
- conclusion: failure
- tests: 1830 passed / 1 failed
- artifact id: 9812424367
- digest: `sha256:de655633e3055c7c97baaaa9630b54cb3f3a2d21b0df27e81d9101f43f5057d3`
- failure occurred in the v926 regression helper before production builder execution; remains failed evidence.

### Exact final feature-head verification

- exact SHA: `9f33708a8d4db6b80bad880c561ea9d92b504698`
- push Verify #641
- conclusion: success
- tests: 1831 passed / 0 failed
- artifact id: 9812469585
- digest: `sha256:f5a8599761e3705b0df4205695ca69cf428e3d52fae20391cfd28d39244ebfa6`

### PR merge-ref integration verification

- PR #320
- synthetic merge SHA: `bbce7d398060c0ec96be84dc8dd10b85ff56495d`
- pull_request Verify #642
- conclusion: success
- tests: 1831 passed / 0 failed
- artifact id: 9812499572
- digest: `sha256:83e3bc0c79500bd41c16da5076e274384cf8add9b7ffd5a524c1649bf9247719`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification

- exact main: `b492b655030791d5e703c8aa607d2763d455e486`
- push Verify #643
- conclusion: success
- tests: 1831 passed / 0 failed
- artifact id: 9812533575
- digest: `sha256:3ee895465fbbaea300bcb0c8e717cd21fe48fe0f53a540274900056a9b611033`

## Immediately preceding verified product package: v911-v920

- exact feature `e16dff8f6cc058f4a5725c8139dcd03ec63b71c5`: Verify #632, 1821 passed / 0 failed
- PR #318 synthetic merge `f2534a7946eacd94067ab8be5ca3f1340b30beaf`: Verify #633, 1821 passed / 0 failed
- squash main `82867cd9efb6a0b4a187d72ca097ee6bda0c0f39`: Verify #634, 1821 passed / 0 failed
- `externally_verified=False`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs remain cancelled/pending evidence and carry no transferable claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow/test-manifest evidence is not independent external verification;
`externally_verified=False`.

## Related implementation

- `app/product_decision_user_action_learning_summary.py`
- `tests/test_product_decision_user_action_learning_summary.py`
- `tests/test_product_decision_user_action_learning_summary_integrity_v921_v930.py`
- `project_brain/CURRENT_CHECKPOINT_V911_V920.md`
- `project_brain/CURRENT_CHECKPOINT_V921_V930.md`

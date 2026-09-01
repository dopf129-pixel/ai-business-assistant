# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`c7c864814ec609b0f2c58b4578a522b2e5e8dad1`

Latest merged production-correctness batch:

`v901-v910: Product Decision User Action Post-Decision Observation Lineage Integrity`

### Entering exact-main verification

- exact main: `157e4db46c6a35ed2dbe9415c0daeb8a77cc2ed5`
- push Verify #620
- conclusion: success
- tests: 1801 passed / 0 failed
- artifact id: 9811196220
- digest: `sha256:00681579472557b22837ce68ebc62f187213ccf31d2623b86da6fdb701abf225`

### Failed intermediate feature SHA

- exact SHA: `0896d8112971966aec9fb61c7a2250436f19d76a`
- push Verify #623
- conclusion: failure
- tests: 1804 passed / 7 failed
- artifact id: 9811289555
- digest: `sha256:56f366de5a4f461f70fdcd8414a9d9b7615b2c0e3a6dc7dcd092802b1d2fdbef`
- historical v811-v820 fixture incompatibility; remains failed evidence.

### Exact final feature-head verification

- exact SHA: `9bf89d1fc58464ccd985bf18190632ea180fe75d`
- push Verify #624
- conclusion: success
- tests: 1811 passed / 0 failed
- artifact id: 9811326005
- digest: `sha256:c8d9404ead30c91a628ba5ca82f27f95932ab1769a9659ff744c3c35e48660c0`

### PR merge-ref integration verification

- PR #316
- synthetic merge SHA: `ee70ea2e581743b3a8ebfbf9446ffb535e109836`
- pull_request Verify #625
- conclusion: success
- tests: 1811 passed / 0 failed
- artifact id: 9811358474
- digest: `sha256:a629d355fc5de5c05e16c7cd51c808c25057f81e516489f404f857a1b916fbf8`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification

- exact main: `c7c864814ec609b0f2c58b4578a522b2e5e8dad1`
- push Verify #626
- conclusion: success
- tests: 1811 passed / 0 failed
- artifact id: 9811391089
- digest: `sha256:c60a3f81cb67ad64290f6ef038ae87f35d58ff68d6b0912b9bbfd2947a5359eb`

## Immediately preceding verified product package: v891-v900

- exact feature head `681d42d44b718f7c0679c350971b71062567cafd`: push Verify #614, 1801 passed / 0 failed
- PR #314 synthetic merge `12dd9e8a9372b33ba2f6d866344427e329a622ae`: Verify #615, 1801 passed / 0 failed
- squash main `3dec82f8aa93c1a35a699aa9270dcfd8e91c1f46`: push Verify #616, 1801 passed / 0 failed
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

- `app/product_decision_user_action_post_decision_observation.py`
- `tests/test_product_decision_user_action_post_decision_observation.py`
- `tests/test_product_decision_user_action_post_decision_observation_integrity_v811_v820.py`
- `tests/test_product_decision_user_action_post_decision_observation_integrity_v901_v910.py`
- `project_brain/CURRENT_CHECKPOINT_V891_V900.md`
- `project_brain/CURRENT_CHECKPOINT_V901_V910.md`

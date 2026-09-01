# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`10977368ac4179f1f7168943a38fcdbc01ecfd78`

Latest merged production-correctness batch:

`v961-v970: Product Decision History Context Result Integrity`

### Entering exact-main verification

- exact main: `40f1a28b3515a07879bda369800b65dea8998f7f`
- push Verify #672
- conclusion: success
- tests: 1861 passed / 0 failed
- artifact id: 9813910089
- digest: `sha256:f18af8ad2031e5d3da93b11c81f4d65cf949a691d0933fec3ef4581945d017b9`

### Failed intermediate feature verification

- exact SHA: `bfcc3551166431288f38ba0c06912133bed56818`
- push Verify #674
- conclusion: failure
- tests: 1870 passed / 1 failed
- artifact id: 9814044437
- digest: `sha256:e0edfc47ee933e8869dbb76ed0df3ca5a2ba4ba4b2d392e469c21a42ea3c82fc`
- failure: undeclared `deepcopy` in new Telegram draft-copy path
- this SHA remains failed evidence permanently

### Exact final feature-head verification

- exact SHA: `ab24a87c19072b5bbb3b9efd6b1630b513bf6645`
- push Verify #675
- conclusion: success
- tests: 1871 passed / 0 failed
- artifact id: 9814074739
- digest: `sha256:5177dc9c3d210ea8f51af5fbf9ddd7633b8c3dc8c7e8f834c75ea68439a58ca0`

### PR merge-ref integration verification

- PR #328
- synthetic merge SHA: `85e808a3dcc04ef9197bc673950546445ee15749`
- pull_request Verify #676
- conclusion: success
- tests: 1871 passed / 0 failed
- artifact id: 9814104003
- digest: `sha256:4bf39ea34acf67aa9d2b71d014f9537e4dfbd2ee05d9bb664ca774fab0a004de`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification

- exact main: `10977368ac4179f1f7168943a38fcdbc01ecfd78`
- push Verify #677
- conclusion: success
- tests: 1871 passed / 0 failed
- artifact id: 9814938009
- digest: `sha256:3d0e611601682145f91855cec93724cc9d13b5b241b69e2f1856ad1046996e36`

## Immediately preceding verified product package: v951-v960

- feature `70cbcc825fc49ab868ae1ac3c58ff80ea115482a`: Verify #666, 1861 passed / 0 failed
- PR #326 synthetic `4b8792f73e6f54836d358b4c0215d885d40c2a93`: Verify #667, 1861 passed / 0 failed
- squash main `7637177202c21d3f2894105e39137efd86855b8c`: Verify #668, 1861 passed / 0 failed
- `externally_verified=False`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs remain cancelled/pending evidence and carry no transferable claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`db5ab92503f499dfe470402ffefc00b15b9c6e59`

Latest merged production-correctness batch:

`v971-v980: Unit Economics Returns Finance Impact Integrity`

### Entering exact-main verification

- exact main: `e606b5020a1300ebb7d5b2edadaa1374d0eaf611`
- push Verify #681
- conclusion: success
- tests: 1871 passed / 0 failed
- artifact id: 9815103598
- digest: `sha256:1931c13743fbaa3d0d670716de4e3d86cba3f5607bcb8139a7849216af2b4853`

### Failed intermediate feature verification

- exact SHA: `b4f0d33d163ee0a81d0252e466519169c55fd1f2`
- push Verify #683
- conclusion: failure
- tests: 1880 passed / 1 failed
- artifact id: 9815323464
- digest: `sha256:56edcc6a74df4a8c97297a7c456f369ff0c9bf7b6f770e2d9524d1c55034b8fa`
- failure: legacy cache fixture used a pre-contract minimal returns-success shape
- production validation was not weakened
- this SHA remains failed evidence permanently

### Exact final feature-head verification

- exact SHA: `0a2ece03b60e019b264b5ecda8a010bca873e7bb`
- push Verify #684
- conclusion: success
- tests: 1881 passed / 0 failed
- artifact id: 9815370444
- digest: `sha256:5671759b8dea4e185f9672a0779f72dbe89e6a60ee371c22c284239e673f361a`

### PR merge-ref integration verification

- PR #330
- synthetic merge SHA: `d8e9c3f5fb978cb4ae2d3675d229ad6bbc48b358`
- pull_request Verify #685
- conclusion: success
- tests: 1881 passed / 0 failed
- artifact id: 9815412044
- digest: `sha256:aa4ada489199dc8cbe616ebd9ac501d1bcc06a6cc154b4cc8b12954a959b618d`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification

- exact main: `db5ab92503f499dfe470402ffefc00b15b9c6e59`
- push Verify #686
- conclusion: success
- tests: 1881 passed / 0 failed
- artifact id: 9815447690
- digest: `sha256:e15ff5518e3cb2d337eec320d5e16dd30d790a7455b2d5470f5c165c3b6f9371`

## Immediately preceding verified product package: v961-v970

- feature `ab24a87c19072b5bbb3b9efd6b1630b513bf6645`: Verify #675, 1871 passed / 0 failed
- PR #328 synthetic `85e808a3dcc04ef9197bc673950546445ee15749`: Verify #676, 1871 passed / 0 failed
- squash main `10977368ac4179f1f7168943a38fcdbc01ecfd78`: Verify #677, 1871 passed / 0 failed
- failed intermediate `bfcc3551166431288f38ba0c06912133bed56818`: Verify #674, 1870 passed / 1 failed
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

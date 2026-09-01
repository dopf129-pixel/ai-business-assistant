# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`7637177202c21d3f2894105e39137efd86855b8c`

Latest merged production-correctness batch:

`v951-v960: Product Decision Action Proposal Result Integrity`

### Entering exact-main verification

- exact main: `2c0e9fcce68a25c3518ff8cdb134470bed73e25d`
- push Verify #664
- conclusion: success
- tests: 1851 passed / 0 failed
- artifact id: 9813494352
- digest: `sha256:b179cdf1117a663888430b4a7de3f9aa3549e0f807cdfe30812c710ccd7c3531`

### Exact final feature-head verification

- exact SHA: `70cbcc825fc49ab868ae1ac3c58ff80ea115482a`
- push Verify #666
- conclusion: success
- tests: 1861 passed / 0 failed
- artifact id: 9813694083
- digest: `sha256:f589a96e408596b8e64294a9608185dd366fb503c0b42050bf22fbcf208fe4d1`

### PR merge-ref integration verification

- PR #326
- synthetic merge SHA: `4b8792f73e6f54836d358b4c0215d885d40c2a93`
- pull_request Verify #667
- conclusion: success
- tests: 1861 passed / 0 failed
- artifact id: 9813722308
- digest: `sha256:c3283632626262262c73c92e37b3dc5fe6dcad802536169c3a903d2060756602`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification

- exact main: `7637177202c21d3f2894105e39137efd86855b8c`
- push Verify #668
- conclusion: success
- tests: 1861 passed / 0 failed
- artifact id: 9813762224
- digest: `sha256:34ccac02b0cbf26e1a8aa67b90d08b572d7076583a4929c796f9a4c49aa95c63`

No failed intermediate production SHA occurred in v951-v960.

## Immediately preceding verified product package: v941-v950

- feature `8aa3a6b6205517c3eb9754976a1140f9633b5220`: Verify #658, 1851 passed / 0 failed
- PR #324 synthetic `7e227b17869617711a3f8b277900674eba383745`: Verify #659, 1851 passed / 0 failed
- squash main `0671c0a0b06c662e935b4dcbf00e4cad12e32175`: Verify #660, 1851 passed / 0 failed
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

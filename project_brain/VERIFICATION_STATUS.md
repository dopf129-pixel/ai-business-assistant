# Verification Status

Date: 2026-09-03

## Latest verified product baseline

`0ca4d226f3f75e2b20035a87a13b1a10d6c71581`

Latest merged production-correctness batch:

`v1151-v1160: Period Profit Summary Input & Result Integrity`

### Entering exact-main verification
- exact main: `de6f514426b3ed887446fc0003efcad708c637d1`
- Verify #845
- 2051 passed / 0 failed
- artifact id: 9852645793
- digest: `sha256:86e7a456ed42180ed37e2b432ac40aa2db15a52d9db7f558b6381122ba29553f`

### Exact final feature-head verification
- exact SHA: `4ab53fe054504c633fbcd6fb708ccb7dc557eaa4`
- Verify #847
- 2061 passed / 0 failed
- artifact id: 9852891478
- digest: `sha256:f74260f869cd01d6ec59c17bd183d4eda80dabb0cdf0a51347d662f7b6ac0c49`

### PR merge-ref integration verification
- PR #367
- synthetic SHA: `a9030acff2031b118c0c0600c008804c3d6ff08a`
- Verify #848
- 2061 passed / 0 failed
- artifact id: 9852935558
- digest: `sha256:a66d3d8aebb72039c9305583ea390f8ed599410011671b36c6e34fc99fc9bd1f`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `0ca4d226f3f75e2b20035a87a13b1a10d6c71581`
- Verify #849
- 2061 passed / 0 failed
- artifact id: 9852981757
- digest: `sha256:ba05065a96af339ea3f49dfb08115c15556e478be099460657f23e3f6f1d5543`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

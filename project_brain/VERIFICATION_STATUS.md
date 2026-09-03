# Verification Status

Date: 2026-09-03

## Latest verified product baseline

`e66125d5e2c737497762178bef86dd36a62721f3`

Latest merged production batch:

`v1231-v1240: Finance Accrual Pagination & Read Session Integrity`

### Entering exact-main verification
- exact main: `400ca040d743dc7db93480605ebd62a7fe9b02f3`
- Verify #984
- 2131 passed / 0 failed
- artifact id: 9887796288
- digest: `sha256:8081f8fc794c49b95c4012940e030db7cac46d5a7560d622c14f02086f821313`

### Failed intermediate evidence
- exact SHA: `8d159ed09410ed978bef6cfdb5719a67bc5491b1`
- Verify #990
- 2140 passed / 1 failed
- artifact id: 9888518874
- digest: `sha256:428c75b168488fa3f7c415751d2622917aee6d32c4474e2c8da7ada5757fde81`
- failure was test-only: a new test required a raw Ozon success response to contain an `error` key.

This SHA remains failed evidence permanently.

### Exact final feature-head verification
- exact SHA: `ad215b8d86c547e740dcb3583e7b7f580e9fb823`
- Verify #991
- 2141 passed / 0 failed
- artifact id: 9888545229
- digest: `sha256:64a52c5115d3ebd12f0988c0c36ae2b04e11463b56ec4c9d792b93e5bc2d832c`

### PR merge-ref integration verification
- PR #383
- synthetic SHA: `4b1f8e48de3f92c6aecc590232697890c8814d08`
- Verify #992
- 2141 passed / 0 failed
- artifact id: 9888577950
- digest: `sha256:1eb510792dc9693d39d425ed1b178f113dffa4ee9a054ab518a2a18c73981d92`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `e66125d5e2c737497762178bef86dd36a62721f3`
- Verify #993
- 2141 passed / 0 failed
- artifact id: 9888609599
- digest: `sha256:c42afb3d6c2beb970d7e46a610abf0c59be8712482fdc6b5eee05c525da32cee`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is project CI evidence only;
`externally_verified=False`.

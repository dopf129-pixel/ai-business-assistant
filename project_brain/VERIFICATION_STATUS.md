# Verification Status

Date: 2026-09-02

## Latest verified product baseline

`cb0148a1d6ad14b2e53f18ca948b66e8422da3c4`

Latest merged production-correctness batch:

`v1111-v1120: Advertising & Expense Finite Result Integrity`

### Entering exact-main verification
- exact main: `7187f6bea4392e844d9eebb928e94f13f5e39605`
- Verify #808
- 2011 passed / 0 failed
- artifact id: 9846215572
- digest: `sha256:95ce9b3d2737ea39c67720f227564d3ddbd9831a570a854e64dbe8c9419e8792`

### Exact final feature-head verification
- exact SHA: `c45284c99d70a45b1bed2b5f62049a7bb5c40df6`
- Verify #810
- 2021 passed / 0 failed
- artifact id: 9848781279
- digest: `sha256:b6f250911b452fe6b92a526efec659ee8388e8936828849fe3abbf41d8af979b`

### PR merge-ref integration verification
- PR #358
- synthetic SHA: `8b8bcfda3b61518637637a05b1b60109a7907192`
- Verify #811
- 2021 passed / 0 failed
- artifact id: 9848820350
- digest: `sha256:6fa1884772e1bc3a1e019ace4126366919d49e1e2f697d38540163d2ff986ba7`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `cb0148a1d6ad14b2e53f18ca948b66e8422da3c4`
- Verify #812
- 2021 passed / 0 failed
- artifact id: 9848865274
- digest: `sha256:0af16c631508c7df09c53de4397ba44e776e568af9e44199ccca338ae41fab38`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

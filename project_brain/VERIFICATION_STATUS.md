# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`70466d338951b2b7cc2bb7c48a9d2c7ee2dc91df`

Latest merged production-correctness batch:

`v1021-v1030: Product Decision Operational Metrics Result Integrity`

### Entering exact-main verification
- exact main: `19c43dfae47df01e733d710f7793e54436fc99fb`
- Verify #731
- 1921 passed / 0 failed
- artifact id: 9819033423
- digest: `sha256:7c40cd27691398369e362a4c2c6c6ed7d2eb3be6d648d2a426dcc4737c109b89`

### Failed intermediate verification
- exact SHA: `678739dea2fa85af3f71933f048f9bfb193fdc62`
- Verify #733
- 1929 passed / 2 failed
- artifact id: 9820082230
- digest: `sha256:6273094ec34e0f137f34150b0faa8de56a05fd84139a168182fc62463bc1d3d6`

This SHA remains failed evidence permanently.

### Exact final feature-head verification
- exact SHA: `6af041c39b86791821249058d0632070f2f68685`
- Verify #734
- 1931 passed / 0 failed
- artifact id: 9820119946
- digest: `sha256:944e125073a632050d3a9754cf5c4d3f9eee8d08b20d50477d274c9f2dc60851`

### PR merge-ref integration verification
- PR #340
- synthetic SHA: `7e64fcd23df9fb405c8c422359e3703b6a720f56`
- Verify #735
- 1931 passed / 0 failed
- artifact id: 9820146443
- digest: `sha256:a5c05914cedd5e433179fee0109208032616de8d2920241b4f642d5f15d6138e`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `70466d338951b2b7cc2bb7c48a9d2c7ee2dc91df`
- Verify #736
- 1931 passed / 0 failed
- artifact id: 9820173379
- digest: `sha256:617e8d058dbce91302226a2b26f48761b4ebafe5cd5ddd54560c22f962ed4d70`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

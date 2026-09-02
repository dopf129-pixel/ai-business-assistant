# Verification Status

Date: 2026-09-02

## Latest verified product baseline

`dbec4ecfc5f38b31aeba5e86a6d0ad09c40d58bb`

Latest merged production-correctness batch:

`v1061-v1070: Telegram Verified Product Decision Guidance / Checklist Wiring`

### Entering exact-main verification
- exact main: `283ec42d4bb2b9c831801d9155caa3e6c582370f`
- Verify #766
- 1961 passed / 0 failed
- artifact id: 9821793575
- digest: `sha256:a7b53b44bd2e5f54377a43c4f8a1bfeb964ceb5885f9809bff9079376e9c36a3`

### Failed intermediate verification
- exact SHA: `f449e7d738b56fb72f39e0836eb2ea3464b899a9`
- Verify #768
- 1970 passed / 1 failed
- artifact id: 9821944714
- digest: `sha256:fee8b3f4e5fcdf83bbea3a81851a25e999b3d2c7e7918637783fe9870ccd40a6`

This SHA remains failed evidence permanently.

### Exact final feature-head verification
- exact SHA: `09abed3a9db1c1cf90a13d4393bb3771f09c964d`
- Verify #769
- 1971 passed / 0 failed
- artifact id: 9821981082
- digest: `sha256:f42a8378a8f9de0bee3533cad6b28e07770734de93ffb2ed30cd490fabbff090`

### PR merge-ref integration verification
- PR #348
- synthetic SHA: `400bbfa95038edd3876a2ea0eb4b2e28db65fefb`
- Verify #770
- 1971 passed / 0 failed
- artifact id: 9822010368
- digest: `sha256:45c355a300615b37be6193a159342f715a173bc0831ff510931919086405800c`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `dbec4ecfc5f38b31aeba5e86a6d0ad09c40d58bb`
- Verify #771
- 1971 passed / 0 failed
- artifact id: 9822044261
- digest: `sha256:6e9aeaa7de76ee1a29edd23f038516c8a1abaed0618aa29d06a8d2e8ec7690ac`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

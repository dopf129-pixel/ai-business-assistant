# Verification Status

Date: 2026-09-02

## Latest verified product baseline

`0f484141713f2452f451e818caf600d113df6ad4`

Latest merged production-correctness batch:

`v1081-v1090: Financial Telegram Query Exception Containment`

### Entering exact-main verification
- exact main: `45dbac5728d406e8cf463b2754d81e11a9a631ec`
- Verify #784
- 1981 passed / 0 failed
- artifact id: 9843911559
- digest: `sha256:67403be1a76fc02ddc58c9b5150b123a962bbf9f56054195e2702bb2577eba83`

### Exact final feature-head verification
- exact SHA: `6cf579771939ceb765a996fa761a406175e003d3`
- Verify #786
- 1991 passed / 0 failed
- artifact id: 9844000230
- digest: `sha256:14235f04653929858f72b31c4ff71bf7dc70a282f2911173e44a88db3d8340fc`

### PR merge-ref integration verification
- PR #352
- synthetic SHA: `69383b1fcfe87aab31dfb6bb29cd4f73bf051e13`
- Verify #787
- 1991 passed / 0 failed
- artifact id: 9844035985
- digest: `sha256:053bb90d398e410a6ff4c8fda33fbcffa7d4a417c6c94daab96266377beda7b5`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `0f484141713f2452f451e818caf600d113df6ad4`
- Verify #788
- 1991 passed / 0 failed
- artifact id: 9844081811
- digest: `sha256:165ca2b0cf1ee918561521e22ad6f0e0615c0ea5c4092be697880a780653c92e`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

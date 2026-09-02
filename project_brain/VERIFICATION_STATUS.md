# Verification Status

Date: 2026-09-02

## Latest verified product baseline

`d1655adf6719e6000f996b4635253c6b99193ba3`

Latest merged production-correctness batch:

`v1141-v1150: Finance Period Aggregation Result Integrity`

### Entering exact-main verification
- exact main: `567a1b7e67e78553d78a02511fc2866c315bdb84`
- Verify #832
- 2041 passed / 0 failed
- artifact id: 9850631816
- digest: `sha256:4f3943a7606ac235967fcbc986847bc25e68afda7e224cb8510a42c3d34120d9`

### Failed intermediate feature evidence
- exact SHA: `f54132ebf109240242a87037a81b1db5ed052d5b`
- Verify #834
- 2050 passed / 1 failed
- artifact id: 9850859003
- digest: `sha256:d77c828d7efb59395c49ebdd57653bcbf310895019ce710c060db18ac95a1d05`
- root cause: test-only false positive from matching `nan` inside `finance`; this SHA remains failed evidence permanently.

### Exact final feature-head verification
- exact SHA: `52661a7c37068759d20797644943a3b9e5e5ebcc`
- Verify #835
- 2051 passed / 0 failed
- artifact id: 9852038669
- digest: `sha256:87a2b36f89567cb55665f074c5dc72a9184a6d29c8acbbeca97276e195e32a99`

### PR merge-ref integration verification
- PR #364
- synthetic SHA: `ef001cc855661041bd3987604496d03e55acaf30`
- Verify #836
- 2051 passed / 0 failed
- artifact id: 9852074846
- digest: `sha256:8fb5141ab367708ae19f8a4c7c93e239c3982718ee7f29ad1f6cc3fbb3e5b866`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `d1655adf6719e6000f996b4635253c6b99193ba3`
- Verify #837
- 2051 passed / 0 failed
- artifact id: 9852118814
- digest: `sha256:81af0f0d117f40de5532cbb9a6d45878192ff651a2107a6d7090ec90c02adaf6`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

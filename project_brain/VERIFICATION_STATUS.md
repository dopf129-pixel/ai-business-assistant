# Verification Status

Date: 2026-09-03

## Latest verified product baseline

`c1c3da7cb69d6ce2af550e57bc6c5e38a0bb8a89`

Latest merged production batch:

`v1191-v1200: Period Profit Returns Protobuf Timestamp Compatibility`

### Entering exact-main verification
- exact main: `d3f32e2ca2e30192a59c4551cf5633dfa0941ec6`
- Verify #912
- 2091 passed / 0 failed
- artifact id: 9885058169
- digest: `sha256:bf3cdceb80d889184a9e856b301cc6cf17a4dabe0a74b7f27402be987a4b8071`

### Exact final feature-head verification
- exact SHA: `9e2c5b27a1df9f32c8e950766abc809ba93f7976`
- Verify #918
- 2101 passed / 0 failed
- artifact id: 9885588430
- digest: `sha256:b4d51f1a5df4889e9f068732ed744a98660ae15fb45900827acb1679990e2e6c`

### PR merge-ref integration verification
- PR #375
- synthetic SHA: `86bc4a07477e910fcaf56a1a1b908fa28a4a68f5`
- Verify #919
- 2101 passed / 0 failed
- artifact id: 9885621112
- digest: `sha256:10cb2f8e871457a75fcd666b4f873c6fc45746d5efe95f463d93ac9f18d07973`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `c1c3da7cb69d6ce2af550e57bc6c5e38a0bb8a89`
- Verify #920
- 2101 passed / 0 failed
- artifact id: 9885660481
- digest: `sha256:bc16fce014476d23c6ead3d2435b199ae2ce48af108dfa64501eed3ba82c7dc6`

No failed production SHA occurred in v1191-v1200.

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is project CI evidence only;
`externally_verified=False`.

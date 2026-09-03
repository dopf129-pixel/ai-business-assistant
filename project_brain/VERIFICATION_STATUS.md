# Verification Status

Date: 2026-09-03

## Latest verified product baseline

`d845c7183ef5a914853a15b788e18b0cebfd1c93`

Latest merged production batch:

`v1251-v1260: Return COGS Recovery Evidence`

### Entering exact-main verification
- exact main: `55942648266e9ca4fbb3d3380180c3a67bfc4c56`
- Verify #1022
- 2151 passed / 0 failed
- artifact id: 9892287935
- digest: `sha256:ed019db51ad4ac1660271bf36ff514010c02f507b85ebd95bea0057738b1396b`

### Failed intermediate evidence
- exact SHA: `2339d8aa8da1ec43c3298be2da8506a1e6dd8b9b`
- Verify #1033
- 2159 passed / 2 failed
- artifact id: 9894124132
- digest: `sha256:aebeb9bd10d18a552aad913ac6389952dc54b96735ced94417e31777f3d4706b`
- failures were test-contract issues only.

This SHA remains failed evidence permanently.

### Exact final feature-head verification
- exact SHA: `30f3edafd9d2af603f2277701cb13492a334dd30`
- Verify #1038
- 2161 passed / 0 failed
- artifact id: 9894214090
- digest: `sha256:1a438369ed77017cfb871ed31b8e4e6a8f1645789088bab1c0f792d0b1aaa1c3`

### PR merge-ref integration verification
- PR #387
- synthetic SHA: `c5947439450297dabb353b3dfd125e3fc6417576`
- Verify #1039
- 2161 passed / 0 failed
- artifact id: 9894260067
- digest: `sha256:4395fe30324b1557496fd20f3bbeea103e3629581bd988144ded0bec7e03ac63`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `d845c7183ef5a914853a15b788e18b0cebfd1c93`
- Verify #1040
- 2161 passed / 0 failed
- artifact id: 9894294668
- digest: `sha256:a32f8b63ef84938477d4852fe0fcd0104206a38ae8962fa789926a3674dc94f6`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is project CI evidence only;
`externally_verified=False`.

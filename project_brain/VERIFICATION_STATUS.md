# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`19851b9d40827b3ca5e3889c3858ca32c5602f67`

Latest merged production-correctness batch:

`v1041-v1050: Product Decision Durable Application Lineage`

### Entering exact-main verification
- exact main: `835b710e2ad7ad37f8b27415064a6900bcb36ada`
- Verify #749
- 1941 passed / 0 failed
- artifact id: 9820823725
- digest: `sha256:26594c818d43ced50ab12e62a1ff5862f87b9f40e0e0b4bbfdacd83a54d9f4c7`

### Failed intermediate verification
- exact SHA: `cfeb3528d5f902625819b6897db192bf794fddda`
- Verify #751
- 1915 passed / 36 failed
- artifact id: 9821284999
- digest: `sha256:094c2a223c66afa81f078f606f72c6de0ab6ea594c3d9198ee33e8f9eaa94ca1`

This SHA remains failed evidence permanently.

### Exact final feature-head verification
- exact SHA: `5e856591925d2288db871ac9632eab5ee7f7a649`
- Verify #752
- 1951 passed / 0 failed
- artifact id: 9821304515
- digest: `sha256:98b8cba6e7a80c1063c53de00f9b60aa989a4c6e181af95ddc8b51f0eb81bbfb`

### PR merge-ref integration verification
- PR #344
- synthetic SHA: `13f8cb191c24eb0589cf4f5ba892d7b13b402bc5`
- Verify #753
- 1951 passed / 0 failed
- artifact id: 9821329483
- digest: `sha256:381635fc6256628f30de341e4c4f2d95b5418cf758120a7802a99f46b3b52ebd`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `19851b9d40827b3ca5e3889c3858ca32c5602f67`
- Verify #754
- 1951 passed / 0 failed
- artifact id: 9821356516
- digest: `sha256:f23470a2f0ab528fe64569dd7b8e7bcb3fcfee9ff8e783900ffbc3337f6b3317`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

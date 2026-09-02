# Verification Status

Date: 2026-09-02

## Latest verified product baseline

`38e54ddc6d289f0f75121cc63efa0268ef2784f8`

Latest merged production-correctness batch:

`v1091-v1100: Tax Configuration Persistence & Result Integrity`

### Entering exact-main verification
- exact main: `5b2e3ddcc579da318685f3eea4d730119a27f6e9`
- Verify #792
- 1991 passed / 0 failed
- artifact id: 9844280616
- digest: `sha256:c642dfd52b1e678cc8939c46f757204cdb1344b475562a389fef02237bfda968`

### Exact final feature-head verification
- exact SHA: `8cc003f6fa66eb499c67d7d3d74f90c0c75abecf`
- Verify #794
- 2001 passed / 0 failed
- artifact id: 9845404869
- digest: `sha256:b5fbdff88ec8df18c47b60b0ede4742010b5d9fcc481d3eaba784d24a1a2c364`

### PR merge-ref integration verification
- PR #354
- synthetic SHA: `5167b644bc53edc27a40c7b15c7068e0c669d2fc`
- Verify #795
- 2001 passed / 0 failed
- artifact id: 9845447757
- digest: `sha256:179121b28a8375c804e9a6d63ba8f30155d473cd9d25a9373b5117f3f58db4df`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `38e54ddc6d289f0f75121cc63efa0268ef2784f8`
- Verify #796
- 2001 passed / 0 failed
- artifact id: 9845488004
- digest: `sha256:a5c706c2d9e0f3613a9129506b2ae9fc1d66acbb57d1f3ec21fd06cd64ede38e`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`b0bfdd5dd79349244ceaf64d1d4df9899211344a`

Latest merged production-correctness batch:

`v1051-v1060: Product Decision Read-Only Persistence Verification`

### Entering exact-main verification
- exact main: `6241ecaeeeae9e2a3cc31f6a5406dd3e9f051933`
- Verify #758
- 1951 passed / 0 failed
- artifact id: 9821483471
- digest: `sha256:f16754b449d117884a87cdbad3c476c27f19ddfa99a4f8c6019652f561d64ece`

### Exact final feature-head verification
- exact SHA: `c0da07cbafeb1fe38001729eebca94648149d96b`
- Verify #760
- 1961 passed / 0 failed
- artifact id: 9821587270
- digest: `sha256:ae830adf4821e4c3f2d3a9f1ae23a6fd78792658a5a7cfd2bea4e5cb6f56460d`

### PR merge-ref integration verification
- PR #346
- synthetic SHA: `0ccae174a2adfe5c650ca96bf7dcf90ceafaec80`
- Verify #761
- 1961 passed / 0 failed
- artifact id: 9821612474
- digest: `sha256:a6f1580e2bfbe2e54189c3e7b82585594606a9b26e2267621d8b1089c29a69dc`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `b0bfdd5dd79349244ceaf64d1d4df9899211344a`
- Verify #762
- 1961 passed / 0 failed
- artifact id: 9821639408
- digest: `sha256:d4af24b29a66591efc4b5336c07d352cec822b12de36351ea9b0b04431c08030`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

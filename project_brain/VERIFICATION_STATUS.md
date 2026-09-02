# Verification Status

Date: 2026-09-02

## Latest verified product baseline

`87c95cf2eb139cd8782d8df79d43b2313939bba0`

Latest merged production-correctness batch:

`v1121-v1130: Store Profit Aggregation Result Integrity`

### Entering exact-main verification
- exact main: `e6845f71db21baebe526db78405bec5bd0f641a8`
- Verify #816
- 2021 passed / 0 failed
- artifact id: 9849222849
- digest: `sha256:72963293649cc86a6e189e95abf3f398b06080ef137db7044f030c43b2a092ec`

### Exact final feature-head verification
- exact SHA: `a888d3c4aa35aaba7526df186bfdbdd2902f9369`
- Verify #818
- 2031 passed / 0 failed
- artifact id: 9849428477
- digest: `sha256:219abdf23fc8e4135142937121cd85ea9619b983ae2b9668c3e74d05b9135d5a`

### PR merge-ref integration verification
- PR #360
- synthetic SHA: `decce34f5a0cf348a4f9ab1ab80c50179d5e9d2b`
- Verify #819
- 2031 passed / 0 failed
- artifact id: 9849493222
- digest: `sha256:84e4ae787b3ff93b30c9ba23f3c7b4032a4a329541922179bff25a660b4c1d40`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `87c95cf2eb139cd8782d8df79d43b2313939bba0`
- Verify #820
- 2031 passed / 0 failed
- artifact id: 9849548406
- digest: `sha256:37853547096138bb851a62399a5ba8c5e3ea54f02c9bb92a9623c155abc5c6b1`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

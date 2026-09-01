# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`0671c0a0b06c662e935b4dcbf00e4cad12e32175`

Latest merged production-correctness batch:

`v941-v950: Product Decision User Action Learning Confidence Evidence Integrity`

### Entering exact-main verification
- exact main: `df1a2f79b710974bb0b951beb18b76fc559e1bbd`
- push Verify #656
- 1841 passed / 0 failed
- artifact id: 9813227264
- digest: `sha256:e758e31f1b27ac899e9415d361852a8941f497a6f2be4a73fc7fc35d4030031d`

### Exact final feature-head verification
- exact SHA: `8aa3a6b6205517c3eb9754976a1140f9633b5220`
- push Verify #658
- 1851 passed / 0 failed
- artifact id: 9813305254
- digest: `sha256:5182f48d2ca345d178dfd239fa4c62c311470b309f5f09cf71cddc97b2946e7f`

### PR merge-ref integration verification
- PR #324
- synthetic SHA: `7e227b17869617711a3f8b277900674eba383745`
- Verify #659
- 1851 passed / 0 failed
- artifact id: 9813331763
- digest: `sha256:e6469900516f779458af0dd989a355da0d4039db70cc6c9d648a7c5342ea5266`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `0671c0a0b06c662e935b4dcbf00e4cad12e32175`
- Verify #660
- 1851 passed / 0 failed
- artifact id: 9813358198
- digest: `sha256:724cd0349abc24f867ed5340aabb3bc3ccea82986c8bf6833b92c981bbcd89d2`

No failed intermediate production SHA occurred in v941-v950.

## Immediately preceding verified product package: v931-v940

- final feature `e600b6726a9eadadce65f8b803b74608b79d96d0`: Verify #650, 1841 passed / 0 failed
- PR #322 synthetic `5b58b853a5e8b402a4e5b61ffd68f4174416b190`: Verify #651, 1841 passed / 0 failed
- squash main `9a504323b6b4bb0adb2a6d5a75507b4c0b6f19f9`: Verify #652, 1841 passed / 0 failed
- failed intermediate `849b0d0e78e441f3080631419ecbc0ea192890ec`: Verify #649, 1840 passed / 1 failed
- `externally_verified=False`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs remain cancelled/pending evidence and carry no transferable claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

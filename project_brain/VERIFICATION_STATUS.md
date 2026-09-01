# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`5f0534bb72dba2471c3c339a69cd7041552dfb4a`

Latest merged production-correctness batch:

`v981-v990: Product Decision Result Integrity`

### Entering exact-main verification
- exact main: `8d3158fbfa0e4e29d40fa0ce1d8b8f373fc74744`
- Verify #690
- 1881 passed / 0 failed
- artifact id: 9815643598
- digest: `sha256:037368b6a69b736e90f0864427528c64f89392970774e7d61e3e247d0f3ef820`

### Cancelled intermediate branch evidence
- `f21c1ca4b21b57a634a502ecb754e93fabb78e18`: Verify #693 cancelled
- `689fd2b9db65861f8853251accb0f2a3e0cf86d8`: Verify #694 cancelled
- no success claim is transferred from cancelled runs

### Failed intermediate feature verification
- exact SHA: `8a286947bdc5862834a05794e330d87ef370ffe7`
- Verify #695
- conclusion: failure
- 1889 passed / 2 failed
- artifact id: 9816934445
- digest: `sha256:289d68239b8811b713c72e00e5185759b6b76242e41c9ee47f84fd0b0085ac06`
- failure source: legacy freshness fixture used noncanonical empty Product Decision reasons
- this SHA remains failed evidence permanently

### Exact final feature-head verification
- exact SHA: `8b90c11763622cc413802a488171738cf2332a1a`
- Verify #696
- 1891 passed / 0 failed
- artifact id: 9816964776
- digest: `sha256:d6a8a29cc277e9229f782020588d2bbbd6ffad6b61088d223bcf577d7edecf21`

### PR merge-ref integration verification
- PR #332
- synthetic SHA: `da5e7689cc87a0597944f371dfe4246082d92806`
- Verify #697
- 1891 passed / 0 failed
- artifact id: 9816994511
- digest: `sha256:6824d8be6988720e5bb1abe1c0ab10cbab198eb359e6ba22f9cd8cccb578ecdc`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `5f0534bb72dba2471c3c339a69cd7041552dfb4a`
- Verify #698
- 1891 passed / 0 failed
- artifact id: 9817030052
- digest: `sha256:c7af1301e9eaa791da1e11038c30503dfb79b2099a91731de90579e625a35830`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

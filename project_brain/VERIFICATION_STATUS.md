# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`982dc4f58fec6172a4fa99475ae72800c107981f`

Latest merged production-correctness batch:

`v1011-v1020: Product Decision Unit Economics Result Integrity`

### Entering exact-main verification
- exact main: `116bbbfe62c6c0f27d33764ffdeff78e14a31550`
- Verify #721
- 1911 passed / 0 failed
- artifact id: 9818600357
- digest: `sha256:389ba9d7c14d8d820cbbeec43da6f0230da4513fd2660d45b0b611bae13f7b99`

### Failed intermediate verification
- exact SHA: `c27b1fbfba804d36167855228f1881c08c4ef506`
- Verify #723
- 1917 passed / 4 failed
- artifact id: 9818770098
- digest: `sha256:4befff3abaa04a2495c064f894ccbf62e4f351ff4c0dcd788be848ab6de4828e`

This SHA remains failed evidence permanently.

### Failed intermediate verification
- exact SHA: `1114863bdc5b23969fe8cf2d3c9166fe5e7cd523`
- Verify #724
- 1918 passed / 3 failed
- artifact id: 9818796986
- digest: `sha256:2f1512681c65a5b470a063e260b62f5689c448a68ad891a0a0bd561355009eda`

This SHA remains failed evidence permanently.

### Exact final feature-head verification
- exact SHA: `fa9cd0e874347ba00320c8e9c36c85d0efb530a0`
- Verify #725
- 1921 passed / 0 failed
- artifact id: 9818832270
- digest: `sha256:000475d4668fa695df71c6e226f8f988fad57e9a4703d4c83928c0c74c9b3319`

### PR merge-ref integration verification
- PR #338
- synthetic SHA: `8014a74ae903863da672ee4b82f9fb565ad3d6cc`
- Verify #726
- 1921 passed / 0 failed
- artifact id: 9818861081
- digest: `sha256:425a071b7d1b996951d6f5ae0cde8858a94c7cf2940155ec582ff81eab8c47fd`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `982dc4f58fec6172a4fa99475ae72800c107981f`
- Verify #727
- 1921 passed / 0 failed
- artifact id: 9818889552
- digest: `sha256:ceda4fa16efb58e088edcf5799e82c9b2afa41ac1d2de46a45fa46598b3d6170`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

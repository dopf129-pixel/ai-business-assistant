# Verification Status

Date: 2026-09-03

## Latest verified product baseline

`875cc4a783a48eb9a9059b9e2e9ba85316fbdc0d`

Latest merged production batch:

`v1261-v1270: External Operating Expense Coverage`

### Entering exact-main verification
- exact main: `9a29e853727c82abdf75b1992c45c532bd45e3ef`
- Verify #1050
- 2161 passed / 0 failed
- artifact id: 9894484795
- digest: `sha256:0a864e6e4515eb024f13758d13d944907bcd4a72250cb7e5508e900145cab025`

### Failed intermediate evidence

- exact SHA: `55d8f189dc170cc524aa8798aea42b1b7ae6251c`
- Verify #1054
- 2150 passed / 11 failed
- artifact id: 9894680388
- digest: `sha256:49302f69375d247b9094b7a58f1a16c5671124eb894eef0153edd3dc1276c376`
- failure cause: external-expense coverage argument was wired before the coverage builder signature was extended.

- exact SHA: `9f32163739d849dfe3681a9de6358fb64db40100`
- Verify #1055
- 2150 passed / 11 failed
- artifact id: 9894698643
- digest: `sha256:e37593e820234269a9230e6be4f8c61fc591d7108f4093201bdb3192e09956d0`
- failure cause: response call wiring advanced before the response builder signature was extended.

- exact SHA: `e788e5110109eb678767313278580989b192f689`
- Verify #1060
- 2160 passed / 1 failed
- artifact id: 9894794990
- digest: `sha256:af0ffe3ef3fe9ddfce906ac6bbb3a33c10f5ac445f1884705aa3b85e483fb1fc`
- failure cause: factory test double had not yet accepted the external expense evidence dependency.

These SHAs remain failed evidence permanently.

Cancelled intermediate SHAs from this feature branch carry no transferable success claim.

### Exact final feature-head verification
- exact SHA: `07f9a35eb238280e95b52bc14d18cc6aba735703`
- Verify #1062
- 2171 passed / 0 failed
- artifact id: 9894853461
- digest: `sha256:9d28a3a5ae753f1215fd042622fd62d7e4985fa96eeba0f2f140318166617298`

### PR merge-ref integration verification
- PR #389
- synthetic SHA: `77dd43cfeb36ebe0066f8747c6c51580083848a6`
- Verify #1063
- 2171 passed / 0 failed
- artifact id: 9894897854
- digest: `sha256:9111b865c015e95c360ba417c3ef68f82377e82f9e2eddfc7c7e7d8c61ae93a0`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `875cc4a783a48eb9a9059b9e2e9ba85316fbdc0d`
- Verify #1064
- 2171 passed / 0 failed
- artifact id: 9894942156
- digest: `sha256:6ba30eda33b5a1315469e4fbf9253058d932cbc756e634b8996b2f31b2158e53`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is project CI evidence only;
`externally_verified=False`.

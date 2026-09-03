# Verification Status

Date: 2026-09-03

## Latest verified product baseline

`9ca4497dda61615076b8203d0404502630ab7e81`

Latest merged production batch:

`v1281-v1290: Historical Product Cost Evidence`

### Entering exact-main verification
- exact main: `212df575cc60a809032954d425902fad86623956`
- Verify #1095
- 2185 passed / 0 failed
- artifact id: 9906001699
- digest: `sha256:a50fb08552d73f187bbacc608751655880f293578a7ac4408154808d82a16f79`

### Intermediate evidence

No failed production SHA occurred in this feature branch.

Cancelled intermediate SHAs carry no transferable success claim.

### Exact final feature-head verification
- exact SHA: `f3fcb80588f394eb05e5944ca2812ed59adf7649`
- Verify #1103
- 2195 passed / 0 failed
- artifact id: 9906200014
- digest: `sha256:c776260a5026572cbe27c2bab5212d2a64d92d95f7a9170a433a2d5b12b46af7`

### PR merge-ref integration verification
- PR #393
- synthetic SHA: `672e18f904768742917df9c808c48ec476d9fd3e`
- Verify #1104
- 2195 passed / 0 failed
- artifact id: 9906235551
- digest: `sha256:d849f4a6413df1de6c6b3e28ed4f5c45465b292266db2c31dbac3602251fcfb0`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `9ca4497dda61615076b8203d0404502630ab7e81`
- Verify #1105
- 2195 passed / 0 failed
- artifact id: 9906262083
- digest: `sha256:6bc9ab6699976e56572a216dab839e96c8921f484047c522eb00535163626987`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is project CI evidence only;
`externally_verified=False`.

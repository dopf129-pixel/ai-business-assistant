# Verification Status

Date: 2026-09-03

## Latest verified product baseline

`05f94da42e21c5ad5f7d78cb7f55bb2d40730f77`

Latest merged production batch:

`v1171-v1180: Telegram Custom Period Date Input`

### Entering exact-main verification
- exact main: `fa30bafeecfa9291175e7f1c4ac0ad2c078b4607`
- Verify #881
- 2071 passed / 0 failed
- artifact id: 9884075851
- digest: `sha256:8bb0274a95fa48b01e315a2c4a7190fcae33c9a4eee11ebdb3c2db49a2303f72`

### Exact final feature-head verification
- exact SHA: `62b040e392514bc410b34d82eccb8e0385b9c548`
- Verify #884
- 2081 passed / 0 failed
- artifact id: 9884220127
- digest: `sha256:18f9ac90e9a8d05bd01a76db6955afa578c951390018b504cae8374663e185be`

### PR merge-ref integration verification
- PR #371
- synthetic SHA: `b865b551289ba4592d8d32594323ea8a6dc64c61`
- Verify #885
- 2081 passed / 0 failed
- artifact id: 9884251146
- digest: `sha256:04099f259682c0e84daa67dd74d3328081855cf86418b299336c16f38f2b0312`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `05f94da42e21c5ad5f7d78cb7f55bb2d40730f77`
- Verify #886
- 2081 passed / 0 failed
- artifact id: 9884281842
- digest: `sha256:a3f889420b898d65c8ef0f027b199ec6c23ebc8bb345933efe9d74c65b686344`

No failed production SHA occurred in v1171-v1180.

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is project CI evidence only;
`externally_verified=False`.

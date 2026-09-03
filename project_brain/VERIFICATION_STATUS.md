# Verification Status

Date: 2026-09-03

## Latest verified product baseline

`5c0ed4bd40207e3f4bcce3770e89e71e163288b1`

Latest merged production batch:

`v1271-v1280: Return Sale-Period Lineage Evidence`

### Entering exact-main verification
- exact main: `356fa301a9025e15a5a9fbb94da706d10670416a`
- Verify #1074
- 2171 passed / 0 failed
- artifact id: 9897945762
- digest: `sha256:9b883028d77316bcabd7634b934f9ab38664a84468eab5622195ff73929c7653`

### Failed intermediate evidence
- exact SHA: `db2c6c0fa900720c303a8f8face32ef3eec3be11`
- Verify #1081
- 2170 passed / 1 failed
- artifact id: 9898277377
- digest: `sha256:2e8365779ec323568d2be3649d17d7a79e8d5a5da745f128cc11555750cd7b2e`
- failure cause: the Period Profit factory test double still accepted only the former one-argument Return COGS evidence constructor after sale-lineage dependency wiring.

This SHA remains failed evidence permanently.

Cancelled intermediate SHAs from this feature branch carry no transferable success claim.

### Exact final feature-head verification
- exact SHA: `e96fb63007647857045f226c9c41fd8157ae962e`
- Verify #1083
- 2185 passed / 0 failed
- artifact id: 9898333361
- digest: `sha256:7ac52123e97a821e6fb65fcc7dc15dfb61d68a8be6fd40c9598b7505a174c3f5`

### PR merge-ref integration verification
- PR #391
- synthetic SHA: `26d6ca0e9b2ef2b4a358cc6a517bd13bf152bffc`
- Verify #1084
- 2185 passed / 0 failed
- artifact id: 9898386674
- digest: `sha256:a4ac6ad8520a2a0726aff061f5f579a74742f868e17e2ced9d89ac84c3798d47`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `5c0ed4bd40207e3f4bcce3770e89e71e163288b1`
- Verify #1085
- 2185 passed / 0 failed
- artifact id: 9898420551
- digest: `sha256:4a187e0b83b0b5950e64aaf749d31b78d7d5435132a77fde2e044667fe06b864`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is project CI evidence only;
`externally_verified=False`.

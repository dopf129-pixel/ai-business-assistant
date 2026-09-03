# Verification Status

Date: 2026-09-03

## Latest verified product baseline

`9c9d379e36edf2123a466ad2b3cd1d000d81bae3`

Latest merged production batch:

`v1181-v1190: Tax Policy Production Availability`

### Entering exact-main verification
- exact main: `8ca28c36249a052fdf83cfd5ab86a13d986cbb1c`
- Verify #896
- 2081 passed / 0 failed
- artifact id: 9884443694
- digest: `sha256:a5d997dde52609adc1511d794a654e5af5d30dfdad1193bb4398d9c5f11117e3`

### Exact final feature-head verification
- exact SHA: `1d0df2799fb87b57d916843a96a080389e2ac07b`
- Verify #900
- 2091 passed / 0 failed
- artifact id: 9884824274
- digest: `sha256:8a54d841f9b6b18c7e0184365da0995bee4b09c57ffffe464acb17df41c6f0b0`

### PR merge-ref integration verification
- PR #373
- synthetic SHA: `a6493407f0bb915f366573404fcffd220e6757a1`
- Verify #901
- 2091 passed / 0 failed
- artifact id: 9884854745
- digest: `sha256:3327e51b96a4c4ad376e21f524b578caa6709d20336b52c430adef277603f8b0`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `9c9d379e36edf2123a466ad2b3cd1d000d81bae3`
- Verify #902
- 2091 passed / 0 failed
- artifact id: 9884888892
- digest: `sha256:f50357c3d1ef309fc7be702b6807406677a733fe7a5102aff67b3c7405676d60`

No failed production SHA occurred in v1181-v1190.

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is project CI evidence only;
`externally_verified=False`.

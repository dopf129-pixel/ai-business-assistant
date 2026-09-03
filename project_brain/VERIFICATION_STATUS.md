# Verification Status

Date: 2026-09-03

## Latest verified product baseline

`a359e3d8e68784849caa659dec0123fb15dc6932`

Latest merged production batch:

`v1241-v1250: Account-Level Ozon Profit Reconciliation`

### Entering exact-main verification
- exact main: `0aa27a1267b9d54f1207455b05e32db843091d86`
- Verify #1003
- 2141 passed / 0 failed
- artifact id: 9888777124
- digest: `sha256:f5251c670e44174ebebc22f3152833c94450e99c8d7cd6f0192fb9231b3f59d2`

### Exact final feature-head verification
- exact SHA: `a0e528f36b1b4721af0e8d0b419c414d20fabea6`
- Verify #1010
- 2151 passed / 0 failed
- artifact id: 9891989048
- digest: `sha256:4e28915675e1e8a6acf32600fe4e0294ba5a8a378c986b10a70a56bb06302d7a`

### PR merge-ref integration verification
- PR #385
- synthetic SHA: `4a361a58d62e56c2e2aa4c608620ae86992ac05f`
- Verify #1011
- 2151 passed / 0 failed
- artifact id: 9892029109
- digest: `sha256:3c5196c966a250b5bd54e6b558be085680f352fcc156d25d8562ffd172f8869f`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `a359e3d8e68784849caa659dec0123fb15dc6932`
- Verify #1012
- 2151 passed / 0 failed
- artifact id: 9892074726
- digest: `sha256:212517f2c06aec43f7c089df382d111436dfa8b17bbaf9f19b719779c6d9d072`

No failed production SHA occurred in v1241-v1250.

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is project CI evidence only;
`externally_verified=False`.

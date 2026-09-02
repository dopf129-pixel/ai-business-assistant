# Verification Status

Date: 2026-09-02

## Latest verified product baseline

`41473566a558bb09899f64d581010b72e4053fbd`

Latest merged production-correctness batch:

`v1071-v1080: Product Decision Telegram Query Exception Containment`

### Entering exact-main verification
- exact main: `e972a385dbd8082abdaee37ab4178f15db5e8eec`
- Verify #775
- 1971 passed / 0 failed
- artifact id: 9843602845
- digest: `sha256:d6388af1d7afd6777fc14321032f5d5c03803dc3657902fa970236ce1478e4b9`

### Failed intermediate verification
- exact SHA: `31902d6e4f1302a5fe221e091b54bd5e2c4a8f3d`
- Verify #777
- 1980 passed / 1 failed
- artifact id: 9843687318
- digest: `sha256:2bfe9053d7dc2d7dac764717034dc1db28d929675235520dbc9b1d88e338de5c`

This SHA remains failed evidence permanently.

### Exact final feature-head verification
- exact SHA: `30da677a1db0fdca3cd4ac2b0928859e0b9b81a8`
- Verify #778
- 1981 passed / 0 failed
- artifact id: 9843713042
- digest: `sha256:3568d4e4b7cab571a44eb108e19395565da4aa1605896cd5ef969f4f410ef6b7`

### PR merge-ref integration verification
- PR #350
- synthetic SHA: `a0bbb0059c67c3d4e0583f2b13883f5dd3f8857e`
- Verify #779
- 1981 passed / 0 failed
- artifact id: 9843741080
- digest: `sha256:bdc23cc1a9c1de9fab7b62fa0b543aeea9e24afaf5f726176d34f3bd7d342466`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `41473566a558bb09899f64d581010b72e4053fbd`
- Verify #780
- 1981 passed / 0 failed
- artifact id: 9843768969
- digest: `sha256:5a85d8e4c90d93666faecf8ca9c786386e835078d1ebd817f8ec97556a7e703a`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

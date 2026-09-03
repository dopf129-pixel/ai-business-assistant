# Verification Status

Date: 2026-09-03

## Latest verified product baseline

`2f438bd6bb739938cee4fe56b83af8f4a563f942`

Latest merged production batch:

`v1211-v1220: Period Profit Tax Rate Unit Integrity`

### Entering exact-main verification
- exact main: `590b068ef46f58e56509ac038759f465975c9a8a`
- Verify #949
- 2111 passed / 0 failed
- artifact id: 9886812170
- digest: `sha256:83cdf8fe62a670cacee5ab69cf07e2baaab324d7c6437d3c65175d3dc6102bf5`

### Failed intermediate evidence
- exact SHA: `a7d5cead4c7c49907d6d045b54a3cec30d48efad`
- Verify #953
- 2110 passed / 1 failed
- artifact id: 9887077119
- digest: `sha256:51184585e794907d4c730305e2af0cfb98e895ed6153babb75ec997a803c0809`
- failure: legacy factory test expected removed direct TAX_RATE module attribute.

- exact SHA: `ee463cd1000113998ae5b895da02334bb5a5f495`
- Verify #954
- 2120 passed / 1 failed
- artifact id: 9887087702
- digest: `sha256:118d2dad053f08adabe6605aa1790a2600628b9a9ece50c53b62f012ac2e0689`
- same legacy factory-test contract drift after regression coverage was added.

These SHAs remain failed evidence permanently.

### Exact final feature-head verification
- exact SHA: `4c50429bc4c2f6515d80b497b85fe8c9663e24eb`
- Verify #955
- 2121 passed / 0 failed
- artifact id: 9887122511
- digest: `sha256:ea8eeeb352ab0309dda2fca54573b6211c052dbbf51996699084edfc68811a58`

### PR merge-ref integration verification
- PR #379
- synthetic SHA: `68c0f7360dd93738377f7111f5f4732d0b4d48af`
- Verify #956
- 2121 passed / 0 failed
- artifact id: 9887163034
- digest: `sha256:5f6b8d4487c21eee14d87b245881dfe8686ac4467514b84e750da4851cb81f69`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `2f438bd6bb739938cee4fe56b83af8f4a563f942`
- Verify #957
- 2121 passed / 0 failed
- artifact id: 9887195049
- digest: `sha256:414836b82a65d5a73a08ad2622e5b7b579262361319c384272f0863cbd45b976`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is project CI evidence only;
`externally_verified=False`.

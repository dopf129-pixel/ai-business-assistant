# Verification Status

Date: 2026-09-03

## Latest verified product baseline

`7b2b570278c9cc71f3eb6dbb23b5554d41de07f7`

Latest merged production batch:

`v1201-v1210: Period Profit Data Completeness Integrity`

### Entering exact-main verification
- exact main: `5e8e74a78e2c5aa41ed59378c27a0f1ed7b55397`
- Verify #930
- 2101 passed / 0 failed
- artifact id: 9885946944
- digest: `sha256:9d4245aa4460358cadfb38a9887dd8bacf212394a995182bd1afd55754c6829b`

### Failed intermediate evidence
- exact SHA: `e3d8b2ed1600e3759135bda4f62865ba38a43ae9`
- Verify #935
- 2103 passed / 2 failed
- artifact id: 9886500028
- digest: `sha256:3d92acbe35ea2c4aab44beed55707f6edf0667e8c08376db82993617fd51dfad`
- root cause: legacy READY return-evidence response compatibility.

- exact SHA: `49c02ae1790b7d395794932e7ac4fa95cbac1644`
- Verify #936
- 2109 passed / 2 failed
- artifact id: 9886515012
- digest: `sha256:179b93cff72ed7316f5aed922b25de95a84f2a3447b09d67b956d237a2074345`
- same compatibility issue after the full regression package was added.

These SHAs remain failed evidence permanently.

### Exact final feature-head verification
- exact SHA: `16c53622612b72bce2aa43fd97d5ff66d47466c3`
- Verify #937
- 2111 passed / 0 failed
- artifact id: 9886550033
- digest: `sha256:cd5485dd1d5c8b1dd49355f1de14795445055b11e6127d2ae4fe4010fb55defb`

### PR merge-ref integration verification
- PR #377
- synthetic SHA: `f1593267f67339f2dd68d235056cdbc69960160a`
- Verify #938
- 2111 passed / 0 failed
- artifact id: 9886596735
- digest: `sha256:6a1599d927da9f77e928ed321e0de92fa14b8b4bd938974e7199e107da9e8d98`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `7b2b570278c9cc71f3eb6dbb23b5554d41de07f7`
- Verify #939
- 2111 passed / 0 failed
- artifact id: 9886631604
- digest: `sha256:51ab9910779fa0141662aafc5e90738299ef13b3f0ee95d25b25a034fcc358ad`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is project CI evidence only;
`externally_verified=False`.

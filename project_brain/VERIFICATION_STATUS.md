# Verification Status

Date: 2026-09-02

## Latest verified product baseline

`1bc8cfc745a94c7bfe3442bf2c774947f79bce8b`

Latest merged production-correctness batch:

`v1101-v1110: Tax Calculation Input & Result Integrity`

### Entering exact-main verification
- exact main: `13479dc0226ad18fe1fe9ff1c20369c27672e759`
- Verify #800
- 2001 passed / 0 failed
- artifact id: 9845686313
- digest: `sha256:a6bd91d23e9732e7aaf1a0f760ea6723099b43ba7f79378e4da06e206cb5dce4`

### Exact final feature-head verification
- exact SHA: `85fc4b76baa725cbc586ca39e8454e30a70fb168`
- Verify #802
- 2011 passed / 0 failed
- artifact id: 9845836394
- digest: `sha256:639494d4a4a71112a5530207d4b1ec10b0e528f3d044b60c025f69b333cdce62`

### PR merge-ref integration verification
- PR #356
- synthetic SHA: `7d070c91d97e811491849475ddcd65552eadd1c7`
- Verify #803
- 2011 passed / 0 failed
- artifact id: 9845882715
- digest: `sha256:b6e89d4068a6c2cd19d083715eb8ea2fc21a8984dbdb0cbd8f60b26ecb4fe2cf`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `1bc8cfc745a94c7bfe3442bf2c774947f79bce8b`
- Verify #804
- 2011 passed / 0 failed
- artifact id: 9845942947
- digest: `sha256:5d9178abb2b6e10ade77688e688e17a9fbb7d938b4c80d65018c48540a2db558`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

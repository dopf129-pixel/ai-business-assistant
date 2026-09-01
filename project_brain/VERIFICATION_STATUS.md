# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`288c6452703eee4082414d1ad36680b4ddf02caa`

Latest merged production-correctness batch:

`v1001-v1010: Product Decision Task Draft Lifecycle Result Integrity`

### Entering exact-main verification
- exact main: `ca07c1565702949d1941102067e15150690227e8`
- Verify #713
- 1901 passed / 0 failed
- artifact id: 9818283861
- digest: `sha256:96d66600d68c334585dc09f8b0ff7ecc4c5ffe199cedef3de4dacfb7f4cb3f90`

### Exact final feature-head verification
- exact SHA: `12e4f1d4f38296b8f46680302478f377121644a8`
- Verify #715
- 1911 passed / 0 failed
- artifact id: 9818413016
- digest: `sha256:7bdc75d5c608109484eb0e3f349f60f2f0ba8a167981c7622e82c81ec6f28dc6`

### PR merge-ref integration verification
- PR #336
- synthetic SHA: `005ac13b1fbb01bb6e95314d1f8c89b994ba85c6`
- Verify #716
- 1911 passed / 0 failed
- artifact id: 9818442054
- digest: `sha256:c873abf6af7d17a6858e8cc5499e5baf3835ca8432d6e01a8df7ee245c7c9071`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `288c6452703eee4082414d1ad36680b4ddf02caa`
- Verify #717
- 1911 passed / 0 failed
- artifact id: 9818471271
- digest: `sha256:37b6e301a54fdb3a297b7e648adb9e4e87376d5cbc9ed3fc69ee1d7ffee801c5`

No failed production SHA exists in this package.

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

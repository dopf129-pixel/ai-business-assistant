# Verification Status

Date: 2026-09-02

## Latest verified product baseline

`189455bb5b44c47bbf5abf188d1b456dad14b1ba`

Latest merged production-correctness batch:

`v1131-v1140: Business Profit Calculation Result Integrity`

### Entering exact-main verification
- exact main: `b3063a754aeaa7ba290e9ea6ef6a0690354d4161`
- Verify #824
- 2031 passed / 0 failed
- artifact id: 9849936981
- digest: `sha256:9fb1c12b1b8a8341346eab20635abadf7337f1ea8b26a0004be754a1dba9fda4`

### Exact final feature-head verification
- exact SHA: `98edb5b5500c25e53b77237016afe3a223360ab8`
- Verify #826
- 2041 passed / 0 failed
- artifact id: 9850198413
- digest: `sha256:a28889fed572b8ac4f1a44d06faf567615ac646040eeee9b3faa4616017810fd`

### PR merge-ref integration verification
- PR #362
- synthetic SHA: `6e335e508c07903d6e4488f1aac40d28a9e4152f`
- Verify #827
- 2041 passed / 0 failed
- artifact id: 9850246557
- digest: `sha256:c490d6b43824bf420dfb2c5d812637a1220016170ec3afc423707f9332da979a`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `189455bb5b44c47bbf5abf188d1b456dad14b1ba`
- Verify #828
- 2041 passed / 0 failed
- artifact id: 9850316806
- digest: `sha256:bcaaf2b0b6927472571ab69c9b0e1d1898e19fa43a9adf62f169278867621ff9`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

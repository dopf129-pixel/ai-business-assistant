# Verification Status

Date: 2026-09-01

## Latest verified product baseline

`7d53fecac126973122270eacfdfc122e50ae3de3`

Latest merged production-correctness batch:

`v1031-v1040: Product Decision Persistence Commit Receipt Integrity`

### Entering exact-main verification
- exact main: `d62fc3672fda6d227a746ff184fcbda36b19c8ed`
- Verify #740
- 1931 passed / 0 failed
- artifact id: 9820317673
- digest: `sha256:92dfb14104245179e9841b11dab06a64de6b50c55c100aa9d781581a3b0552fa`

### Failed intermediate verification
- exact SHA: `14a0709209228310625dd91871e963a866ab6cc9`
- Verify #742
- 1940 passed / 1 failed
- artifact id: 9820529167
- digest: `sha256:1091138eae94c940d4ee0add628a30071df2f547037b379f7b52c62fc33bd0b8`

This SHA remains failed evidence permanently.

### Exact final feature-head verification
- exact SHA: `88372919c9275a51482703e59fe21d8c4d9c5682`
- Verify #743
- 1941 passed / 0 failed
- artifact id: 9820570261
- digest: `sha256:735bfcb0bf9a44204928ceefb49079347d9c044839d4461872c51720ccc34da5`

### PR merge-ref integration verification
- PR #342
- synthetic SHA: `7e54ca702706ad192eb70da63e351e96efdb31b5`
- Verify #744
- 1941 passed / 0 failed
- artifact id: 9820601679
- digest: `sha256:906f36eeae5b1737725880484897f314cbe16ba9231caf86736e90c54fbdeda2`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `7d53fecac126973122270eacfdfc122e50ae3de3`
- Verify #745
- 1941 passed / 0 failed
- artifact id: 9820633507
- digest: `sha256:af6b1b1cf03d70b8330d2450653303b088577ef0df6dbb5b1d5a4604a6141715`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is not independent external verification;
`externally_verified=False`.

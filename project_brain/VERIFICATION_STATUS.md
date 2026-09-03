# Verification Status

Date: 2026-09-03

## Latest verified product baseline

`d06a5f8cc23814e3177f58f6182bef6fbceb0697`

Latest merged production batch:

`v1161-v1170: Telegram Period Profit Analyst Wiring`

### Entering exact-main verification
- exact main: `bb2e444b5a7ee6caa9cc4e39adccc5df64949835`
- Verify #859
- 2061 passed / 0 failed
- artifact id: 9883235366
- digest: `sha256:87ac10f53b0baf234342e9966c6f3892d436564bc99351968b22513b6f65f71a`

### Failed intermediate feature evidence
- exact SHA: `e7fce70c39f976e97bf78687621ace5125f9d30a`
- Verify #866
- 2069 passed / 2 failed
- artifact id: 9883777834
- digest: `sha256:bf6bd18f7a8286de371506b91facbce73d874214ce4cc97c2d46cb16123ddb6b`
- root cause: backward-compat partial-core fixture and exact pre-feature keyboard expectation were stale after the new Telegram wiring.
- this SHA remains failed evidence permanently.

### Exact final feature-head verification
- exact SHA: `9c5d14f0220e5f13ee0a7d834855f7e07db58cab`
- Verify #868
- 2071 passed / 0 failed
- artifact id: 9883814622
- digest: `sha256:11377f17edbcefa550f753fa4fe9ace40ddb4273f2fbc28abf51ea9420ac5eb8`

### PR merge-ref integration verification
- PR #369
- synthetic SHA: `04b20cc49a253bfb357626cf62a71b779a75112e`
- Verify #869
- 2071 passed / 0 failed
- artifact id: 9883849757
- digest: `sha256:b9c5b5bee9ba6d162f80e5a3cf4bd49ea3244e23f0f51eb81ee04c973ef9ee8c`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `d06a5f8cc23814e3177f58f6182bef6fbceb0697`
- Verify #870
- 2071 passed / 0 failed
- artifact id: 9883879151
- digest: `sha256:ca8b45d7ea5b7b5651393d3aa57839c2ad8f87a7eaa904401aac31656cbdc7ed`

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is project CI evidence only;
`externally_verified=False`.

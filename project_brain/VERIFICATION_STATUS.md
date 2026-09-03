# Verification Status

Date: 2026-09-03

## Latest verified product baseline

`08d0d0fa6860101921ead603ec4a00b95c9ee8bf`

Latest merged production batch:

`v1221-v1230: Period Profit Revenue Share Presentation`

### Entering exact-main verification
- exact main: `5cb69fed7bc44fcd5f66a8a004e625bee9993953`
- Verify #967
- 2121 passed / 0 failed
- artifact id: 9887385716
- digest: `sha256:d48d11f3c4a478d585466db124b5f032776a76b4b591bac5eadb1fa1e31a7477`

### Exact final feature-head verification
- exact SHA: `77994ccb67c060f7c01694ac65eea5c8aec24e1d`
- Verify #970
- 2131 passed / 0 failed
- artifact id: 9887454837
- digest: `sha256:1d0b3d4481b8c3b7db1574c937f204b5c9bf50b95faa6ad6302d8a3178c5392b`

### PR merge-ref integration verification
- PR #381
- synthetic SHA: `b9a72b875081d6f12fe7f5b50d4b0c6f6af13e89`
- Verify #971
- 2131 passed / 0 failed
- artifact id: 9887485384
- digest: `sha256:a2fdc18398338989d9dffa1a782741d947f2eb0c2e94e623d2f9e121a656dddc`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `08d0d0fa6860101921ead603ec4a00b95c9ee8bf`
- Verify #972
- 2131 passed / 0 failed
- artifact id: 9887518565
- digest: `sha256:ff0b6adc775f02a7454d785ad4b7815719ca11254e3f67836bf1fc29c17636b9`

No failed production SHA occurred in v1221-v1230.

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is project CI evidence only;
`externally_verified=False`.

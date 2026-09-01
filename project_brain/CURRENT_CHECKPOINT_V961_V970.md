# CURRENT_CHECKPOINT_V961_V970

Date: 2026-09-01

## Product Decision History Context Result Integrity

Production package:

`v961-v970: Product Decision History Context Result Integrity`

Goal:

Protect the seller-facing Product Decision pipeline from malformed, exceptional, or identity-overwriting context returned by the decision-history dependency before cache, task-draft lifecycle, or Telegram presentation.

## Verified behavior

- `decision_history_service.record()` must return a mapping;
- returned history context is restricted to an explicit whitelist;
- history context cannot overwrite Product Decision SKU, priority, decision type, or error state;
- malformed/exceptional history context becomes explicit unknown/unavailable interaction state;
- unknown history count remains `None`, never coerced to zero;
- invalid history context is not cached;
- invalid history context cannot enter task-draft lifecycle;
- valid context remains cacheable and preserves canonical history fields;
- Telegram skips latest history/draft reads when history context is invalid;
- malformed, cross-SKU, or unknown-status latest history cannot enter the seller card;
- attached task draft must match SKU, proposal type, decision revision, and remain non-executed/non-executable.

## SHA-bound verification evidence

### Entering exact main

- SHA: `40f1a28b3515a07879bda369800b65dea8998f7f`
- push Verify #672
- 1861 passed / 0 failed
- artifact id: 9813910089
- digest: `sha256:f18af8ad2031e5d3da93b11c81f4d65cf949a691d0933fec3ef4581945d017b9`

### Failed intermediate production SHA

- SHA: `bfcc3551166431288f38ba0c06912133bed56818`
- push Verify #674
- 1870 passed / 1 failed
- artifact id: 9814044437
- digest: `sha256:e0edfc47ee933e8869dbb76ed0df3ca5a2ba4ba4b2d392e469c21a42ea3c82fc`
- failure: new Telegram draft-copy path referenced undeclared `deepcopy`, producing a `NameError`;
- this SHA remains failed evidence permanently.

### Exact final feature head

- SHA: `ab24a87c19072b5bbb3b9efd6b1630b513bf6645`
- push Verify #675
- 1871 passed / 0 failed
- artifact id: 9814074739
- digest: `sha256:5177dc9c3d210ea8f51af5fbf9ddd7633b8c3dc8c7e8f834c75ea68439a58ca0`

### PR synthetic merge-ref

- PR #328
- synthetic SHA: `85e808a3dcc04ef9197bc673950546445ee15749`
- pull_request Verify #676
- 1871 passed / 0 failed
- artifact id: 9814104003
- digest: `sha256:4bf39ea34acf67aa9d2b71d014f9537e4dfbd2ee05d9bb664ca774fab0a004de`

This is synthetic integration evidence only.

### Squash-main verification

- exact main SHA: `10977368ac4179f1f7168943a38fcdbc01ecfd78`
- push Verify #677
- 1871 passed / 0 failed
- artifact id: 9814938009
- digest: `sha256:3d0e611601682145f91855cec93724cc9d13b5b241b69e2f1856ad1046996e36`

## Review classification

Architecture Review Required: Yes

Critical Review Required: No

Reason: an existing seller-facing history/query contract was materially hardened and the production/test diff exceeds the architecture-review size threshold. No new persistence owner, runtime route, execution layer, or business mutation path was introduced.

GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.

# Current Checkpoint v766-v773

Date: 2026-08-31

Package: Telegram Analyze / Plan History Integrity v1

## Product correctness closed

Telegram `analyze` and `plan` previously appended successful canonical history after `assistant.ask` without validating the assistant result and ignored the persistence result. An explicit downstream failure could therefore leave a false seller-facing success event, while failed or malformed history persistence could be hidden behind assistant success.

The boundary now requires a dict with real boolean `error` from the assistant before any success-history write. Explicit assistant failure is preserved. Validated assistant success records the expected event once when persistence context exists. The history result must itself be a dict with real boolean `error`, and success requires `saved=True`.

Explicit history failure is surfaced after assistant completion. Malformed or exceptional history persistence is ambiguous and returns `persistence_state_unknown=True`; no rollback is fabricated. Exception text is replaced with a stable non-secret failure code. No-user / absent-history-service behavior remains compatible.

No Product Decision rule/threshold changed. Product Task Draft remains non-executable. No Action Executor connection, business mutation authorization, quantity/price inference, Ozon mutation, or new persistence layer was introduced. Repository `data/users.json` was not modified.

## Review classification

Architecture Review Required: Yes

Reason: meaningful seller-facing runtime result and canonical-history persistence semantics changed at a runtime boundary, and the package exceeded 300 changed lines including focused regression tests.

Critical Review Required: No

No architectural replacement, persistence-owner change, authorization change, or autonomous execution capability was introduced.

## SHA-bound verification evidence

### Entering exact main

- exact SHA: `9c2f783710e125b183e8a314e1ac4c2eac1754f1`
- push Verify #449
- conclusion: success
- tests: 1666 passed / 0 failed
- artifact: `verification-9c2f783710e125b183e8a314e1ac4c2eac1754f1`
- artifact digest: `sha256:a292cffdbb1309e47f33c028062ce699fd1364f18f3db1007cf50e46295b51fa`

### Exact final feature head

- branch: `fix/telegram-analyze-plan-history-integrity-v766-v773`
- exact SHA: `dd6a5984026f591941fa0f2db62fc260a48f9e02`
- push Verify #451
- conclusion: success
- tests: 1674 passed / 0 failed
- artifact: `verification-dd6a5984026f591941fa0f2db62fc260a48f9e02`
- artifact digest: `sha256:328c9cc03f7b0b8e292ceb1e42cc78895ba5f86bc32875916c4fc5a5d46ecd02`

### PR synthetic merge-ref

- PR #288
- synthetic merge SHA: `83a8863f79f3ad76d721d4f7fd9eee2ed28a2b20`
- pull_request Verify #452
- conclusion: success
- tests: 1674 passed / 0 failed
- artifact: `verification-83a8863f79f3ad76d721d4f7fd9eee2ed28a2b20`
- artifact digest: `sha256:3c38001164cc6a7eb1b9f2838356843aff9a546ce7f15c5048eed2966251da3c`

This proves only the PR synthetic integration revision.

### Squash-main exact push

- exact main SHA: `1bd23e97a565e15b2c2ef6e2067278eacac6caa0`
- push Verify #453
- conclusion: success
- tests: 1674 passed / 0 failed
- artifact: `verification-1bd23e97a565e15b2c2ef6e2067278eacac6caa0`
- artifact digest: `sha256:46778bcf50f95fbf335d2d03c2e64aedf648461ec980818c8348fa8d627fca26`

No failed or cancelled intermediate production SHA occurred in v766-v773. Historical failed/cancelled evidence from earlier packages remains permanent and is not reclassified.

## Verification semantics

Each evidence row is bound only to its exact SHA. Feature success is not PR integration evidence; PR merge-ref success is not squash-main evidence. Missing evidence remains unknown. Cancelled evidence is not success. GitHub Actions is project CI evidence, not independent external verification.

`externally_verified=False`

## Related implementation

- `app/services/assistant_button_handler_service.py`
- `tests/test_telegram_analyze_plan_history_integrity_v766_v773.py`

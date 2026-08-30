# Current Checkpoint v677-v686

Date: 2026-08-31

Package: Telegram TypeError Retry Integrity v1

## Verified implementation

Telegram runtime compatibility dispatch now selects callable arity before invocation and no longer retries after an internal TypeError.

Verified behavior:

- legacy one-argument adapters, bot services, and button handlers remain supported where compatibility is required;
- modern callable arity is detected before the first call;
- an internal TypeError from TelegramRunner downstream dispatch propagates from a single invocation;
- an internal TypeError from TelegramBotService downstream dispatch propagates from a single invocation;
- an internal TypeError from AssistantTelegramAdapter button dispatch propagates from a single invocation;
- no compatibility retry can duplicate a partially started handler side effect;
- no business rules or persistence semantics changed;
- no Product Decision/Product Task Draft execution or Ozon mutation is introduced;
- `data/users.json` remains untouched.

## Architecture Review

Architecture Review Required: Yes.

Reason:

- execution-adjacent dispatch semantics changed across Runner, BotService, and Adapter boundaries;
- package exceeds 300 changed lines including focused tests.

Critical Review Required: No.

Review result:

- no architecture replacement;
- compatibility remains explicit and bounded;
- no persistence owner/layer change;
- no autonomous business execution capability added;
- no Ozon mutation;
- `data/users.json` untouched.

## SHA-bound verification evidence

### Entering verified main

- exact SHA: `b8e1656a607901ef251c686a61f6bc72eee69bbf`
- push Verify #371
- tests: 1577 passed / 0 failed
- artifact: `verification-b8e1656a607901ef251c686a61f6bc72eee69bbf`
- artifact digest: `sha256:09c311fc3da6c2e17ed57855e73a4a41d99d00d60e69549b6abe21d428f9a47b`

### Exact final feature head

- branch: `fix/telegram-typeerror-retry-integrity-v677-v686`
- exact SHA: `b8371c4194f004ed71584439543fa8a30998f5fb`
- push Verify #372
- tests: 1587 passed / 0 failed
- artifact: `verification-b8371c4194f004ed71584439543fa8a30998f5fb`
- artifact digest: `sha256:6e949f48bd074ca220fa62f1a3e190209811c6807abb2eba5d411a32adf55225`

### PR synthetic merge-ref

- PR #270
- exact feature head: `b8371c4194f004ed71584439543fa8a30998f5fb`
- synthetic merge SHA: `3064816c03be1efdbf4272833f3430d9fb68521c`
- pull_request Verify #373
- tests: 1587 passed / 0 failed
- artifact: `verification-3064816c03be1efdbf4272833f3430d9fb68521c`
- artifact digest: `sha256:5b97f77ae6a2b59a4e2e1b319fb992f4a7b9ffe3f3491126f88a7d8e8ce83c31`

### Squash-main verification

- exact main SHA: `9a8b290333428334f76903c4bf6284863b930f06`
- push Verify #374
- tests: 1587 passed / 0 failed
- artifact: `verification-9a8b290333428334f76903c4bf6284863b930f06`
- artifact digest: `sha256:1a8272687166b2dc82d9ee7bb069b4103b863b88db65d03b260db253ab2be470`

## Verification semantics

- feature push, synthetic merge-ref, and squash-main evidence remain distinct;
- no evidence is transferred between different SHAs;
- workflow/test-manifest evidence is not independent external verification;
- `externally_verified=False`.

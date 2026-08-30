# Current Checkpoint v645-v651

Date: 2026-08-31

Package: Existing User Record Integrity v1

## Verified implementation

AssistantUserStorageService now distinguishes a persisted user key from an absent user before deciding whether creation is allowed, and validates the canonical existing-user record shape without auto-healing corrupted evidence.

Verified behavior:

- an existing user key with `null` fails closed and is not recreated;
- an existing empty object no longer passes validation through default values;
- existing records require explicit `memory` dict and `history` list fields;
- the embedded `user_id` must match the normalized storage key;
- malformed existing records return `USER_STORAGE_USER_INVALID` and remain untouched;
- optional context remains compatible;
- truly absent users retain the normal creation path;
- no migration or auto-repair mutates corrupted persisted evidence;
- no business execution, Product Decision/Product Task Draft execution, or Ozon mutation is introduced;
- `data/users.json` remains untouched.

## Architecture Review

Architecture Review Required: Yes.

Reason:

- persisted user-record validity semantics changed at the storage boundary.

Critical Review Required: No.

Review result:

- existing persistence owner and JSON format are preserved;
- no new persistence layer;
- no automatic corruption repair;
- no business execution capability added;
- no Ozon mutation;
- `data/users.json` untouched.

## SHA-bound verification evidence

### Entering verified main

- exact SHA: `f9c66a59fe185bcd81f5c8f428120fd3e3c2bf86`
- push Verify #336
- tests: 1544 passed / 0 failed
- artifact: `verification-f9c66a59fe185bcd81f5c8f428120fd3e3c2bf86`
- artifact digest: `sha256:5897b43da8989cf6c3bf410378f7bf03c1d31c240410568dc3b644cc6239a15c`

### Exact final feature head

- branch: `fix/existing-user-record-integrity-v645-v651`
- exact SHA: `3f8f4fabce0feba50f745b308ccbdf20cb6ccf99`
- push Verify #339
- tests: 1551 passed / 0 failed
- artifact: `verification-3f8f4fabce0feba50f745b308ccbdf20cb6ccf99`
- artifact digest: `sha256:84e68a8ce1ee924756efca7620d50720c1762d014b0b696997b5539902354434`

### PR synthetic merge-ref

- PR #262
- exact feature head: `3f8f4fabce0feba50f745b308ccbdf20cb6ccf99`
- synthetic merge SHA: `d579316aa809344e88e3db967967954a064038bd`
- pull_request Verify #340
- tests: 1551 passed / 0 failed
- artifact: `verification-d579316aa809344e88e3db967967954a064038bd`
- artifact digest: `sha256:6321f96e23133f6069d1ba7c77eb000c239c6bbfc9509f6bdd4f68c4ea6483d0`

### Squash-main verification

- exact main SHA: `4fc8b894d463781902226ebf92c5a260761d8762`
- push Verify #341
- tests: 1551 passed / 0 failed
- artifact: `verification-4fc8b894d463781902226ebf92c5a260761d8762`
- artifact digest: `sha256:e1f90db4426be801e5b902aebcae9af1561649c689f3090d0d62c5eef85c99b7`

## Verification semantics

- feature push, synthetic merge-ref, and squash-main evidence remain distinct;
- no evidence is transferred between SHAs;
- workflow/test-manifest evidence is not independent external verification;
- `externally_verified=False`.

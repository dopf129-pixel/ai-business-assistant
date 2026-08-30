# Current Checkpoint v687-v695

Date: 2026-08-31

Package: Telegram User Admission Integrity v1

## Verified implementation

Identified Telegram requests now require valid canonical user-profile admission before successful downstream runtime dispatch.

Verified behavior:

- explicit user-profile storage errors block /start before keyboard success;
- explicit user-profile storage errors block text before memory-command or assistant dispatch;
- explicit user-profile storage errors block buttons before button-handler dispatch;
- malformed create_user results fail closed;
- create_user exceptions become stable non-secret failure codes;
- valid canonical user admission preserves start/text/button behavior;
- no-user-id legacy paths remain compatible;
- no new persistence layer or owner was introduced;
- no Product Decision/Product Task Draft execution or Ozon mutation is introduced;
- `data/users.json` remains untouched.

## Architecture Review

Architecture Review Required: Yes.

Reason:

- production Telegram admission semantics now gate downstream runtime dispatch on canonical persisted-user availability;
- package exceeds 300 changed lines including focused tests.

Critical Review Required: No.

Review result:

- canonical AssistantUserStorageService remains the persistence owner;
- no architecture replacement or migration;
- no autonomous business execution capability added;
- no Ozon mutation;
- `data/users.json` untouched.

## SHA-bound verification evidence

### Entering verified main

- exact SHA: `e666eae65467fde17041ac807382fa298ac1e69b`
- push Verify #377
- tests: 1587 passed / 0 failed
- artifact: `verification-e666eae65467fde17041ac807382fa298ac1e69b`
- artifact digest: `sha256:e7fcb5fb9ae0c32feac5830f4873d9df1e1e4a7c4b3431a34fca4e24a403ad38`

### Exact final feature head

- branch: `fix/telegram-user-admission-integrity-v687-v695`
- exact SHA: `9c778fc9911fa956960c17aa03c490a48aee100c`
- push Verify #378
- tests: 1596 passed / 0 failed
- artifact: `verification-9c778fc9911fa956960c17aa03c490a48aee100c`
- artifact digest: `sha256:b358d74fbe5906900bf5afb324d646212459ccbc7ded2c33928785bd86b9fdf9`

### PR synthetic merge-ref

- PR #272
- exact feature head: `9c778fc9911fa956960c17aa03c490a48aee100c`
- synthetic merge SHA: `02362780db074ed45c4ca23bbeacfda12320d504`
- pull_request Verify #379
- tests: 1596 passed / 0 failed
- artifact: `verification-02362780db074ed45c4ca23bbeacfda12320d504`
- artifact digest: `sha256:5004c5540377f6a13d54c4c82f3fcd256949fd5e19addcfae220a9c652c806aa`

### Squash-main verification

- exact main SHA: `4b687f2d00c04f8d00d4a34f9801156639a1cf0b`
- push Verify #380
- tests: 1596 passed / 0 failed
- artifact: `verification-4b687f2d00c04f8d00d4a34f9801156639a1cf0b`
- artifact digest: `sha256:7dc1eddf89b22601fa373d08f6763fd1532b91e383cd9fdc451fe093d6dcd5a7`

## Verification semantics

- feature push, synthetic merge-ref, and squash-main evidence remain distinct;
- no evidence is transferred between different SHAs;
- workflow/test-manifest evidence is not independent external verification;
- `externally_verified=False`.

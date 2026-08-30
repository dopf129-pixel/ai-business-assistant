# Verification Status

Date: 2026-08-31

## Latest verified product baseline

`4b687f2d00c04f8d00d4a34f9801156639a1cf0b`

Latest merged production-correctness batch:

`v687-v695: Telegram User Admission Integrity`

### Entering exact-main verification

- exact main: `e666eae65467fde17041ac807382fa298ac1e69b`
- push Verify #377
- conclusion: success
- tests: 1587 passed / 0 failed
- artifact: `verification-e666eae65467fde17041ac807382fa298ac1e69b`
- artifact digest: `sha256:e7fcb5fb9ae0c32feac5830f4873d9df1e1e4a7c4b3431a34fca4e24a403ad38`

### Exact final feature-head verification

- branch: `fix/telegram-user-admission-integrity-v687-v695`
- exact SHA: `9c778fc9911fa956960c17aa03c490a48aee100c`
- push Verify #378
- conclusion: success
- tests: 1596 passed / 0 failed
- artifact: `verification-9c778fc9911fa956960c17aa03c490a48aee100c`
- artifact digest: `sha256:b358d74fbe5906900bf5afb324d646212459ccbc7ded2c33928785bd86b9fdf9`

### PR merge-ref integration verification

- PR #272
- branch head: `9c778fc9911fa956960c17aa03c490a48aee100c`
- synthetic merge SHA: `02362780db074ed45c4ca23bbeacfda12320d504`
- pull_request Verify #379
- conclusion: success
- tests: 1596 passed / 0 failed
- artifact: `verification-02362780db074ed45c4ca23bbeacfda12320d504`
- artifact digest: `sha256:5004c5540377f6a13d54c4c82f3fcd256949fd5e19addcfae220a9c652c806aa`

This is synthetic merge-ref integration evidence only.

### Post-merge exact-main verification

- exact main: `4b687f2d00c04f8d00d4a34f9801156639a1cf0b`
- push Verify #380
- conclusion: success
- tests: 1596 passed / 0 failed
- artifact: `verification-4b687f2d00c04f8d00d4a34f9801156639a1cf0b`
- artifact digest: `sha256:7dc1eddf89b22601fa373d08f6763fd1532b91e383cd9fdc451fe093d6dcd5a7`

## Telegram User Admission Integrity

AssistantTelegramAdapter now treats canonical persisted-user admission as a fail-closed prerequisite for identified Telegram users.

Explicit user-storage errors, malformed profile results, and profile exceptions stop successful /start, text, and button downstream dispatch. Successful canonical admission preserves existing behavior, while no-user-id compatibility remains unchanged.

No persistence owner or layer changed. No business execution authorization, Product Decision/Product Task Draft execution, or Ozon mutation was introduced. Repository `data/users.json` was not modified.

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Workflow/test-manifest evidence is not independent external verification;
`externally_verified=False`.

## Related implementation

- `app/telegram_app_layer/assistant_telegram_adapter.py`
- `tests/test_telegram_user_admission_integrity_v687_v695.py`
- `project_brain/CURRENT_CHECKPOINT_V687_V695.md`

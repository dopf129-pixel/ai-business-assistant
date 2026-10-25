# Daily-use backup review fixes R1–R3

Date: 2026-10-25
Scope: confirmed review findings in PR #715 (backup/restore), inherited by PRs #716 and #717.

## R1 — real application list files rejected

`BotBackupService` previously treated every JSON file outside three product-decision names as an object. The real `ActionStorageService`, `ConversationHistoryStorageService`, and `StoreReportStorageService` write arrays, so a normal installation containing any of these files could not produce a backup. `LIST_JSON_FILES` now includes all three names, and both source and archive validation use case-insensitive basename matching. The regression writes data through each production storage class, then verifies, dry-runs and restores the archive.

## R2 — bot could start during snapshot

Checking `STOPPED` once did not exclude a concurrent startup. A token-scoped `BotStartupMaintenanceGuard` now serializes the full backup with bot startup. Backup takes the guard before lifecycle inspection and holds it until publication or failure cleanup. `BotInstanceLease.acquire()` takes the same guard while acquiring its long-lived instance lock and publishing `STARTING`; it returns `BOT_INSTANCE_MAINTENANCE_ACTIVE` if a snapshot owns the guard. If startup acquires the guard first, the backup cannot acquire it and exits as `BOT_BACKUP_STARTUP_BUSY`. If another instance is already live, lifecycle inspection under the guard still returns the existing stopped-state refusal. Synthetic interleaving confirms startup cannot enter while both files are read.

## R3 — configured mapping registry was not restorable

Discovery accepted a configured JSON mapping registry under an approved root, but restore only accepted hard-coded filenames. The archive manifest now records the exact relative `(root, path)` of a discovered configured mapping file. Verification validates that descriptor against a listed JSON entry and the restore allowlist before a dry-run can succeed. Actual restore applies the same descriptor. Root selection uses the longest matching approved root, so a nested storage directory is restored under `storage/` instead of being mislabeled as `project/`. External paths remain rejected.

Regression coverage checks project, nested storage, and separate approved storage roots through backup, archive verification, dry-run and actual restore. A separate case confirms backup refuses without publishing when startup owns the guard. Old archives without a mapping descriptor continue to work for the pre-existing allowlist; unsupported entries are rejected during verification instead of receiving a misleading restore plan.

## Verification

- Focused Windows profile: `tests/test_bot_backup_service.py` and `tests/test_bot_instance_lifecycle_service.py` — **32 passed in 1.93s**.
- `compileall -q app tests` and `git diff --check` passed. Compile emitted one existing `SyntaxWarning` in an unchanged test module.
- The first pytest invocation stopped during collection because the application directory was not on `PYTHONPATH`; after correcting invocation, the test suite passed.
- Exact-head CI for PR #715 and descendants is required after forwarding this fix through the stack. No merge, deployment, real bot start, Telegram/Ozon API call, or user-data access was performed.

## Review classification

Architecture review required: the existing lifecycle lock contract now includes a short-lived startup/snapshot guard shared by startup and backup. No new external dependency or persistence store was added.

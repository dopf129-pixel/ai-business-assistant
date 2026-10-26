# Daily-use readiness D02 — staged restore verification

## Result

Status: **VERIFIED_OFFLINE** on generated synthetic data. Restore writes only to a new destination path and publishes a completed staging directory atomically. It never replaces the active project/storage root and never writes `.env` or a credential key.

The archive is verified before any staging directory is created. Manifest version, exact archive membership, completion marker, safe relative paths, duplicate Windows-normalized paths, file/count/expanded-size limits, SHA-256 values, JSON shape and SQLite integrity are checked. Restore paths are constrained to the backup v1 allowlist. Symlink/reparse ZIP members, traversal, unsupported files, existing destinations, and destinations overlapping current roots fail closed.

`restore_bot.ps1` offers `-CheckOnly`, which verifies archive and destination without writing. Actual restore writes into a unique staging sibling, verifies each payload again while copying, writes `RESTORED.json` last, and renames staging to the requested new directory. Restored layout is `<target>/project/...` and `<target>/storage/...`; app code and `.env` are not included. Encrypted Ozon credentials require the separately held original `OZON_CREDENTIAL_MASTER_KEY`.

## Verification

Focused Windows/Python 3.12 profile: `tests/test_bot_backup_service.py` — **13 passed in 0.69s**. It covers D01 backup plus D02 dry-run/no-write, restore from synthetic archive, two distinct tenant identities read through the existing `ExpenseRepository` before and after restore, source-data preservation, existing/live-root target rejection, interrupted restore cleanup, CLI `--dry-run`, and ZIP traversal/link/duplicate/expanded-size refusal.

Python `py_compile` passed for `app/services/bot_backup_service.py` and `app/bot_backup.py`. PowerShell parser accepted `backup_bot.ps1` and `restore_bot.ps1`. `git diff --check` passed.

## Operator flow and rollback

1. Check and stop only this bot instance; backup refuses unless the token-bound lifecycle state is `STOPPED`.
2. Run `backup_bot.ps1`, then verify the produced archive with `python -m bot_backup verify <archive>`.
3. Run `restore_bot.ps1 -ArchivePath <archive> -TargetDirectory <new-sibling-path> -CheckOnly` first. Remove `-CheckOnly` only when a real restore is explicitly intended; the target must not exist.
4. Restore is a data staging copy, not an application checkout. To test a restored copy later, use a separate application checkout, place the `project` data beneath that checkout, and run with `AI_ASSISTANT_STORAGE_ROOT` explicitly pointed at the restored `storage` directory. Keep the current checkout and its `.env` untouched.
5. Roll back the test by stopping that test instance, closing its PowerShell session (which clears the process-scoped storage override), and returning to the original checkout and its original `.env`/storage root. No restore command changes the original roots.

## Limitations

- No actual owner backup/restore or real bot launch was performed. Application-level live activation and rollback are intentionally left for owner acceptance after D03–D06.
- The staged `project` root contains only data files; it does not contain executable application code. The instruction above requires a separate application checkout for any future activation test.
- Atomic rename protects publication on the tested local filesystem. Exact-head Windows/Linux CI still needs to repeat this profile.

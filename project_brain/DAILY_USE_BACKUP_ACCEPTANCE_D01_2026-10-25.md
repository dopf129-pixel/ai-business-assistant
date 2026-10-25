# Daily-use readiness D01 — verified local backup

## Result

Status: **VERIFIED_OFFLINE** on synthetic data. No real database, user JSON, `.env`, Ozon API, Telegram API, bot process, or user store was accessed.

`backup_bot.ps1` delegates to a narrow local Python CLI. The backup refuses to run without a lifecycle token and a confirmed `STOPPED` state; it never stops a process. It discovers the allowlisted legacy/project JSON and SQLite paths plus supported JSON/SQLite files under hashed tenant directories. A configured mapping registry outside the approved project/storage roots is rejected.

SQLite files are snapshotted through SQLite's backup API in read-only mode and checked with `integrity_check`. JSON files must parse and satisfy the existing list/object shape contract. The archive contains only relative paths, sizes, SHA-256 checksums, format/schema metadata, application revision, and a completion marker written after verification. `.env`, keys, Git state, logs, caches, and unsupported files are excluded. Publication uses a partial archive followed by verification, fsync, and atomic rename. Existing archives are not pruned.

## Verification

Command: focused Windows pytest profile for `tests/test_bot_backup_service.py` using the repository Python 3.12 virtual environment; exact-head CI remains required.

Result: **7 passed in 0.46s**. Coverage includes Unicode/spaced roots, legacy and tenant JSON/SQLite, source immutability, secret exclusion, lifecycle running refusal, invalid JSON, invalid SQLite, external mapping path refusal, interrupted publication preserving a prior archive, and rejection of unlisted ZIP members.

`py_compile` passed for `app/services/bot_backup_service.py` and `app/bot_backup.py`. `git diff --check` reported only pre-existing trailing blank-line additions at the ends of `CURRENT_STATE.md` and `TEST_MAP.md`; those are removed in this stage before handoff.

## Limitations

- Disk-full and OS permission failure paths are represented by publication-failure injection; real disk-full behavior was not induced.
- The command must be run after the owner has stopped the bot. It does not touch process lifecycle.
- Restore, update orchestration, and use against owner data are not covered here; D02–D04 and E acceptance remain pending.
- The current local Windows pytest sandbox initially denied temporary-directory access. Focused tests passed after running in the authorized isolated worktree environment. CI must repeat storage-backed tests on the exact PR head.

## Operator command

From the project directory, after stopping the bot:

```powershell
.\backup_bot.ps1
```

The command prints a local archive path and sanitized verification summary. Keep the original `OZON_CREDENTIAL_MASTER_KEY` separately; encrypted credentials require the same key after restoration.

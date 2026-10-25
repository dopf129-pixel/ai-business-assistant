# Daily-use readiness D01 — verified local backup

## Result

Status: **VERIFIED_OFFLINE** on synthetic data. No real database, user JSON, `.env`, Ozon API, Telegram API, bot process, or user store was accessed.

`backup_bot.ps1` delegates to a narrow local Python CLI. The backup refuses to run without a lifecycle token and a confirmed `STOPPED` state; it never stops a process. It discovers the allowlisted legacy/project JSON and SQLite paths plus supported JSON/SQLite files under hashed tenant directories. A configured mapping registry outside the approved project/storage roots is rejected.

SQLite files are snapshotted through SQLite's backup API in read-only mode and checked with `integrity_check`. JSON files must parse and satisfy the existing list/object shape contract. The archive contains only relative paths, sizes, SHA-256 checksums, format/schema metadata, application revision, and a completion marker written after verification. `.env`, keys, Git state, logs, caches, and unsupported files are excluded. Publication uses a partial archive followed by verification, fsync, and atomic rename. Existing archives are not pruned.

## Review remediation R1–R3 (2026-10-25)

- The list/object contract includes the real application writers for `actions.json`, `conversation_history.json`, and `store_reports.json`; creation and verification use the same filename rule.
- Backup takes a token-scoped startup guard before checking lifecycle state and holds it through verified publication. `BotInstanceLease` takes the same guard while acquiring the long-lived instance lock, so startup cannot overlap the snapshot and a running/starting bot still causes a fail-closed result.
- An explicitly configured mapping registry inside an approved root is recorded in the manifest as a root-relative path. When project and storage roots overlap, the most specific root is selected. Archive verification validates restore support before dry-run reports success; actual restore uses the same descriptor. External mapping paths remain unsupported.
- Regression coverage uses the three production storage classes, synthetic interleaving, and project/nested/separate storage roots. Focused Windows result: **32 passed in 1.93s**; `compileall -q app tests` and `git diff --check` passed. Compile emitted one existing SyntaxWarning in an unchanged test. Exact-head Verify #715 `40185833721`, #716 `40185869091`, and #717 `40186507007` passed on Windows/Linux; #717's full suite passed **3,728 tests per platform**.
- The bounded lifecycle soak counts the startup/snapshot kernel-lock file as one of three persistent files (instance metadata, instance lease lock, startup/snapshot lock). Lock files are retained across cycles to prevent concurrent processes from locking separate inodes for the same token namespace.

## Verification

Command: focused Windows pytest profile for `tests/test_bot_backup_service.py` using the repository Python 3.12 virtual environment; integrated exact-head CI is recorded above.

Historical D01 baseline result: **7 passed in 0.46s**. Coverage included Unicode/spaced roots, legacy and tenant JSON/SQLite, source immutability, secret exclusion, lifecycle running refusal, invalid JSON, invalid SQLite, external mapping path refusal, interrupted publication preserving a prior archive, and rejection of unlisted ZIP members. The latest R1–R3 result above supersedes this count.

`py_compile` passed for `app/services/bot_backup_service.py` and `app/bot_backup.py`. `git diff --check` reported only pre-existing trailing blank-line additions at the ends of `CURRENT_STATE.md` and `TEST_MAP.md`; those are removed in this stage before handoff.

## Limitations

- Disk-full and OS permission failure paths are represented by publication-failure injection; real disk-full behavior was not induced.
- The command must be run after the owner has stopped the bot. It does not touch process lifecycle.
- This D01 acceptance does not itself validate restore, update orchestration, or use against owner data; restore and update are covered by D02–D05 and the integrated E00/CI profiles. Production data remains unverified pending the owner evidence in E03.
- The current local Windows pytest sandbox initially denied temporary-directory access. Focused tests passed after running in the authorized isolated worktree environment. CI must repeat storage-backed tests on the exact PR head.

## Operator command

From the project directory, after stopping the bot:

```powershell
.\backup_bot.ps1
```

The command prints a local archive path and sanitized verification summary. Keep the original `OZON_CREDENTIAL_MASTER_KEY` separately; encrypted credentials require the same key after restoration.

# Windows local handoff

This project supports a Windows-first local handoff path for a trusted recipient who runs the bot from PowerShell with their own Telegram bot token and their own Ozon seller credentials.

For a compact set of copyable status, backup, restore, update, credential-recovery,
and diagnostic steps, see [the daily-use recovery runbook](daily-use-recovery-runbook.md).

## Supported local runtime

Use Python 3.12. The repository-level `start_bot.ps1` script is the supported Windows bootstrap and launcher. On first run it:

- requires the Windows `py` launcher with Python 3.12 available;
- creates `.venv` when missing;
- installs `requirements.txt` into that environment;
- creates a gitignored `.env` when missing;
- generates a fresh Fernet `OZON_CREDENTIAL_MASTER_KEY` locally without printing it;
- configures `AI_ASSISTANT_STORAGE_ROOT=.runtime-data` for persistent local runtime data;
- asks the operator to place their own `TELEGRAM_BOT_TOKEN` into `.env`;
- launches the canonical `python -m telegram_api_bot` entrypoint through the virtual environment.

Subsequent runs reuse the same `.env`, master key, virtual environment, and `.runtime-data` storage. Do not regenerate the master key after Ozon credentials have been saved: the same key is required to decrypt the stored ciphertext after restart.

If `/start` reports that a connection is already stored but cannot be decrypted,
restore the original `OZON_CREDENTIAL_MASTER_KEY` in `.env` and keep the existing
`.runtime-data` directory. Reconnecting with a new key does not recover the saved
encrypted record. For a storage-path error, check that `AI_ASSISTANT_STORAGE_ROOT`
still points to the same writable directory used before.

## Local backup and staged restore

Backups are local data archives; they do not contain application code, `.env`,
Telegram/Ozon keys, logs, or Git state. Stop the token-bound bot with
`stop_bot.ps1` before running `backup_bot.ps1`; backup refuses any lifecycle
state other than confirmed `STOPPED` and never stops the process itself.

`status_bot.ps1` displays polling readiness separately from local configuration.
`RUNNING` means PTB polling and update handling were confirmed; `STARTING` means
the process is not ready yet, and `STOPPED` means its lifecycle lock is free.
The configuration check is offline and does not validate Telegram/Ozon access.
A bad configuration status can coexist with a previously running process; it
describes the current local settings. The last captured startup/polling failure
is shown only as a safe code. Use the report completeness diagnostics for Ozon
source failures and calculation gaps.

```powershell
.\status_bot.ps1
```

```powershell
.\stop_bot.ps1
```

```powershell
.\backup_bot.ps1
```

The backup command returns a verified ZIP path under `.local-backups`. Verify it
without extracting it:

```powershell
.\.venv\Scripts\python.exe -m bot_backup verify ".\.local-backups\<archive-name>.zip"
```

Before restore, select a destination path that does not exist and is outside the
current project and storage roots. First validate the plan without writes:

```powershell
.\restore_bot.ps1 -ArchivePath ".\.local-backups\<archive-name>.zip" -TargetDirectory "..\restore-drill" -CheckOnly
```

To create the staged data copy, run the same command without `-CheckOnly`. It
creates `restore-drill\project` and `restore-drill\storage`, but does not start
the bot, change `.env`, or switch the current checkout. The destination contains
data only, not the application code.

For a future activation test, use a separate application checkout. Place the
restored `project` data under that checkout and launch it with a process-scoped
`AI_ASSISTANT_STORAGE_ROOT` pointing at the restored `storage` directory. Keep
the current checkout and its `.env` untouched. To roll back that test, stop its
bot, close the PowerShell window to clear the process-scoped storage override,
and return to the original checkout. The original storage root and `.env` remain
unchanged by backup and restore.

Encrypted credentials can be decrypted only with the original
`OZON_CREDENTIAL_MASTER_KEY`. Keep that key separately and never add it to the
archive or command line.

## Checked local update

Run the read-only preflight first. It does not fetch or change files:

```powershell
.\update_bot.ps1 -CheckOnly
```

To perform the supported update, use the default mode. It fetches the official
`origin/main`, checks the exact commit, gracefully stops only the running bot
from this project folder, verifies a local backup, updates with fast-forward,
checks dependencies and local startup settings, starts the bot in background,
and waits until polling is reported ready:

```powershell
.\update_bot.ps1
```

To update and leave the bot stopped after local checks:

```powershell
.\update_bot.ps1 -NoStart
```

The updater blocks before stopping the bot if the checkout is on the wrong branch,
has unsafe local changes, or the running instance cannot be tied to this folder.
It never stashes, resets, cleans, or force-kills Python. If it reports that the
bot is stopped and the update did not finish, inspect the reported backup path
and run the read-only check:

```powershell
.\update_bot.ps1 -CheckOnly
```

The updater does not restore data or roll Git back automatically. Resolve the
reported Git/dependency/runtime issue before starting the bot again. A current
version exits without restarting the process.

## Secrets

`.env` and `.runtime-data/` are gitignored. `.env.example` contains placeholders only. Never copy another seller's Telegram token, Ozon Client ID, Ozon API key, `.env`, local database, or runtime data into a handoff package.

The canonical Python entrypoint loads `.env` for local use. Existing process environment variables still take precedence, so the same entrypoint remains compatible with production/container deployment.

## Windows shutdown behavior

`python-telegram-bot` signal-handler registration is not supported by the standard Windows event loop. The Telegram runner therefore passes `stop_signals=None` on Windows and retains explicit `SIGINT`/`SIGTERM` handling on POSIX systems. This removes the Windows `PTBUserWarning` without changing Linux container shutdown semantics.

## Ozon safety boundary

Ozon integration remains read-only. The local handoff path does not add seller-side mutation capability. It does not create accounting facts, does not execute Return COGS commitments, and does not change Period Profit execution semantics.

Return COGS invariants remain unchanged: `ReturnedToOzon` is candidate evidence only, unknown is not zero, guessed quantity × cost is forbidden, and inventory presentation becomes authoritative only under the canonical ready status plus supported inventory state.

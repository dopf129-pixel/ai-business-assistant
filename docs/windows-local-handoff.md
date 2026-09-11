# Windows local handoff

This project supports a Windows-first local handoff path for a trusted recipient who runs the bot from PowerShell with their own Telegram bot token and their own Ozon seller credentials.

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

## Secrets

`.env` and `.runtime-data/` are gitignored. `.env.example` contains placeholders only. Never copy another seller's Telegram token, Ozon Client ID, Ozon API key, `.env`, local database, or runtime data into a handoff package.

The canonical Python entrypoint loads `.env` for local use. Existing process environment variables still take precedence, so the same entrypoint remains compatible with production/container deployment.

## Windows shutdown behavior

`python-telegram-bot` signal-handler registration is not supported by the standard Windows event loop. The Telegram runner therefore passes `stop_signals=None` on Windows and retains explicit `SIGINT`/`SIGTERM` handling on POSIX systems. This removes the Windows `PTBUserWarning` without changing Linux container shutdown semantics.

## Ozon safety boundary

Ozon integration remains read-only. The local handoff path does not add seller-side mutation capability. It does not create accounting facts, does not execute Return COGS commitments, and does not change Period Profit execution semantics.

Return COGS invariants remain unchanged: `ReturnedToOzon` is candidate evidence only, unknown is not zero, guessed quantity × cost is forbidden, and inventory presentation becomes authoritative only under the canonical ready status plus supported inventory state.

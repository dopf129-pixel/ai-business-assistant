# Daily-use readiness D04 — checked update and readiness

## Result

Status: **VERIFIED_OFFLINE** with mocked process, backup, command and update boundaries. `update_bot.ps1` now has three explicit modes:

- `-CheckOnly`: read-only local preflight, with no fetch or lifecycle action;
- default: fetch `origin/main`, validate the fetched SHA, stop only the token-bound instance proven to belong to this checkout, create and verify a backup, fast-forward to that exact SHA, check dependencies/code/environment, start in background and confirm polling readiness;
- `-NoStart`: perform the same checked update, leave the bot stopped after local checks.

The update must start in the project's `main` checkout tracking the canonical `origin/main`. It does not stash/reset/clean, does not accept an arbitrary ref, and does not force-terminate Python processes. It preserves only the exact legacy local `data/tasks.json`/`data/users.json` cases allowed by D03, provided incoming changes do not overlap them. Each Git ref is pinned to the validated full SHA; the preflight is repeated after stop, after backup, and before the fast-forward.

Updater instances serialize through a non-blocking OS lock under the current worktree's private Git directory. Already-current code returns `BOT_UPDATE_ALREADY_CURRENT` without backup, stop, or restart. A requirements change always triggers `pip install -r requirements.txt`; otherwise `pip check` runs and install is the fallback. The updater then runs `compileall` and the existing offline `runtime_healthcheck`. A normal update returns success only when the lifecycle reports `RUNNING` on the exact target revision and checkout fingerprint.

Any failure after a confirmed stop reports whether the process remains stopped, the verified backup path when one exists, and the read-only recovery check command. No automatic rollback or business-data restore is performed. The CLI suppresses raw command errors and secrets.

## Verification

Windows/Python 3.12, isolated synthetic services and repositories:

```powershell
$py = 'C:\Users\gelashvilee\Desktop\Ai ассистент\.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path (Get-Location).Path 'app'
& $py -m py_compile app/services/bot_update_runtime_service.py app/bot_update.py
& $py -m pytest -p no:cacheprovider -q --tb=short tests/test_bot_update_runtime_service.py tests/test_bot_update_preflight_service.py tests/test_bot_backup_service.py tests/test_bot_instance_lifecycle_service.py
```

Result: **54 passed in 11.84s**. The profile covers successful no-start and readiness paths; no-op current version; wrong identity; fetch/preflight/stop/backup/verification/merge/dependency/compile/health/start/readiness failures; foreign checkout; revision movement after stop and backup; requirements-triggered install; updater lock contention and OS-kernel lock serialization; CLI `-NoStart` and token redaction; backup/restore/lifecycle regressions.

Python compilation passed. Direct PowerShell parser API reported **0 parse errors** for both `update_bot.ps1` and `start_bot.ps1`. `git diff --check` passed.

## Exact boundary of this verification

- No real Git remote was fetched and no owner repository ref was changed.
- No real `.env`, seller data, backup archive, or bot process was accessed.
- All updater network/process/backup/command effects were injected fakes; the only Git repository created was a temporary synthetic repository for kernel-lock testing.
- Full Windows/Linux exact-head CI and independent architecture review are still required.

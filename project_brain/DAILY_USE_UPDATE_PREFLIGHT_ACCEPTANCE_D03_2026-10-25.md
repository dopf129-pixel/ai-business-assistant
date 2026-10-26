# Daily-use readiness D03 — read-only update preflight

## Result

Status: **VERIFIED_OFFLINE** with isolated synthetic Git repositories and lifecycle state. The planner accepts only the expected repository root, branch `main`, upstream `origin/main`, and the project's canonical HTTPS/SSH remote. It pins the fetched/cached `origin/main` commit SHA in the plan and marks a cached ref as potentially stale. It does not fetch, pull, checkout, reset, stash, clean, install dependencies, stop/start the bot, or call Ozon/Telegram.

It reports current/target revision, branch/tracking, behind count, whether `requirements.txt` changes, whether a backup is needed, and token-bound process state. It blocks wrong roots/branches/remotes/upstream, local commits ahead, unsafe dirty code, conflicting untracked paths, changes to protected `data/tasks.json`/`data/users.json`, unknown lifecycle state, and a running/starting/stopping process that cannot be proven to belong to the current checkout.

The lifecycle metadata now contains a one-way SHA-256 fingerprint of the normalized project root. It does not persist the path. Older active processes without this field fail closed and must be stopped manually. Graceful stop checks the expected checkout fingerprint before issuing authenticated loopback control; PID is never used to terminate a process.

The CLI shows a concise Russian summary plus sanitized JSON. Token, master key, `.env` contents, and remote credentials are not included.

## Verification

Windows/Python 3.12:

```powershell
$py = 'C:\Users\gelashvilee\Desktop\Ai ассистент\.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path (Get-Location).Path 'app'
& $py -m pytest -p no:cacheprovider -q --tb=short tests/test_bot_update_preflight_service.py tests/test_bot_instance_lifecycle_service.py
```

Result: **24 passed in 10.54s**. Coverage includes current/behind refs, requirements changes, an unchanged running bot, same/foreign checkout fingerprint, modified tracked and ignored protected data, incoming protected-data conflict, dirty code, untracked overwrite, local divergence, wrong root/branch/remote/upstream, unknown lifecycle, stop refusal for an old/foreign checkout, and CLI redaction. Synthetic Git tests assert no fetch or mutating Git calls and unchanged worktree/process state.

`py_compile` passed for the preflight service and CLI. The PowerShell parser accepted `update_bot.ps1` and `start_bot.ps1`. `git diff --check` passed.

## Owner check

From the project directory:

```powershell
.\update_bot.ps1 -CheckOnly
```

This command uses cached `origin/main`; if it is stale, it shows that limitation. It remains read-only. D04 adds the explicit fetch and runs the same planner against the exact fetched commit SHA.

## Limitations

- No owner checkout, live process, `.env`, Git remote fetch, or bot was used.
- Exact-head CI is still required. All Git repositories used by local tests are generated synthetic fixtures.

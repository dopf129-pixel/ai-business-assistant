# Daily-use readiness D05 — process status and safe diagnostics

## Result

Status: **VERIFIED_OFFLINE**.

`status_bot.ps1` now reports two independent facts: whether Telegram polling is actually ready (`STOPPED`, `STARTING`, `RUNNING`, `STOPPING`, or `UNKNOWN`) and whether the current local environment passes the existing offline healthcheck. It also reports the process revision, launch time, foreground/background mode, whether the process belongs to this checkout, and an allowlisted last startup/polling failure code. It never prints the checkout path or its fingerprint.

Environment diagnosis maps only known healthcheck outcomes to safe codes. It does not echo key syntax, token values, paths, exceptions, Telegram/Ozon payloads, or environment contents. The healthcheck remains filesystem/environment only; it does not contact Telegram/Ozon or initialize seller repositories. The process state remains based on the existing lifecycle OS lock and PTB readiness contract, not PID presence.

`stop_bot.ps1` now scopes the graceful stop to the current checkout. A foreign or old process whose checkout fingerprint is missing is left alone. Startup/polling exceptions caught by the canonical runner are reduced to safe allowlisted codes; only those codes persist in lifecycle metadata. Older metadata remains readable when the optional failure code is absent.

The existing `/about_bot` build metadata and Period Profit support JSON now include the allowlisted foreground/background mode. Support JSON keeps its existing size bound and reconstructs an allowlisted schema; invalid mode becomes `UNAVAILABLE`.

## Verification

Windows/Python 3.12:

```powershell
$py = 'C:\Users\gelashvilee\Desktop\Ai ассистент\.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path (Get-Location).Path 'app'
& $py -m py_compile app/telegram_bot_control.py app/services/bot_instance_lifecycle_service.py app/telegram_app_layer/telegram_api_bot.py app/services/app_build_metadata_service.py app/services/period_profit_support_diagnostic_export_service.py
& $py -m pytest -p no:cacheprovider -q --tb=short tests/test_telegram_bot_control_cli.py tests/test_app_build_metadata_service.py tests/test_period_profit_support_diagnostic_export_service.py tests/test_bot_instance_lifecycle_service.py tests/test_telegram_runtime_health_shutdown_contract.py tests/test_windows_local_handoff_readiness.py tests/test_bot_update_runtime_service.py tests/test_bot_update_preflight_service.py tests/test_bot_backup_service.py
```

Result: **87 passed in 13.27s**. Coverage includes missing/invalid token/key/storage states; checkout identity and foreign process; allowlisted failure persistence and redaction; startup/polling exceptions; build metadata and support export; lifecycle lock/readiness; updater and backup regressions. Existing runtime healthcheck tests assert no network or storage creation.

PowerShell parser API reported **0 errors** for `update_bot.ps1`, `start_bot.ps1`, `status_bot.ps1`, and `stop_bot.ps1`. Python compilation passed. No real bot, Git remote, owner `.env`, or seller data was used.

## Limitations

- Failure code recording covers exceptions that leave the canonical `main()` runner. It does not capture every asynchronous library log event while polling continues.
- Runtime healthcheck validates local startup prerequisites; a green result does not prove an Ozon source is available or a financial calculation is complete. Those statuses remain in the calculation diagnostics.
- Exact-head Windows/Linux CI is required.

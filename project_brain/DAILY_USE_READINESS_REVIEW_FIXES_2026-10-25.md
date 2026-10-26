# Daily-use readiness — confirmed review fixes

## Follow-up review corrections (2026-10-26)

Повторный review двух дополнительных дефектов в PR #717 выявил, что exact-path проверка пропускала игнорируемый файл/папку при замене его Git-потомком или Git-предком, а пример restore dry-run передавал `..` в строгий валидатор target.

- Preflight перечисляет ignored локальные пути с `git ls-files --others --ignored --exclude-standard --directory -z` и блокирует любой входящий изменённый путь, который пересекается с ними по точному совпадению либо границе предок/потомок. Перечисление схлопывает целые ignored directories, чтобы не обходить содержимое runtime-каталогов.
- Git fast-forward дополнен `--no-overwrite-ignore` как последним предохранителем от path-shape collision, если локальное состояние изменится после preflight.
- Runbook теперь нормализует sibling `restore-drill` через PowerShell `GetFullPath` до вызова restore service; service сохраняет строгое отклонение сырых `..` путей и безопасную проверку пустой новой папки.
- Synthetic Windows/Python 3.12 профиль preflight/updater/backup: **57 passed in 15.60s**.
- Code head `7c065b3a4ca6ef8211b3d149e5d998147cd3f925` прошёл exact-head Verify `40292624411`: Windows и Linux по **3,740 passed**, compile и Linux production Docker build/runtime smoke успешны. Повторная проверка двух исправлений не выявила новых actionable дефектов.
- В PR добавлена запись этих результатов и связанная тестовая карта. No merge/deploy/live bot operation performed.

Date: 2026-10-25. Status: `IMPLEMENTED_CI_GREEN_REPEAT_REVIEW_CLEAR; OWNER_VALIDATION_PENDING`.

## Confirmed findings and changes

1. **Ignored local file overwritten by fast-forward (P1).** Preflight now checks each existing incoming path with `git check-ignore`. If the target commit would claim an ignored local file, it returns `BOT_UPDATE_IGNORED_OVERWRITE_CONFLICT`; a failed ignore check blocks safely. Regressions create a synthetic Git target that tracks an ignored database and verify that local contents remain untouched, while a non-overlapping ignored database does not block.
2. **Bot can start during update (P1).** The updater now acquires the token-scoped startup/maintenance OS lock before its update checks and keeps it through backup, merge, dependency install/check and offline health check. Backup reuses the caller's exact held guard without closing it. The guard releases before the regular start script handoff and on all exits. A synthetic `BotInstanceLease` is refused during merge and accepted after release.
3. **Graceful stop can retarget a replacement process (P1).** Stop inspection can return the active generation only to its internal caller. The stop request captures that generation, verifies generation and checkout after every wait and immediately before opening the control socket, and checks the same generation while awaiting shutdown. Regressions replace a STARTING instance with a foreign generation/checkout and confirm no stop request is sent.
4. **SQLite backup can exceed the update deadline (P2).** The SQLite online-backup API now runs in `app/sqlite_backup_worker.py` with a parent-enforced deadline (default 30 seconds, configurable within 0.1–120 seconds). Timeout terminates the worker, maps to `BOT_BACKUP_SQLITE_TIMEOUT`, and removes the partial snapshot. The child receives only standard-library execution context and a minimal environment. A real synthetic exclusive lock verifies bounded exit; a valid database verifies snapshot integrity metadata.

## Files

- Runtime: `app/services/bot_update_preflight_service.py`, `app/services/bot_update_runtime_service.py`, `app/services/bot_instance_lifecycle_service.py`, `app/services/bot_backup_service.py`, new `app/sqlite_backup_worker.py`.
- Regression coverage: `tests/test_bot_update_preflight_service.py`, `tests/test_bot_update_runtime_service.py`, `tests/test_bot_instance_lifecycle_service.py`, `tests/test_bot_backup_service.py`.
- Documentation: `CHANGELOG.md`, `project_brain/CURRENT_STATE.md`, `project_brain/TEST_MAP.md`, `project_brain/DECISIONS.md`, new `project_brain/DECISIONS_060.md`.

## Verification

- Windows/Python 3.12 focused profile for preflight, updater, lifecycle and backup: **70 passed in 14.99s**.
- Windows/Python 3.12 linked bounded-soak, end-to-end restore and bot-control profile: **8 passed in 3.58s**.
- Full local `pytest` was not rerun because the project journal records that it can mutate shared root JSON and fail against Windows temporary-directory ACLs. The isolated focused profiles above passed, and full exact-head GitHub CI passed on both platforms.
- In-memory Python compilation of the 4 services, worker and 4 test modules passed; `git diff --check` passed. Commit `39d1a12bcb699ef504abbbb1c484a5a7745f23a7` passed Verify run `40222900262`: Windows **3,736 passed in 69.29s**, Linux **3,736 passed in 15.67s**, compile, production Docker build and runtime smoke all passed.
- No merge, deployment, production bot start/stop, network request, user-data backup or user-data restore was performed.

## Review status

Class: **Architecture Review Required**. Changes extend the lifecycle lock boundary and add a bounded subprocess for SQLite snapshotting. Repeat technical review of these four fixes found no further actionable defect. The PR still needs its normal independent approval; owner-side operational validation remains pending. No merge, deployment, production bot start/stop, network request, user-data backup or user-data restore was performed.

# Пакет независимого review: завершение существующих функций

Дата: 26.10.2026.
Целевая ветка: main.
Актуальная база сравнения PR: main SHA 89eb9224c3e9ec2126f58dc4d38794b33c2a2cc0. Историческая исходная точка Z00 — e879e6d7881a097f040e56d9962223525840917c; текущая база main включена в ветку merge-коммитом 15141441c6468018f9553405a7f31b6dd2da86a4.
Рабочая ветка: codex/existing-functionality-completion.
PR #718: https://github.com/dopf129-pixel/ai-business-assistant/pull/718. Текущий head SHA и ссылки на проверки следует сверять непосредственно в PR, поскольку docs/status commits обновляют ветку.

## Объём и архитектурная оценка

Изменения в 22 отслеживаемых файлах, примерно 1.8k строк добавлений; изменения runtime сосредоточены в пяти существующих сервисах. По правилам проекта архитектурное ревью требуется из-за размера diff и расширения сериализуемого cross-docking evidence. Классификация: небольшое расширение существующих контрактов, без нового service/layer/dependency и без схемной миграции.

Новые поля cross-docking evidence добавляются как optional; старые сохранённые планы остаются допустимыми. Отчётные формулы прибыли, налоговые правила и поведение Ozon API не менялись. Restore и lifecycle реализации не менялись: для них добавлена сквозная синтетическая проверка и уточнена инструкция первого безопасного обновления.

## Карта файлов и что проверить

### Доказательство кросс-докинга и сохранённый сценарий

- app/services/cross_docking_unit_rate_source.py — stable snapshot timestamp, независимая полнота finance/supply и signed accrual totals.
- app/services/planning_cross_docking_adapter.py и app/services/planning_workspace_repository.py — sanitization/validation optional evidence при save/restore, включая backward compatibility без новых полей.
- app/services/telegram_unit_price_calculator_runtime_service.py — текст для результата целевой цены, рекламного лимита и раскрытия evidence.
- app/services/telegram_unit_price_sensitivity_runtime_service.py — указание включённой/отсутствующей ставки в сценарной таблице.
- tests/test_cross_docking_unit_rate_source.py, tests/test_planning_cross_docking_adapter.py, tests/test_saved_planning_plan_telegram_flow.py, tests/test_unit_price_scenario_telegram_runtime.py, tests/test_telegram_unit_price_sensitivity_runtime_service.py — signed adjustments, checkpoint completeness, restored legacy plan, included/unavailable wording, same-source and saved-plan projections.

Проверить, что signed Ozon amounts остаются отдельной диагностикой; положительный плановый cost выводится как положительная сумма; incomplete evidence не превращается в ноль; продолжение checkpoint не меняет period/scope/as-of snapshot; старый plan v1 и payload без optional полей продолжают открываться.

### Backup и восстановление

- tests/test_daily_use_end_to_end_restore.py — synthetic end-to-end: план/revision, две effective-date себестоимости, tenant expenses и coverage, encrypted Ozon credential, restore в новый root и чтение после reopen.
- tests/test_bot_backup_service.py — форматы хранения, checksums, dry-run, restore target isolation, path/symlink и failure atomicity.
- tests/test_ozon_credential_production_persistence.py — действующие проверки шифрования/ключа.

Проверить, что архив содержит Client ID и ciphertext, но не plaintext API key, Telegram token или master key; корректный ключ восстанавливает credential, отсутствующий и неверный ключ возвращают явную unavailable/mismatch ошибку и не показывают подключённый магазин. Исходный storage остаётся неизменным.

### Первый безопасный update и operational lifecycle

- docs/daily-use-recovery-runbook.md — legacy checkout без updater, только fast-forward на чистой main, локальное сохранение diff/untracked вне checkout; запрещены destructive команды как копируемое решение.
- tests/test_windows_local_handoff_readiness.py — регрессия safety контракта.
- tests/test_bot_instance_lifecycle_service.py, tests/test_bot_update_runtime_service.py, tests/test_bot_update_preflight_service.py — synthetic checkout/process ownership and failure behavior.

Проверить, что stop таргетирует только правильный checkout/generation, updater подтверждает точный revision/readiness, startup/maintenance guard удерживается на полном окне, а controlled failure не делает скрытый restart/rollback.

## Локальная проверка

- Интеграционный профиль Z21: 198 passed in 7.73s.
- Полный Windows/Python 3.12 pytest на точном синхронизированном дереве: 3745 passed in 42.92s.
- python -m compileall -q app tests завершился с кодом 0; есть один существующий SyntaxWarning в tests/test_unit_economics_returns_impact_integrity_v971_v980.py:177.
- Профили Z17–Z19: 24, 33 и 82 passed соответственно.
- Live Telegram/Ozon и production bot не использовались.

## CI и независимое решение

PR #718 открыт; GitHub Verify workflow #40337702406 завершился успешно на code head df6b506e6febdf56915ec2eb4ca36f3e6ca57e20. Успешны Windows/Python 3.12, Linux/Python 3.11 и Docker build/runtime smoke; SHA-bound artifact: verification-0ec162a151f131c4cdaedd730e0aed94f758567e. Локальный полный pytest: 3745 passed; integrated profile: 198 passed; compileall exit 0. Самопроверка этого пакета не является независимым reviewer approval; независимое решение остаётся отдельным.

## Дополнительные замечания текущего review PR #718

Первый переход со старого checkout теперь использует `git fetch --no-tags origin main`, затем `git merge --ff-only --no-edit --no-overwrite-ignore FETCH_HEAD`. Synthetic regression исполняет команды из самого runbook и подтверждает, что конфликт с ignored локальными данными сохраняет файл и не двигает `main`.

Signed начисление кросс-докинга по SKU теперь проецируется из complete финансового evidence отдельно от расчёта ставки. При отсутствии подтверждённых поставок сумма остаётся видимой, а ставка за единицу остаётся неизвестной до появления знаменателя. Добавлена регрессия `NO_CROSSDOCK_SUPPLIES`.

Адресный профиль после исправлений: **35 passed in 15.43s**; полный Windows/Python 3.12 `pytest`: **3747 passed in 42.67s**; compileall и diff-check успешны. Эти локальные проверки выполнены до публикации обновлённого SHA. Предыдущие CI и review handoff относятся к старому SHA и не подтверждают новый head; после push обязателен exact-head CI, затем независимый reviewer должен повторно проверить обновлённый diff.

## Внешние проверки владельца остаются отдельно

Пошаговая безопасная инструкция и реестр E-01–E-03 приведены в разделе Z23 журнала `LUNA_EXISTING_FUNCTIONALITY_COMPLETION_PROGRESS_2026-10-26.md`.

ENGINEERING_READY не означает OWNER_ACCEPTED. Для завершения фактической проверки всё ещё нужны полный реальный 56-дневный источник cross-docking и рабочее наблюдение 24–72 часа. Полученные owner diagnostics и акт по одной позиции не доказывают реальный multi-SKU знаменатель. Не запрашивать API keys, .env, полную SQLite БД или несмаскированные логи.

PR не следует сливать или развёртывать до независимого review и зелёного CI; данная рабочая задача сама не выполняет merge/deployment.

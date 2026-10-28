# Unit-price persistence, privacy and restore — Q29

Дата: 27.10.2026. Статус: VERIFIED.

## Подтверждённый контракт

- Тарифные профили, сохранённые планы, наблюдения и неизменяемые версии результатов используют существующий `PlanningWorkspaceRepository` и общий `ozon_assistant.db`.
- Действующий `BotBackupService` архивирует эту SQLite-базу. Новый backup-механизм и новая таблица не нужны.
- Все записи проверяются owner/store scope. Версии observation result append-only и читаются по exact revision.
- Допустимые поля результата проходят строгую allowlist; неизвестное поле `raw_response` отклоняется до записи.
- Размеры профилей, наблюдений, результатов и сравнения, количество профилей, результатов и ревизий ограничены существующими quota constants.
- SQLite migrations additive. Существующие планы и результаты сохраняются при миграциях схем v2/v3/v4 в текущую v5.

## Проверка N13

Добавлен `tests/test_unit_price_backup_restore.py`. Он в изолированных временных каталогах создаёт синтетические owner/store, тариф с двумя ценовыми диапазонами, план, observation и два результата; выполняет backup, archive verification, dry-run, восстановление в новый root и повторное чтение после открытия новой repository instance.

Проверено:

- exact payload плана, тарифные диапазоны, store scope, `result_revision=2` и исторические revisions 1 и 2 совпадают после восстановления;
- восстановление в dry-run не создаёт target;
- другой store не может прочитать план, тариф или observation;
- result с `raw_response` отвергается, sentinel не попадает в SQLite;
- ранее существующие тесты v2/v3/v4 migration сохраняют планы и результаты и атомарно откатывают неудачную миграцию.

## Фактические проверки

Команда выполнена на Windows / Python 3.12 в тестовом окружении проекта; `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `PYTHONNOUSERSITE=1`, синтетические временные storage и basetemp, provider/credential env удалены.

- `tests/test_unit_price_backup_restore.py` и четыре адресные v2/v3/v4 migration регрессии: **5 passed in 0.95s**.
- В первом прогоне обнаружена ошибка только в fixture clock (строка вместо `datetime`), затем fixture исправлен. Следующий прогон прошёл.
- `git diff -- data` остаётся пустым; владелец Ozon, production storage, `.env`, live API и реальный бот не затрагивались.

## Ограничения

Это синтетическая проверка механизма архивации и восстановления, не резервная копия реальной пользовательской базы. Полный repository pytest и exact-head GitHub CI запланированы в Q33–Q35.

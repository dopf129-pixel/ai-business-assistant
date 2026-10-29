# W18 — точное повторное открытие замороженной экономики эксперимента

Дата: 29.10.2026  
Кодовый коммит: `731be723` — `Load exact frozen inputs for price experiments`.  
Кодовый этап: W18 (`W16`, `W17`) — DONE.  
Следующий этап: W19.

## Что изменено

- В `PlanningWorkspaceRepository` добавлен `get_price_experiment_frozen_snapshot`. Он возвращает сохранённый комплект без вызовов источников: точную ревизию плана с расчётной/стоимостной основой, content-addressed expense snapshot, точную ревизию тарифного профиля и точную ревизию quantity observation result, если они заданы.
- Каждый элемент читается через существующий tenant-scoped reader и сверяется с идентичностью эксперимента. Неизвестная ревизия, чужой scope, повреждённый hash или отсутствующий снимок закрывают чтение с явной ошибкой; неполный комплект наружу не возвращается.
- Размер возвращаемого комплекта ограничен суммой лимитов четырёх записей. `read_only=true` и `source_io=false` отражают, что метод только читает локальную базу Planning Workspace.
- После изменений плана/себестоимости, тарифа, observation result и расходного snapshot старый experiment восстановил прежние ревизии. Новый experiment можно создать с новыми exact refs; ранее сохранённый результат не переписывается. Поздняя correction добавляет следующую append-only result revision с новым snapshot reference.
- Сохранённый план schema 4 копируется с тем же extended scenario и повторно открывается без дополнительного source call.

## Проверки

- Связанный Windows/Python профиль: **79 passed in 5.77s** по `test_planning_workspace_unit_economics.py`, `test_planning_workspace_repository.py`, `test_planning_workspace_tariff_profiles.py`, `test_unit_price_observation_repository.py`, `test_saved_planning_plan_telegram_flow.py`.
- `py_compile` изменённых модулей: PASS.
- `git diff --check`: PASS; `git diff -- data`: пустой.
- Полный pytest не запускался на W18: он запланирован на W38–W39. Тесты использовали временное хранилище; реальные Ozon/Telegram API, bot и owner database не использовались.

## Архитектурная оценка

Минорное расширение существующего repository API; новое хранилище, таблица, service layer и источник не добавлялись. Существующие immutable revisions, tenant guards и сохранённые планы не меняются. Независимый review и exact-head CI остаются частью W38–W39.

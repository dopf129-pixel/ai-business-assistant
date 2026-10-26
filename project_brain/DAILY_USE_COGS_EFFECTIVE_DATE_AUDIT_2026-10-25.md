# B04 — даты действия себестоимости и Return COGS — 25.10.2026

## Подтверждённая ошибка и исправление

В `PeriodProfitFinanceSkuScopeService._recover_missing_product` после отсутствия подтверждённой записи `get_historical_cost_evidence(at_date, sku=...)` использовалась единственная текущая строка из `get_all_costs()`. Текущая строка не содержит `effective_from`; поле времени её изменения не доказывает, что эта себестоимость действовала в прошлом расчётном периоде.

Проблема была воспроизводима в двух существующих regressions:

- период `2026-08-31` получал текущую запись, изменённую `2026-09-01`;
- период `2026-09-01` получал запись `/costsku`, внесённую `2026-09-05`.

Владелец ранее подтвердил правило: «предлагать дату; всю историю применять только после отдельного подтверждения» (`project_brain/LUNA_DEVELOPMENT_TASK_2026-10-12.md`, ответ владельца). Автоматический fallback нарушал это правило и мог завышать COGS за прошлый период.

Исправление: периодный scope принимает для исторического SKU только подтверждённую date-scoped запись из `get_historical_cost_evidence`. При её отсутствии cost-inclusive расчёт остаётся fail-closed с `PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE`; текущие недатированные записи не читаются. Pre-COGS режим, точный SKU каталога и отдельное подтверждение применения ко всей истории сохраняются.

## Return COGS gates

Проверен read-only blocker resolver: recovery evidence должен быть полным и однозначным, затем отдельно проходят accounting attribution, recognition, profit-application authorization, explicit commit и final application. Только `SALEABLE_RESTORED` без этих стадий не меняет прибыль; `NON_SALEABLE` также требует подтверждённого состояния. Недостоверная/устаревшая цепочка не выставляется как применённая сумма. Учётный write consumer не добавлялся.

## Изменённые файлы

- `app/services/period_profit_finance_sku_scope_service.py`: удалена подстановка текущей себестоимости без даты действия.
- `tests/test_period_profit_historical_sku_cost_v1411_v1420.py`: уникальная текущая запись без effective-date evidence теперь ожидаемо блокирует прошлый период.
- `tests/test_period_profit_historical_sku_cost_input_v1421_v1430.py`: добавлен regression, что запись `/costsku` от 5 сентября не используется для расчёта за 1 сентября и текущая таблица для этого не читается.

## Проверки

- Профиль B04 — 18 модулей по исторической себестоимости, Return COGS gates, seller-cost flow, идентичности SKU и completeness view: **154 passed in 5.28s**; Windows Python 3.12, отдельный storage root.
- Подтверждённые исторические записи продолжают проходить; недатированная/последующая текущая запись не передаётся в SummaryService.
- Полный `pytest` не запускался. Часть файловых/SQLite Return COGS tests с `tmp_path` локально ограничена Windows ACL; точный CI должен выполнить полный набор перед PR readiness.
- `DECISIONS.md` не менялся: код применяет ранее зафиксированный выбор владельца, нового архитектурного решения нет.

Источники: выбор владельца — проектная задача от 12.10.2026; имена и критерии стадий — существующие реализации и regression tests. В B04 не использовались live Ozon API, Telegram или базы владельца.

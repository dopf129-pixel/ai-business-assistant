# W42 — повторное исправление review PR #722

Дата: 31.10.2026
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Исходный HEAD до исправлений: `da9aca88770713d02933d96734f65465033e9f20`
Статус: исправлено локально; commit/push, exact-head CI и независимое повторное review ожидают.

## Исправления

| ID | Подтверждённая проблема | Исправление |
|---|---|---|
| W42-R1 | Старую кнопку выбора цены можно было нажать после отметки об изменении рекламы. Runtime подставлял текущую experiment revision, а repository проверял только result revision и collection hashes. | Callback теперь содержит ожидаемую experiment revision и сразу становится stale после смены состояния. Для comparison-based KEEP/SELECT repository в одной транзакции сверяет phase-state revisions и контрольные event revisions обеих фаз, плюс текущие collection hashes. Прямой repository вызов также отклоняет устаревшее сравнение. STOP_WITHOUT_PRICE_CHANGE остаётся доступным после нового безопасного отображения результата. |
| W42-R2 | Readiness принимал одну успешную продажу при eligible sample 30, но сравнение требовало 30 успешных продаж. Фаза могла получить READY/FINISHED, а затем сравнение навсегда возвращало общее `PHASE_FINANCIAL_OR_UNIT_DATA_INCOMPLETE`. | Gate `SOLD_UNIT_DENOMINATOR` теперь требует `MIN_MATURITY_UNITS` успешных продаж; при меньшем числе, но подтверждённом ненулевом знаменателе результат `WAITING_FOR_DATA` без unit-profit. Завершение фазы блокируется. Comparison использует ту же константу вместо независимого числа 30. Причина `SOLD_SAMPLE_BELOW_MINIMUM` показывается пользователю. |

## Регрессии и проверки

- Telegram сквозная regression: после отображения сравнения применяется старый owner-decision callback, созданный до изменения контрольных условий; старый callback отклонён, новое сравнение показывает только безопасное завершение без смены цены.
- Repository regression: прямой SELECT после нового control event, с актуальной experiment revision и старым comparison, отклонён как `PLANNING_PRICE_EXPERIMENT_DECISION_COMPARISON_STALE`.
- Readiness regression: при eligible sample 30 и одной успешной продаже фаза остаётся `WAITING_FOR_DATA`, прибыль на единицу не публикуется, finish отклоняется.
- Все тесты unit-economics experiment и Telegram runtime: **117 passed in 7.15s**.
- Полный Windows `pytest`: **4,352 passed in 46.30s**.
- `python -m compileall -q app`: PASS; `git diff --check`: PASS.
- Полный тестовый прогон изменил демонстрационный `data/tasks.json` и создал `data/tasks.json.lock`; исходный JSON восстановлен, lock удалён. `data/` чистая.
- Реальные Ozon API и Telegram не вызывались; бот не запускался.

## Архитектурный эффект и следующий шаг

Minor extension существующих tenant/CAS guard contracts, без новой таблицы, миграции, слоя или внешнего запроса. Классификация по правилам проекта: **Architecture Review Required**, так как ужесточена атомарная запись решения в Planning Workspace.

Изменены `planning_workspace_repository.py`, Telegram experiment runtime, phase maturity/comparison/recommendation services и три связанных тестовых файла; обновлены `CHANGELOG.md`, `CURRENT_STATE.md`, `TEST_MAP.md`, журнал W42 и Decision 065. Следующее действие: проверить полный diff, создать commit, обновить PR #722 и получить exact-head CI; затем провести независимое review. Слияние, deploy и запуск бота не выполнялись.

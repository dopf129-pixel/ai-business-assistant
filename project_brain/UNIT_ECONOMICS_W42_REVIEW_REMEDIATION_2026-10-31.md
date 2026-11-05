# W42 — повторное исправление review PR #722

Дата: 31.10.2026
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Исходный HEAD до исправлений: `da9aca88770713d02933d96734f65465033e9f20`
Статус W42: опубликовано в PR #722 коммитом `d3577d510c0a92d6f198d0e5f1dc4e50c35739e5`; Windows и full-verification CI прошли на этом SHA (runs `41198178560`, `41198174172`). W43 follow-up см. ниже.

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

Изменены `planning_workspace_repository.py`, Telegram experiment runtime, phase maturity/comparison/recommendation services и три связанных тестовых файла; обновлены `CHANGELOG.md`, `CURRENT_STATE.md`, `TEST_MAP.md`, журнал W42 и Decision 065. Слияние, deploy и запуск бота не выполнялись.

## W43 — повторное открытие устаревшего сравнения

- Review подтвердил пробел в отображении: после контрольного события история результатов открывала прежнее сравнение, оставляла старую рекомендацию и показывала кнопки KEEP/SELECT. Repository отклонял выбор, но экран не объяснял почему.
- `_comparison_matches_latest_evidence` теперь также сверяет phase-state revisions обеих фаз и их последние event revisions с сохранённым сравнением. Чтение событий ограничено одной последней строкой; repository остаётся финальной атомарной проверкой решения.
- Устаревшее сравнение получает общее сообщение о смене данных или условий и не показывает кнопки выбора цены. Добавлена регрессия через публичные `phase_results` → `result` callbacks; ранее выданная кнопка остаётся устаревшей.
- Профиль экспериментов и Telegram: **117 passed in 7.28s**; полный Windows `pytest`: **4,352 passed in 43.81s**; `python -m compileall -q app` и `git diff --check` PASS.
- Полный прогон изменил `data/tasks.json`; файл восстановлен до исходного hash `38637702206478ab3c08d7ae1c4ac87f1f1c6354`, созданный `data/tasks.json.lock` удалён.
- Исправление опубликовано коммитом `48cc6709342e689b950dc0ba461b177963e7b4c9` в PR #722. Windows и full-verification CI прошли на exact head в [run 41200852297](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/41200852297). Есть только предупреждение Actions о переходе с Node.js 20.

# Основание большого пакета разработки — 17.10.2026

## Метод и исходная точка

Это аудит для постановки задач: чтение production composition, основных contracts/runtime и документации, проверка актуальных PR через GitHub. Он не заменяет независимый code review #697 и не объявляет новые функции реализованными.

Локальный HEAD: `3f7923ced48ba9434fdf5930d1f55431e0eacedd`, ветка `codex/luna-store-analytics-task-20261015`. Проверенный 17.10.2026 PR #697 открыт и не слит, head совпадает, base main `c55434327f50134324a5ca58e2f084854b809832`. Документированный прошлый CI: Verify `38756264065`, Windows/Linux 3 268 тестов, compileall и Docker smoke. Нового полного pytest для подготовки markdown-ТЗ не выполнялось.

Пользовательские `data/tasks.json` и `data/users.json` изменены локально; не читались как источник тестовых данных и не входят в подготовленные документы.

## Подтверждённое поведение и продуктовые пробелы

| Наблюдение | Код на проверенном SHA | Классификация и вывод |
|---|---|---|
| Есть finalized сравнение периодов, мост B/E, top-SKU вклад и scoped report views | `period_profit_comparison_contract.py`, `period_profit_comparison_bridge.py`, `period_profit_sku_contribution.py`, `assistant_period_profit_runtime_service.py` | VERIFIED_BEHAVIOR. Не заказывать повторно. Для новых выгрузок требуется учитывать, что snapshot хранит ограниченный top list |
| Есть одиночный transient калькулятор, target margin и 2–5 вариантов цены | `unit_price_scenario_service.py`, `unit_price_target_planning_service.py`, `telegram_unit_price_calculator_runtime_service.py` | VERIFIED_BEHAVIOR. NEW_FEATURE: партия разных SKU и чувствительность cost/ad/price, reuse существующей арифметики |
| `query_all()` обходит каждый элемент `load_products()` и возвращает общую ошибку после ошибки одного decision | `product_business_decision_query_service.py::query_all`, примерно строка381 | VERIFIED_BEHAVIOR, не отдельное доказательство аварии. Для нового обзора нужны bounded selection и частичный результат, без переписывания всех legacy callers |
| Публичные `query`/`query_all` декорируют decisions историей; `_with_decision_history` вызывает `record` | `product_business_decision_query_service.py::_with_decision_history`, примерно строка516 | VERIFIED_BEHAVIOR. Нельзя обозначить этот путь как новый read-only обзор, просто вызвав его. Нужен публичный query без history/proposal/task effects с reuse ядра |
| Есть сводка top5 и существующий paged список решений | `seller_attention_summary_service.py`, `assistant_keyboard_service.py::build_product_decisions_keyboard` | VERIFIED_BEHAVIOR. Новый обзор — выбранная группа/filters/coverage и переход к планированию; ещё один простой paged список не считается новой функцией |
| Source калькулятора создаёт новый trace в `_load_snapshot` | `unit_price_scenario_source.py::_load_snapshot`, примерно строка127 | VERIFIED_BEHAVIOR. В standalone это ограниченный source. Для multi-SKU нельзя возобновлять budget на каждом элементе; требуется наследование общего cap и ограничение ожиданий |
| Source требует явные logistics/last_mile/acquiring/advertising inputs | `unit_price_scenario_source.py::suggested_inputs`, `input_provenance` | VERIFIED_BEHAVIOR. Партия обязана показывать неполноту и давать редактор допущений, не заполнять эти поля нулями |
| Экспериментальный отчёт уже имеет expense partition, additive/reference семантику и summary/details | `experimental_store_economics_runtime_service.py::_build_expense_breakdown`, `_render`, `_render_details` | VERIFIED_BEHAVIOR. Не возвращаться к старому пункту «сделать разнесение с нуля» и не менять прибыль ради нового UI |
| Outgoing document sender ставит всем файлам caption про CSV себестоимости | `telegram_app_layer/telegram_api_bot.py::_send_result`, примерно строка137 | VERIFIED_BEHAVIOR, допустимо для текущего cost export. NEW_FEATURE integration prerequisite: явный document kind/caption перед новыми выгрузками |
| Cost import требует точный заголовок собственного CSV | `seller_cost_table_service.py::HEADER`, `import_csv` | VERIFIED_BEHAVIOR. Сохранить; новые report exports не должны походить на cost import |
| Trace хранит `events` списком, stack dump содержит внутренние идентификаторы/пути | `period_profit_operation_diagnostics.py::update`, `dump_worker_stack` | VERIFIED_BEHAVIOR. Это не готовый shareable JSON. NEW_FEATURE: bounded whitelist summary и отдельная обезличенная выгрузка |
| Текст уже дробится по UTF-16 лимиту | `telegram_progress_feedback.py::split_telegram_text`, `finish_progress` | VERIFIED_BEHAVIOR. Не реализовывать chunking заново; новые views тестировать в существующем sender |

Ни одной неподтверждённой production-ошибке не присвоен P1/P2. Технические prerequisite изменения принимаются собственными regression tests при реализации.

## Приоритеты

1. A — основание: review используемых границ, общий budget и scoped transient snapshots.
2. B — выбранная группа товаров с фильтрами, неполнотой и безопасными переходами.
3. C — новый пакетный план цен разных SKU с локальными допущениями и target check.
4. D — новая чувствительность к трём параметрам, включая матрицу двух осей.
5. E — полезные CSV/JSON по существующим и новым снимкам, корректный file contract.
6. F — диагностика через бота и версия процесса для самостоятельной проверки владельцем.
7. G — сквозная приёмка и review handoff нескольких небольших PR.

Пакет не вводит платные источники, прогноз спроса, автоматические изменения Ozon или persistent saved scenarios. Новые возможности работают поверх уже имеющихся read-only источников и pure calculations.

## Артефакт и статус

Исполняемое ТЗ: `LUNA_LONG_RUN_PRODUCT_TASK_2026-10-17.md` — 7 крупных модулей, 32 этапа, зависимости, числовые примеры, лимиты, проверки и протокол восстановления после compaction. Подготовка не запускает реализацию. Новый пакет A–G имеет статус NOT_STARTED.

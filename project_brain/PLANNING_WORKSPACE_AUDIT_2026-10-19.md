# Основание программы planning workspace H–O

Дата: 19.10.2026. Тип: ограниченный аудит для постановки задач, **не полный code/security review**.

## Подтверждённая база

Локальный `main` = `722f368526c278b701cbfd69f3dbb9a474d52386`.
Повторно прочитаны metadata [PR #702](https://github.com/dopf129-pixel/ai-business-assistant/pull/702): merged=true, merge_commit_sha совпадает с локальным HEAD; совокупный reviewed head — `fcb53683bbdc3d48ab14b1f8fa2f428d9f5719fd`.
Jobs [merged-main Verify 39165543772](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/39165543772) completed/success: Windows, Linux pytest/compileall, production Docker build/runtime smoke. Baseline прошлого исполнения — 3 425 passed на каждой платформе; в этой подготовке прочитаны статусы jobs, новый pytest не выполнялся.

Прочитаны CURRENT_STATE, DECISIONS, TEST_MAP, ROADMAP, README/guide, предыдущее ТЗ A–G и handoff, production entrypoint/start script, calculator/batch/source/tax, tenant storage/SQLite repository, report snapshot и export contracts. Локальные seller JSON использованы только для фиксации hashes, не как тестовые fixtures.

## Наблюдения и выбранные продуктовые продолжения

| Подтверждённое наблюдение | Источник в коде | Вывод для ТЗ |
|---|---|---|
| Есть обзор, single/batch, target, sensitivity, export и support diagnostics | `app/services/product_overview_service.py`, `unit_price_batch_plan_service.py`, `unit_price_sensitivity_service.py`, `analytics_export_service.py` и runtimes | Реализованный baseline. Не заказывать повторно A–G |
| Scenario state transient; соответствующее решение явно требует изоляции допущений от фактов | DECISIONS: Price Planning Scenario Isolation; calculator/batch runtimes | NEW_FEATURE: отдельные saved planning documents; перед реализацией аддитивный ADR, сохранение не превращает recipe в факт |
| Calculator выдаёт компоненты, tax и profit одной успешной продажи | `app/services/unit_price_scenario_service.py` | NEW_FEATURE: рекламные пределы через этот же forward calculation; не копировать формулы/не менять налог |
| Batch scope — ограниченные exact SKU, результат на единицу, без Q/общего налога группы | `app/services/unit_price_batch_plan_service.py` | NEW_FEATURE: manual successful-sales mix, weighted totals и один aggregate TaxService |
| TaxService имеет income, income-minus-expenses, minimum tax и NONE | `app/services/tax_service.py` | Подтверждённая семантика. Сумма per-unit taxes не заменяет налог группы во всех режимах |
| Finalized analytics snapshot owner/store/TTL-bound; SKU contribution ограничен top lists | `assistant_period_profit_runtime_service.py::get_analytics_snapshot_for_export`, `_save_completeness_view`; export service | NEW_FEATURE: plan/fact adapter с проверкой basis/coverage. Top list не полный factual set |
| Уже есть tenant path resolver и SQLite repositories | `app/services/tenant_storage.py`, `expense_repository.py` | Новые изолированные planning tables; без нового storage framework/переноса business records |
| Main просто строит application и вызывает run_polling; start script не содержит status/stop/single-instance контракта | `app/telegram_app_layer/telegram_api_bot.py::main`, `start_bot.ps1` | NEW_FEATURE: безопасное управление своим процессом. Отсутствие удобного lifecycle не объявлено воспроизведённым P1/P2 |
| Main уже слит, но docs наверху ещё сообщают «PR открыт/не слит» | CURRENT_STATE/ROADMAP/старые handoff и GitHub metadata | CONFIRMED_DOC_DRIFT: актуальный указатель и H00 reconciliation без удаления истории |

Новые production defects этим аудитом не объявлены подтверждёнными. Исправлять существующие проблемы в ходе исполнения только после воспроизведения/доказательства и с ограниченным regression scope.

## Почему этот пакет

Нынешний пользователь может рассчитать и выгрузить временный сценарий, но следующий цельный продуктовый цикл — сохранить вариант, задать свой объём, проверить допустимую рекламу и сопоставить план с фактом. Эти функции используют имеющиеся источники и не требуют платной аналитики, записи в Ozon, прогноза спроса или распределения неизвестных account costs.

Приоритет: H baseline/lifecycle → I durable planning → J ad headroom и K sales mix → L factual comparison → M guided completeness → N comparison/export → O acceptance. Восемь модулей, 36 конкретных этапов, числовые контроли, concurrency/persistence/ownership tests и протокол восстановления после compaction.

## Проверенные примеры и ограничения

Прямые fake-only вызовы действующих UnitPriceScenarioService/TaxService подтвердили числа ТЗ: profit 141 ₽ при P=500/ad=10%; target 25% на ad=13,20%, отказ на 13,21%; breakeven на 38,20%, убыток на 38,21%; второй SKU profit before tax 230 ₽, tax 48 ₽; aggregate income tax 480 ₽ и aggregate income-minus-expenses tax 15 ₽ в соответствующих примерах.

Будущие API/repository/UI не реализованы и не проверены этими вызовами. Полный pytest для docs-only работы не запускался. Для H–O необходимы новые meaningful regressions, clean Windows/Linux CI и независимый architecture review. Merge/deploy не разрешены этим ТЗ.

Документальная проверка подготовки: 36 уникальных этапов в правильной последовательности; явные ссылки `app/...py` существуют; markdown fences парные; whitespace/diff checks успешны. Пользовательские JSON совпали по SHA256 до и после подготовки. Ветка подготовки осталась `main`; commit/PR подготовки не создавались.

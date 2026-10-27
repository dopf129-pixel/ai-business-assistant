# Telegram lifecycle наблюдения цены (Q20)

Дата: 27.10.2026
Статус: VERIFIED
Классификация: Architecture Review Required

## Изменение

Production flow позволяет начать наблюдение из сохранённого FBO-плана: для batch-плана выбирается конкретная строка товара, владелец вводит цену продавца и timezone-aware дату/время уже выполненной установки, просматривает подтверждение и явно создаёт запись. Ни один route не меняет цену или настройки Ozon.

Карточка наблюдения позволяет запросить период, прочитать ограниченный evidence collector Q17, нормализовать данные Q18, оценить их Q19 evaluator, сохранить результат append-only revision, открыть историю/детали, оставить или очистить заметку и завершить наблюдение. Доступ к данным и callbacks привязан к owner/store/tenant и конкретной ревизии плана/результата. Для SKU без сопоставимых источников Telegram честно показывает неполноту; модельная прибыль подписывается как модель и не называется фактической.

Перед обращением к collector проверяются ровно две ISO даты, 3–56 дней, завершённость локального окна и начало не раньше даты установки цены. При ошибке пользователь остаётся на вводе дат; collector не вызывается. В collector остаётся независимая защитная проверка тех же temporal constraints.

## Проверки

- `tests/test_telegram_unit_price_observation_runtime.py` — 7 тестов: создание/повторное открытие, incomplete result и append-only history, отказ stale callback, заметка/завершение, FBO + tenant scope, ввод цены/времени/окон, route сохранённого плана и выбор SKU из batch.
- `tests/test_period_profit_analytics_runtime.py::test_production_factory_routes_period_analytics_without_requery` — production composition.
- Изолированная команда: `python -m pytest -q --basetemp <новая TEMP-папка> tests/test_telegram_unit_price_observation_runtime.py tests/test_period_profit_analytics_runtime.py::test_production_factory_routes_period_analytics_without_requery`.
- Фактический адресный результат после добавления проверки невалидных/незавершённых окон: **8 passed in 1.34s** на Windows/Python 3.12.
- Linked Q16–Q20 profile по 14 модулям/целям: **197 passed in 4.70s**. Python AST parse затронутых 7 файлов прошёл; `git diff --check` прошёл с ожидаемыми предупреждениями о LF→CRLF для Markdown. `git diff -- data` пуст.
- Тестовый collector синтетический. Проверки использовали отдельные TEMP storage/basetemp и отключённые dotenv/plugin autoload; environment names credential/provider были удалены без вывода значений. Owner data, `.env`, live API/network, owner database и бот не использовались.

## Границы и продолжение

Не подтверждены история per-sale цены, все успешно проданные единицы, полная совместимая реклама/дата её атрибуции и фактическая прибыль на единицу. Эти отсутствующие данные остаются unknown/incomplete и не заполняются предположениями. Реальный API, `.env`, owner database, tracked data и запущенный бот не использовались.

Следующий этап Q21 проверит quality/comparability gates: периоды, цены, количества, revenue/DRR basis, тариф/налог/расходы, overlap, полноту, свежесть и confounders; неподтверждённые данные не смогут получить verified label.

# W30 — guided Telegram entry для экономики SKU

Дата: 29.10.2026  
Статус: DONE  
Зависимости: W10, W18. Следующий этап: W31.

## Изменение

- Меню юнит-экономики объясняет базовый режим: он отображает доступные текущие или исторические данные, неизвестные расходы помечаются отдельно и не считаются нулевыми.
- Плановый режим отдельно обозначен как сценарий «что если»: можно менять цену и допущения; сценарий не отправляет изменение цены в Ozon.
- В SKU-detail при подключённом калькуляторе поясняется граница базовой оценки и действие перехода в плановый сценарий. Список `missing_fields` остаётся источником текста основного отчёта; расширенная модель не переписывает фактический расчёт.
- Подписи кнопок согласованы: «Плановая экономика» в списке и «Планировать цену» из карточки SKU.
- Подтверждение ручного тарифа проходит через текущий public Telegram adapter и возвращает результат того же `scenario_id`, SKU, цены и себестоимости. Подтверждённая ставка помечается как пользовательское допущение.
- Когда плановый runtime отключён, базовое меню не предлагает недоступный маршрут.

## Файлы

- `app/services/assistant_button_handler_service.py` — guided scope/missing-data copy и точка входа из текущего отчёта SKU.
- `app/services/assistant_keyboard_service.py` — понятная подпись планового режима.
- `app/services/telegram_unit_price_calculator_runtime_service.py` — согласованная подпись кнопки в SKU-detail.
- `tests/test_product_unit_economics_telegram_ui.py`, `tests/test_unit_price_scenario_telegram_runtime.py`, `tests/test_telegram_unit_price_tariff_profile_runtime.py`, `tests/test_financial_telegram_query_exception_containment_v1081_v1090.py` — регрессии UI, public callbacks, ручного тарифа и обработки ошибок.

## Проверки

Изолированный Windows/Python прогон связанных UI/calculator/tariff/exception suites:

```text
69 passed in 2.11s
```

Тесты использовали отдельный временный `AI_ASSISTANT_DATA_DIR`; dotenv отключён. Ozon API, Telegram API, реальный бот, owner database и существующая `data/` не использовались.

`py_compile`: PASS.  
`git diff --check`: PASS.  
`git diff -- data`: пусто.

## Архитектурная оценка

**Minor architectural extension.** Изменены только существующие Telegram text/keyboard routes и регрессии. Новые сервисы, хранилища, внешние источники, зависимости и расчётные контракты не вводились. Базовая фактическая экономика и сценарный калькулятор остаются раздельными.

## Ограничения

W30 создаёт понятную навигацию, но не начинает experiment/phase workflow; его public wizard реализуется в W31. Источник-specific заполнение W10 readiness metadata также не заявляется этим UI этапом. Полный pytest и CI выполняются на W38–W39.

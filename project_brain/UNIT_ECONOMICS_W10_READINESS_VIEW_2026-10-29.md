# W10 — публичная проекция полноты и применимости

Дата: 29.10.2026
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Предыдущий commit: `0348ecb7` (W09)
Статус: DONE для чистой read-only projection; Telegram navigation and provider-specific evidence adapters не подключены.

## Реализация

Добавлен `UnitEconomicsReadinessViewService`, который принимает W09 snapshot и небольшой allowlisted metadata map. Для каждого компонента он показывает статус `INCLUDED`, `EXCLUDED` или `UNKNOWN`, подтверждённый источник, applicability, наблюдаемую сумму/единицы, сумму/единицы, реально применённые к оконной ставке, саму ставку и ограниченные машинные причины.

Суммы и количества берутся только из snapshot; metadata не может подменить их. Источник и applicability принимаются как фиксированные коды; reason codes генерируются только из проверенных snapshot статусов. Свободный текст и сырые API данные не отражаются. Без source/applicability metadata компонент остаётся `UNKNOWN`. При полной доказанной coverage нулевая сумма выводится как `INCLUDED` с `0.00 ₽`, а не превращается в unknown. Подтверждённая сумма при нулевом знаменателе остаётся видна как наблюдаемая, но per-unit rate и применённая сумма остаются неизвестными. Частичный/неполный snapshot никогда не даёт включённую компоненту.

Reference и phase проецируются независимо. Окна не объединяются, а пересекающиеся окна переводят eligibility comparison в `INCOMPARABLE` с причиной `WINDOWS_OVERLAP`. Проекция проверяет exact schema/scope/date bounds, identity consistency пары, coverage, component amounts/units и rate arithmetic, но не возвращает identity. Функция чистая, не делает HTTP/API вызовов и не пишет в repository; output явно содержит `read_only=true` и `api_calls=0`.

## Регрессии и фактические проверки

Добавлен `tests/test_unit_economics_readiness_view_service.py` (15 тестов): confirmed zero vs missing metadata, полный положительный компонент и source, excluded reconciliation-only сумма, partial evidence, zero denominator, source/applicability allowlists and generated reason codes и отказ свободному тексту, отсутствие SKU/owner ID, отдельная reference/phase пара, overlap gate и invalid snapshot.

Объединённый изолированный Windows профиль W05–W10:

```text
tests/test_unit_economics_readiness_view_service.py
tests/test_unit_economics_window_snapshot_service.py
tests/test_unit_economics_additional_expense_evidence_service.py
tests/test_unit_economics_return_evidence_service.py
tests/test_unit_economics_advertising_evidence_service.py
tests/test_unit_economics_expense_normalizer.py
tests/test_unit_price_observation_normalizer.py
tests/test_period_profit_operation_diagnostics.py
131 passed in 2.00s
```

`py_compile`, `git diff --check` и line-length scan прошли; `git diff -- data` пустой. В локальной `.venv` отсутствует объявленный в проекте `tzdata`, поэтому адресные тесты выполнены pytest из проектной среды с уже установленной комплектной tzdata через `PYTHONPATH`; зависимости или пользовательское окружение не изменялись. Ozon/Telegram credentials оставались пустыми, dotenv отключён, тестовое хранилище и pytest base временные. Реальные API, пользовательская база и бот не запускались.

## Ограничения и следующий этап

W10 формирует безопасную публичную проекцию, но ещё не подключает её к Telegram экрану и не создаёт source metadata из API adapters. При отсутствии или несоответствии metadata отчёт намеренно покажет `UNKNOWN`. W11 должен аддитивно расширить canonical forward калькулятор, сохранив legacy behavior и добавив полный расчётный parity.

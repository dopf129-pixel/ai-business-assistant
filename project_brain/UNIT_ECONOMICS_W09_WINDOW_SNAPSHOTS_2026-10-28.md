# W09 — 56-дневный reference и отдельное окно фазы

Дата: 29.10.2026
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Входной code HEAD: `fb78bfa8`
Статус: DONE для bounded orchestration и pure snapshot assembly; конкретные Ozon source adapters и canonical calculator остаются последующими этапами.

## Реализация

Добавлен `UnitEconomicsWindowSnapshotService`. `reference_window` строит ровно 56 полностью завершённых локальных календарных дней до заданной `as_of_local_date` в явной IANA-зоне. `phase_window` принимает отдельный интервал из 1–28 завершённых локальных дней; текущая незакрытая дата и невалидная зона отвергаются. `build_pair` сохраняет reference и phase как независимые snapshots и никогда не объединяет их числитель или знаменатель.

`build_snapshot` принимает ограниченные нормализованные сегменты одного точного SKU/store/schema. Сегменты внутри окна не пересекаются; для полноценного результата они покрывают каждый запрошенный день, все страницы/компоненты завершены, а количества имеют один совместимый вид знаменателя. Основная ставка — сумма подтверждённых расходов / сумма единиц по непересекающимся сегментам, с Decimal и округлением до копейки. Нулевые единицы сохраняют подтверждённую сумму и полноту, но ставка остаётся `None` со статусом `ZERO_DENOMINATOR`. Только непрерывный полностью собранный суффикс истории получает `SHORT_HISTORY`; его observed rate показывается отдельно, полная 56-дневная ставка не публикуется. Сохраняются requested bounds, observed bounds и безопасные coverage details каждого сегмента. Пропуски, неполные страницы, смешанные знаменатели, supplied units кросс-докинга, конфликт идентичности и отрицательный credit не становятся применимой ставкой.

`collect_sources` запускает только переданные normalized-evidence readers последовательно под единым дочерним `PeriodProfitOperationTrace` с верхним ограничением 120 секунд и 128 HTTP-попыток на всю user operation. Если parent уже использовал попытки, дочерний trace получает лишь остаток; local и total counters раздельны, parent не сбрасывается. Отказ бюджета, 429 или сбой останавливает текущий проход; недостающие readers отмечаются как не начатые. Другой явный неполный результат также не выдаёт общий сбор за complete. Автоматических повторов нет. Reader обязан нормализовать ответ заранее; bounded JSON проверка с denylist блокирует частые raw-response, credential и operation-ID containers/keys, но не является универсальным API scrubber. Конкретные Ozon collectors не подключены этим этапом; реальные API не вызывались.

## Регрессии и фактические проверки

Добавлен `tests/test_unit_economics_window_snapshot_service.py` (16 тестов): N08 weighted 200/110 = 1.82 вместо среднего дневных rates; 56 завершённых дат и зона; отдельно фаза; короткая история; 0 единиц; несовместимые и кросс-докинговый знаменатели; gap/429; overlap/identity/credit; полный user-operation request budget без сброса parent; остановка после 429 и time budget; неполный source не complete; duplicate source key; отказ на raw-response container; суммарный лимит evidence 64 KiB. Полная пара сообщает collection completeness отдельно от `comparison_eligibility`.

Изолированный Windows/Python connected profile, credentials пустые, dotenv отключён, storage и pytest временные:

```text
tests/test_unit_economics_window_snapshot_service.py
tests/test_unit_economics_additional_expense_evidence_service.py
tests/test_unit_economics_return_evidence_service.py
tests/test_unit_economics_advertising_evidence_service.py
tests/test_unit_economics_expense_normalizer.py
tests/test_unit_price_observation_normalizer.py
tests/test_period_profit_operation_diagnostics.py
116 passed in 1.80s
```

Windows / Python 3.12.10; dotenv disabled, Ozon/Telegram credentials empty, isolated temporary storage and pytest base. `py_compile`, `git diff --check` passed; `git diff -- data` is empty. Владельческие данные, `.env`, база данных, Ozon, Telegram и реальный бот не использовались.

## Границы и следующий этап

W09 готовит shared bounded collection и immutable-by-contract in-memory snapshot assembly, но не утверждает, что Ozon API сейчас предоставляет все необходимые exact-SKU источники. Отсутствующие отмены/возвраты/продажи и неподтверждённое SKU-хранение остаются unknown/unavailable. W10 добавит read-only projection полноты и применимости без дополнительных API вызовов при навигации.

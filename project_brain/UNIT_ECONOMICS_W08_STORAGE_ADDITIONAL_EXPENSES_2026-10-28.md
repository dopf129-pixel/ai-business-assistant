# W08 — хранение, размещение и дополнительные услуги

Дата: 28.10.2026
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Входной code HEAD: `c59ab11a`
Статус: DONE для pure evidence resolver; collector, storage API adapter, persistence и canonical calculator не входят в этап.

## Реализация

Добавлен `UnitEconomicsAdditionalExpenseEvidenceService`, который принимает только нормализованный `SELLER_FINANCE` snapshot W05 и раскладывает расходы по взаимоисключающим evidence buckets. Стабильные ключи `FINANCE_PAID_STORAGE`, `FINANCE_PLACEMENT` и `FINANCE_CROSS_DOCKING` требуют соответствующих нормализованных категорий. Произвольный `OTHER_SERVICE` допускается только через immutable authorized component mapping с уникальным source key на строку и проверяемым content hash. Тот же ключ нельзя переопределить в другом bucket; несовпадение key/category становится conflict.

Результат не вычисляет ставку за единицу: он возвращает source numerator и раздельные ownership totals, сохраняя `unit_amount_rub`, `denominator_units` и `denominator_kind` пустыми до W09. Для хранения остаются разные состояния exact SKU recurring и `WINDOW_ALLOCATION` candidate. Периодный вариант нельзя молча поделить на продажи: нужен будущий явный model и совместимый denominator.

Компоненты `BASE_ALREADY_INCLUDED` остаются только в base ledger; `RECONCILIATION_ONLY` не применяются; account/unattributed суммы не делятся на заказы или выручку. Только recurring amount с точной SKU атрибуцией и проверенным origin является exact SKU candidate. Window allocation показывается отдельно и не включается в exact candidate. `ONE_OFF` сохраняется как исторический amount, но не создает recurring rate; net credit сохраняет отрицательный знак и требует отдельной проверки, а отрицательный recurring credit блокирует кандидата.

`CONFIRMED_ZERO` отличается от `MISSING` и `PARTIAL`; отсутствующий storage/placement не выдаётся как ноль. Даже при успешном resolver `full_cost_coverage_confirmed=false`: W08 не утверждает, что все услуги магазина охвачены или что есть подходящий источник для любого SKU. Финансовый cross-docking bucket только делегирует сумму уже существующей `CrossDockingUnitRateSource` и не добавляет её к новой сумме второй раз.

Изменений существующих отчётов, их прибыли/налога, `TaxService`, существующего cross-docking источника, Ozon clients, repository/schema и Telegram flow нет. Реальные storage/SKU данные не получены; API source audit W02 оставляет SKU storage attribution неподтверждённой. Resolver не делает I/O и не меняет бизнес-данные.

## Regression coverage и проверки

Добавлен `tests/test_unit_economics_additional_expense_evidence_service.py` (12 regression functions): N07 exact SKU amount, confirmed zero vs missing, base overlap, account-level storage, explicit window candidate without division, N04 one-off net credit, authorized/hashed OTHER_SERVICE mapping, unmapped service, cross-docking delegation, partial source, mapping tampering, key/category conflict.

Изолированный Windows/Python 3.12.10 connected profile с synthetic storage, без dotenv, credentials, Ozon requests, Telegram и production data:

```text
tests/test_unit_economics_additional_expense_evidence_service.py
tests/test_unit_economics_return_evidence_service.py
tests/test_unit_economics_advertising_evidence_service.py
tests/test_unit_economics_expense_normalizer.py
tests/test_unit_price_observation_normalizer.py
89 passed in 1.23s
```

`py_compile` — PASS; `git diff --check` — PASS; `git diff -- data` — пусто; строки длиннее 120 символов не обнаружены. Пользовательские базы, `.env`, credentials, Ozon и бот не использовались.

## Границы и следующий этап

W08 реализует нормализацию и категорийный resolver, а не получает SKU storage из Ozon: публичный audit пока не подтверждает источник хранения с полным SKU mapping. W09 должен собирать bounded reference/phase snapshots, использовать weighted numerator/denominator только с доказанным scope и coverage, уважать общий request/time budget и не выдавать missing storage за ноль. При отсутствии точного источника результат должен оставаться unavailable/partial.

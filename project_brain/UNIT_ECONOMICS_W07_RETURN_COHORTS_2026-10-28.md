# W07 — возвратные расходы, retained cohort и состояние товара

Дата: 28.10.2026
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Входной code HEAD: `db5bb230`
Статус: DONE для pure resolver; source adapters и получение реальных данных не входят в этап.

## Реализация

Добавлен `UnitEconomicsReturnEvidenceService` — pure resolver поверх нормализованных финансовых компонентов, точной связи количеств и отдельного evidence о физическом состоянии возвращённого товара. Существующие отчёты, `TaxService`, запись себестоимости и источники Ozon не менялись.

Комиссии возврата и невыкупа обрабатываются только по двум явным component keys `FINANCE_CUSTOMER_RETURN_FEES` и `FINANCE_CUSTOMER_NONBUYOUT_FEES`. Суммы posting целиком, средние начисления и количество строк отчёта не используются как расходы или знаменатель. Два обязательных типа имеют независимые состояния `PRESENT`, `CONFIRMED_ZERO`, `MISSING`, `PARTIAL` и `CONFLICT`; отсутствующий компонент не становится нулём.

Строгая когорта требует точного owner/store/product/offer/SKU/sale-schema, полностью прочитанных posting/return источников, точного join доставленных единиц с возвратами именно из этих доставок и совпадающего непрозрачного `cohort_ref`. Нормализатор W05 получил обратно совместимое optional-поле: 64 lowercase hex символа; оно проходит в ограниченный snapshot и учитывается fingerprint. Его создаёт только будущий адаптер после доказанного transient join; это случайный токен одной in-memory collection, а не хэш/кодировка provider IDs. Без источника exact join токен не создаётся и strict расчёт закрыт.

Знаменатель — `delivered_units - confirmed_returned_units_from_deliveries`; `posting_count` и `api_row_count` не принимаются. Ноль/отрицательный retained denominator, `returned > delivered`, несовпадающее retained count, разные когорты, incomplete coverage и неподтверждённая атрибуция не дают strict RUB/unit. Различные source windows допускаются только когда adapter доказал связь и выставил один токен; само совпадение дат не является доказательством.

Inventory evidence отделено от возвратных логистических сборов. `SALEABLE_RESTORED` не списывает себестоимость; `IRRECOVERABLE_CONFIRMED` добавляет COGS только один раз и только с подтверждённым ownership; `PENDING`/`UNKNOWN` сохраняет неизвестность и блокирует итог. Компенсация вычитается только с явно подтверждённым `NON_OVERLAPPING`; `ALREADY_INCLUDED` не вычитается повторно, `NONE_CONFIRMED` допускает только ноль. Несовпадение количества диспозиций с возвращёнными единицами блокирует strict режим. Компенсационные/возвратные кредиты, превышающие потери, переходят в review/incomplete, а не создают отрицательную ставку.

Итог N02: возвратные сборы 200 + невыкуп 100 + подтверждённый дополнительный COGS 60 − непересекающаяся компенсация 10 = loss pool 350; при 100 retained единицах ставка 3,50 ₽/шт. Восстановленный товар, ожидающее решение и gross refund выручки не добавляют COGS.

## Regression coverage и проверки

Добавлен `tests/test_unit_economics_return_evidence_service.py` (22 тест-функции, часть параметризована) для N02/N06, partial-vs-zero, account/window allocations, corrections/credits, exact cohort binding, unit mismatch, pending/recovered/irrecoverable inventory, компенсации и отсутствия сырого маркера в публичном resolver result. В тестах W07 snapshot теперь проходит через реальный W05 normalizer с cohort_ref во входном evidence.

Расширен `tests/test_unit_economics_expense_normalizer.py`: optional cohort ref allowlisting/fingerprinting и отказ malformed значениям без эха входа.

Изолированный Windows/Python 3.12.10 profile на синтетическом storage, без dotenv, credentials, Ozon API, Telegram и production data:

```text
tests/test_unit_economics_return_evidence_service.py
tests/test_unit_economics_expense_normalizer.py
tests/test_unit_economics_advertising_evidence_service.py
tests/test_unit_price_observation_normalizer.py
tests/test_returns_buyout_facts_source.py
tests/test_returns_finance_attribution_facts_source.py
tests/test_returns_finance_attribution_analytics_service.py
tests/test_return_cogs_accounting_attribution_evidence_v1311_v1320.py
115 passed in 1.89s
```

Ранние прогоны выявили ошибки только в новых тестах: assertion пустой строки/int-сравнение, затем пропущенный импорт pytest; после исправлений финальный запуск прошёл. В рабочем каталоге не читались/менялись `data/`, `.env`, owner DB; live Ozon/бот не запускались. `py_compile`, `git diff --check` и проверка отсутствия diff в `data/` также PASS.

## Границы и дальнейшая работа

Это вычислительный контракт, а не подключение seller endpoints: пока нет adapter, который доказывает posting↔delivery↔return↔SKU связь и создаёт cohort token. Поэтому результаты тестовых fixtures не подтверждают доступность exact cohort в реальном аккаунте. W08 добавит resolver storage/placement и раздельное ownership дополнительных услуг; W09 сможет собирать только фактически доступные evidence и должен оставлять unsupported/unavailable источники неизвестными.

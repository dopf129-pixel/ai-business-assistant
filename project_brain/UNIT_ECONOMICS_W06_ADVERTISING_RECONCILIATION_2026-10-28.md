# W06 — расходы на рекламу и сверка Performance CPC

Дата: 28.10.2026
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Входной code HEAD: `ebe40128` (после W05)
Статус: DONE для pure evidence resolution; Ozon adapters и применение в расчёте цены остаются на последующих этапах.

## Реализация

Добавлен `UnitEconomicsAdvertisingEvidenceService`. Это чистый resolver поверх уже нормализованных `ExpenseSnapshotV1`-совместимых данных. Он не вызывает Ozon/Performance API, не читает credentials, не хранит данные и не меняет существующие отчёты.

- Финансовые ключи `FINANCE_ADVERTISING_CPC`, `FINANCE_ADVERTISING_CPO` и `FINANCE_ADVERTISING_OTHER` — основной источник рекламных сумм. `ADVERTISING_OTHER` добавлен в allowlist нормализатора и контракт W03. Расширенные ключи для account-level/точного SKU `FINANCE_ADVERTISING_OTHER_ACCOUNT` и `FINANCE_ADVERTISING_OTHER_SKU` имеют явную mapping; неизвестный рекламный ключ не угадывается по названию.
- Любой неизвестный тип, несоответствие component key/category, конфликт, неполная страница, неизвестная сумма или неподтверждённое происхождение блокирует полный SKU-итог. Отсутствующий вид рекламы остаётся `MISSING`; ноль считается подтверждённым только при полном snapshot с явным expected key и complete coverage.
- Расходы `UNATTRIBUTED` показаны отдельной account-level суммой и счётчиком компонента. Даже если начисление и коррекция взаимно погасились до 0 ₽, строка остаётся account-level и не распределяется на SKU. `WINDOW_ALLOCATION` сохраняется отдельно и не включается в точный SKU-итог.
- К Exact SKU/Cohort сумма относится в дополнительный сценарий только с `ADDITIONAL` ownership и подтверждённым `OFFICIAL_SOURCE`/`DETERMINISTIC_DERIVATION` origin. `BASE_ALREADY_INCLUDED` и `RECONCILIATION_ONLY` отображаются отдельными ownership-суммами и не прибавляются.
- Performance CPC допустим только как отдельная reconciliation-сумма с `RECONCILIATION_ONLY`, точной SKU identity, типом CPC, подтверждённым происхождением и полным источником. Он никогда не добавляется к финансовой CPC-сумме. Разница показывается только при совпадающих identity, календарном окне, timezone и date basis. При другой SKU Performance-сумма скрывается из результата сверки.
- Абсолютная стоимость рекламы на единицу рассчитывается как полный применимый финансовый расход / явно названное положительное количество `ORDERED_UNITS_WINDOW` или `SOLD_UNITS_WINDOW`. Результат раскрывает окно и знаменатель; расход не ограничивается ценой товара. Неполный знаменатель, неизвестная/разовая частота, неподтверждённая карта, несовпадающие даты/identity и net credit без review блокируют ставку. Отличие date basis сохраняется предупреждением: это только распределение расхода окна, не когортная причинная оценка.
- Публичный результат — inspection-only (`read_only=true`, `executed=false`). Новые adapters, расчетный pipeline, DB schema, Telegram UI и price experiment не входят в W06.

## Числовая приёмка

Синтетический N01/N05 проверен: финансовые CPC 1 000 ₽ + подтверждённая CPO 200 ₽ при Performance CPC 1 000 ₽ дают первичный финансовый расход 1 200 ₽, а не 2 200 ₽; на 100 единиц — 12 ₽/шт. Performance показывает только сверку и нулевую разницу. Отдельно 1 200 ₽ на 10 единиц сохраняется как 120 ₽/шт. — выше цены 100 ₽ это не делает сценарий невалидным.

Регрессии также покрывают:

- account-level начисление −300 ₽ с коррекцией +300 ₽ остаётся отдельно и блокирует SKU-итог;
- `MISSING` и `CONFIRMED_ZERO` имеют разный результат;
- Performance-only не становится финансовым начислением;
- несовпадающие SKU, окно, date basis и источник блокируют разницу;
- CPC/CPO/OTHER не складываются при конфликте ключа/категории или неизвестном типе;
- нулевые, incomplete, wrong-identity и wrong-window количества блокируют ₽/шт.;
- unknown/one-off mapping и net credits не превращаются автоматически в прогнозную recurring ставку;
- некорректные rows и календарные окна отвергаются, а не отбрасываются;
- подписанное Performance значение всегда остаётся reconciliation-only и не меняет primary total.

## Фактические проверки

Windows / Python 3.12.10 / pytest 8.4.2, новый `AI_ASSISTANT_STORAGE_ROOT` и `pytest basetemp`, dotenv/plugin autoload выключены, credential-переменные пустые:

```text
tests/test_unit_economics_advertising_evidence_service.py
tests/test_unit_economics_expense_normalizer.py
tests/test_unit_price_observation_normalizer.py
tests/test_period_profit_sku_advertising.py
tests/test_unknown_advertising_financial_evidence_v514_v520.py
tests/test_unit_price_advertising_cap_service.py
90 passed in 1.77s
```

Первый проход выявил ошибку в тестовом ожидании для полного нулевого финансового CPC и опечатку в обращении к result; тесты уточнены. Повторный проход: **90 passed**. Реальные API/сеть, владелец база и бот не использовались. Следующим перед commit выполнить компиляцию изменённых Python-файлов и `git diff --check`.

## Границы и следующий этап

В W06 нет provider-specific mapping или real API evidence. Только последующие source-adapter этапы смогут сформировать normalized finance/Performance snapshots из официальных ответов Ozon и доказать полноту/атрибуцию. До этого чистый resolver намеренно не обещает подтверждённые суммы магазина. W07 продолжает на базе W05: возвраты, невыкупы, точные количества/когорты и отдельное состояние инвентаря.

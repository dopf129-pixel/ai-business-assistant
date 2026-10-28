# Q15 — контракт источников и истории цены

Дата: 2026-10-27
Статус: VERIFIED — контракт перед реализацией наблюдений.

## Решение о доступности цены

На дату проверки официальный Seller API FAQ Ozon отвечает, что историю изменения цены товара через API получить нельзя; её можно посмотреть в карточке товара в личном кабинете, нажав на цену и открыв «История изменений». Источник: [Ozon for dev — Seller API FAQ, ответ о price history](https://dev.ozon.ru/start/257-FAQ-spravochnik-oshibok-i-sposobov-ikh-resheniia) (проверено 27.10.2026).

Следствие: текущий API price read не заполняет прошлую историю. Пользователь может подтвердить, что изменил цену, и указать время применения; такая запись имеет `OWNER_DECLARED` provenance и не становится API-фактом. Не скрейпить личный кабинет и не требовать от пользователя raw API JSON в штатном потоке.

## Виды ценового evidence

| Evidence kind | Поля / часы | Что можно утверждать | Что запрещено |
|---|---|---|---|
| `SCENARIO_PRICE` | `seller_price`, запись сценария | «Рассчитано при заданной цене продавца» | Представлять цену как установленную или фактически продававшуюся |
| `OWNER_DECLARED_PRICE_CHANGE` | точная SKU/store identity, `seller_price`, owner confirmation, `effective_from` (timezone-aware instant), `declared_at`/`recorded_at`, source `USER` | «Владелец подтвердил установку с указанного времени»; применимо как owner-declared input к model | Называть API-подтверждённой ценой или распространять на даты до `effective_from` |
| `CURRENT_PRICE_SNAPSHOT` | точная SKU/store identity, seller/buyer price если поле доступно, `observed_at` — фактическое время чтения текущего API | Текущая карточка показывает значение на момент чтения | Восстанавливать прошлую цену, утверждать отсутствие промежуточных изменений, использовать как всю историю окна |
| `PER_SALE_VERIFIED_PRICE` | точная SKU/store identity, seller price per successful unit, валюта, ID для dedup, `sale_event_at` либо документированный event date, документированная семантика суммы | Цена конкретной продажи и только для этой продажи/схемы | Подменять `sale_event_at` датой начисления, датой отчёта или временем чтения |
| `PRICE_HISTORY_UNCONFIRMED` | отсутствует хотя бы цена, точная identity, нужный час/граница окна или полнота истории | Период можно показать как наблюдение с ограничениями либо как модель | Verified comparison, единый price label для mixed/uncovered window |

`recorded_at` фиксирует момент сохранения в боте, `declared_at` — когда пользователь сообщил, `effective_from` — заявленное им начало действия, `observed_at` — чтение API, `sale_event_at` — событие продажи, `accrual_date` — календарная дата начисления, `report_generated_at` — время сборки отчёта. Эти часы не взаимозаменяемы. Все instants требуют offset/UTC; исходный offset сохраняется. Date-only значения остаются датой с `date_basis`, не конвертируются в фиктивную полночь UTC.

## Сверка с текущей реализацией

- `CurrentProductEconomicsSource.get()` получает текущую цену карточки. `seller_price_as_of` в сценарии — время чтения, а не дата изменения цены; это `CURRENT_PRICE_SNAPSHOT`.
- `FinanceService.get_daily_sale_posting_evidence()` сейчас выдаёт `posting_number`, `sku`, `accrual_date`, `source`, но не сохраняет quantity или per-sale seller price. Набор пока годится для подтверждения наличия positive finance sale rows, но не для price timeline и не для successful-sale units.
- `PeriodProfitOzonClient` собирает `commission.seller_price` в агрегированную diagnostics сумму и считает поле диагностическим, не формульным. Текущая проекция теряет связи с единицей, полнотой SKU и event timestamp. Не считать её проверенной historical series.
- Источник финансовых начислений использует дату начисления по дням. Пока endpoint не даёт документированную и проверенную дату события продажи, `accrual_date` нельзя приравнивать к `sale_event_at`.
- Ozon product prices API читается только как текущий snapshot. Не вводить browser scraping.

## Интервалы, даты и завершённость

- `requested_window` — включительный интервал календарных дат `[from, to]`, с обязательными `window_timezone` и `window_date_basis` для пользовательского окна.
- Источники хранят собственный `source_window`, `source_date_basis`, timezone (если документирована), `requested_at`, `received_at`, `source_as_of`, `complete`, correction/revision и reason. Отсутствующую зону или timestamp не угадывать; несовпадающий basis блокирует сравнение.
- Сбор разрешён только после полного истечения последнего выбранного календарного дня в timezone окна. Это `ELAPSED_WINDOW`, а не гарантия финализации Ozon. `source_complete` и `settlement/finalization` — независимые состояния; поздние корректировки создают новую immutable result revision.
- Если цена менялась внутри дня, весь день нельзя приписывать одной цене. Для одного интервала требуются per-sale event time/price или подтверждённые effective timestamps, позволяющие разделить данные. Иначе `MIXED_PRICES` или `PRICE_HISTORY_UNCONFIRMED`.
- Для сравнения совпадают timezone/date basis и границы окон либо имеется проверенное преобразование; разные/неизвестные clocks выводятся как причина `INCOMPARABLE`.

## Семантика quantities и сумм (N07–N09)

- `successful_sale_units` — количество действительно проданных (не отменённых и не возвращённых согласно выбранной когорте) единиц товара. Источник должен возвращать quantity per SKU; posting count, строка отчёта и число заказов не являются единицами автоматически.
- `ordered_units`, `cancelled_units`, `returned_units` хранятся отдельно с датой события, cohort/basis, source status и полнотой. Отмена по дате изменения статуса не смешивается с отменой по дате создания; возврат по смене статуса не вычитается из другой временной когорты без явного правила.
- Для unit cost сохраняются исходные numerator (`amount`), `successful_sale_units` denominator и component/revenue/date basis. Совместимый агрегат — `Σamount / Σunits`, не простое среднее дневных rates. При `Q=0` per-unit значение неизвестно, сумма остаётся отдельно.
- `revenue_basis` обязателен. Seller revenue и attributed revenue не взаимозаменяемы: одинаковая CPC сумма даёт разную DRR при разных знаменателях. CPC-only остаётся ограниченной CPC-моделью, а не всей рекламой.
- Повторные IDs deduplicate до агрегации; конфликтующие дубликаты делают evidence `CONFLICT`. Partial pages/metrics, missing prices/quantity/date, overlapping windows и разные cost/tax/commission/ad scopes блокируют `CANONICAL_FACT_COMPARABLE`.
- N09 mixed-price window можно разделить только при доказанной price-to-sale mapping и корректном распределении совместимых расходов. Иначе показываются факты окна без ranking конкретной цены; плановые допущения остаются отдельно в `SCENARIO_ASSUMPTIONS`.

## Нормализованные статусы

- `ELAPSED_WINDOW`: календарное окно полностью прошло.
- `COLLECTION_PARTIAL` / `SOURCE_UNAVAILABLE`: источник не подтвердил полный охват или вызов невозможен.
- `PRICE_HISTORY_UNCONFIRMED`: за часть нужного интервала нет доказанного price evidence.
- `OWNER_DECLARED_ONLY`: есть явное заявление владельца, но нет per-sale verification.
- `MIXED_PRICES`: окно содержит разные доказанные цены и нет достаточного разделения по событиям/расходам.
- `CONFLICT`: разные значения для одного evidence identity/часа либо conflicting duplicate.
- `COMPARABLE`: выставляется только quality/comparability gate Q21, не контрактом источника и не наличием одной цены.

Unknown/missing не заменяются нулями. Owner-declared price может поддерживать `MODELLED_FROM_OBSERVED_INPUTS`/scenario, но сама по себе никогда не даёт `CANONICAL_FACT_COMPARABLE`.

## Покрытие и границы реализации

- Q15 — контрактная стадия; runtime не менялся. Она задаёт интерфейс для Q16 durable journal, Q17 source collection, Q18 normalization, Q19 estimation и Q21 comparability gates.
- N07 covered: weighted sums/denominator and zero-quantity semantics.
- N08 covered: distinct seller/attributed revenue DRR bases.
- N09 covered: mixed price/date/cohort/source completeness prevents unsupported ranking.
- Официальный FAQ подтверждает отсутствие price-change history endpoint на дату проверки. Наличие suitable per-sale actual seller-price source, exact sale-event clock and quantity **not yet verified**; следующие этапы обязаны сохранять `PRICE_HISTORY_UNCONFIRMED`, пока поля не подтверждены адаптером/API evidence.

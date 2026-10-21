# Средний расход кросс-докинга — журнал выполнения

Дата начала: 19.10.2026  
ТЗ: `LUNA_CROSS_DOCKING_UNIT_ECONOMICS_TASK_2026-10-19.md`, редакция 3.  
База: `main` / `7e6eabdeba34a822434e5ef417a135995628cc41`.
Ветка: `codex/cross-docking-x00-x01` (свежий managed worktree; старый dirty worktree сохранён отдельно без изменений).

## Правила сохранности

- Основная пользовательская папка не используется для кода; `data/tasks.json` и `data/users.json` остались только в исходной рабочей копии.
- Бот и Ozon API не запускались; `.env` не читался.
- Полный локальный pytest запрещён из-за зафиксированного ACL/shared-storage инцидента; допустимы только bounded targeted profiles с изолированными test-storage и basetemp.
- Merge/deploy не выполнялись.

## Этапы

| Этап | Статус | Результат |
|---|---|---|
| X00 | COMPLETE WITH BOUNDED SCOPE | Официальные list/detail/act контракты и два пользовательских live-примера подтверждают источник фактического количества по SKU и дату завершения для заявки с одной вложенной cross-dock поставкой. Неоднозначные multi-supply заявки и строки без ровно одного SKU далее fail closed. |
| X01 | COMPLETE WITH BOUNDED COVERAGE | Добавлен read-only collection source: cursor list → детали заявок пакетами до 50 → exact accepted act/product lookup. Нормализация использует line `fact_quantity` по SKU и дату только для completed order с одной nested crossdock supply. Multi-supply/unknown/incomplete — `INCOMPLETE`, без denominator. Лимит 64 HTTP попытки/60 секунд; continuation checkpoint остаётся X03. |
| X02 | COMPLETE | Общий классификатор начислений и pure complete-window signed leaf evidence; ставка SKU или магазина на X01 фактически поставленные единицы. Production path пока не подключён. |
| X03 | COMPLETE | Добавлен capped production collector: daily finance pages, type dictionary, supply list/details/acts/products, process-local scoped checkpoints, tenant/window/model cache, in-flight dedup, shared request/time budgets, 28-day finance-cache reuse, and lazy current/scenario factory wiring. Complete evidence only; no calculator arithmetic/UI change yet. Targeted profile: 146 passed. |
| X04 | COMPLETE | Автоматическая ставка подключена к текущей и плановой юнит-экономике; целевая цена, безубыточность, рекламный предел и sensitivity используют общий расчёт; Telegram показывает период, метод SKU/store, фактические начисления/поставленные единицы, coverage и явное исключение неполной ставки. Профиль: **256 passed in 5.54s**. |
| X05 | NEXT | Сохранённые и групповые планы должны фиксировать evidence/version и сохранять legacy behavior без подстановки сегодняшних данных в историю. |
| X06 | PENDING | Регрессии, документация, CI и review handoff после X00–X05. |

## X03 — bounded collection, checkpoint, cache and production wiring — 2026-10-21

- Added `OzonCrossDockingFinanceSource` to read all inclusive daily accrual pages with bounded cursor advancement; partial-day rows remain private to a checkpoint and cannot enter the 56-day financial projection.
- Added `CrossDockingUnitRateSource`, which composes the signed X02 financial projection with the X01 supply evidence. It limits collection to 64 actual HTTP attempts and 60 seconds, accounts attempts in the existing operation trace, shares a 28-day request-local finance cache, and resumes only the same tenant/store/date-window/model scope.
- Checkpoints and completed evidence remain process-local, size-bounded and TTL-bound. Completed evidence is cached; an incomplete result carries no numeric rate. Force refresh resets the matching checkpoint. Raw daily finance rows are discarded after the complete pure projection.
- Reused one `PeriodProfitFinanceService` in the current economics and unit-price scenario factories. The current source exposes the read-only provider; the scenario source adds an evidence projection only and still does not subtract it from price/profit (that is X04).
- A fresh cold request consumes the bounded budget and resumes in the next explicit calculation; tests verify no partial rate, no cross-store reuse, one dictionary lookup per resumed window, overlap reuse, lazy initialization and shared trace limits.
- Verification on Windows: isolated targeted pytest profile (10 related test files): **146 passed in 2.76s**. Full local pytest was not run because of the recorded ACL/shared-storage restriction. No live Ozon call, bot run, merge or deploy.
- Scope: X03 complete. Next: X04 mathematical integration and user-facing labels, followed by X05 persistence/version compatibility.

## X04 — калькулятор, текущая экономика и Telegram — 2026-10-21

- `CurrentProductEconomicsSource` получает ставку только для подтверждённых tenant/SKU; сценарный источник использует отдельный быстрый price/commission path, чтобы не запускать один и тот же 56-дневный сбор дважды. При отсутствии конфигурации/identity/полного окна возвращается явное unavailable evidence; числовая ставка не заполняется нулём.
- Текущая модель вычитает кросс-докинг один раз из прибыли до налога; исходный marketplace fee subtotal остаётся прежним. USN_INCOME сохраняет выручечную налоговую базу; USN_INCOME_MINUS_EXPENSES пропускает расход через существующий TaxService.
- Единый `UnitPriceScenarioService` переносит optional rate в пересчёт цены. Старый input/result contract остаётся прежним, когда X-ключ отсутствует; когда источник неполон, сценарий считает без X и явно добавляет исключённую область. Target price, break-even, advertising cap, price comparison и sensitivity используют этот же forward calculator.
- Current and planning UI показывают фактический период 56 дней, SKU-rate/store estimate, signed expense total / actual supplied units, data coverage и безопасную причину, если ставка не включена. В Telegram выводе нет source SKU или supply ID. Unknown/incomplete current result не кэшируется как complete, следующий явный запрос может продолжить checkpoint.
- Регрессии по 17 связанным модулям (cross-dock collectors, current/scenario sources/providers, cache, runtime, target solver, ad-cap, sensitivity и factory wiring): **256 passed in 5.54s** на Windows. Использованы отдельные test-storage и pytest basetemp с отключённой plugin autoload. `git diff --check` прошёл до документационного обновления; полный local pytest запрещён из-за известного ACL/shared-storage инцидента. Live Ozon API, bot, merge и deploy не запускались.
- X04 complete. Next: X05 frozen component evidence/version through saved, batch and historical plan paths.

## X02 — signed finance evidence and pure rate — 2026-10-20

- Extracted the fee category aliases and matching rules into `app/services/ozon_accrual_fee_classifier.py`; `ExperimentalStoreEconomicsRuntimeService` delegates to this shared helper so the existing report and new unit-cost logic cannot drift to separate cross-docking labels.
- Added `CrossDockingFinancialEvidenceService`. It consumes an inclusive date-to-raw-response map from `/v1/finance/accrual/by-day`, validates every day, fee type, leaf amount and `accrual_id`, deduplicates exact repeats within the same accrual day and fails closed on conflicting identity. It traverses the existing FinanceService leaf scopes (posting delivery services, item fees, non-item fees and container fees), classifies from the existing Ozon accrual type dictionary, sums actual signed leaf amounts and never includes aggregate parent `total_amount`.
- SKU leaf amounts remain SKU-specific; non-item/container amounts remain shared. Positive signed rows reduce the net expense total and are included by their finance date; the service does not need the original supply ID, so a correction to an older supply does not add historical Q again.
- `calculate_rate` accepts only complete X01 supply evidence and a requested SKU. It uses SKU C/Q when expense attribution is complete, store C/Q when shared amounts exist, and keeps no-supply, target-SKU-not-participating, incomplete evidence, zero denominator, observed zero and net refund distinct. The input contract has no sales metric. Decimal arithmetic uses HALF_UP cents and exposes raw ratio and rounding residual.
- Added 19 pure tests; combined with X01 supply normalization/source and existing experimental report/finance breakdown regressions: **102 passed in 1.70s**. The first run exposed that the old report depends on a class-level matcher alias; it was restored with identical semantics before the successful rerun. Separate temporary `AI_ASSISTANT_STORAGE_ROOT` and pytest basetemp were used. Full local pytest/live API/bot not run.
- Static AST compilation and `git diff --check` are recorded in the final verification section below; no code is integrated into the calculators yet.

## Follow-up — ID заявки для актов Ozon — 2026-10-20

- Вывод пользователя показал, что товарные строки акта доступны, а запросы `/v3/supply-order/get` и `/v1/supply-order/act/summary/get` возвращались с общей ошибкой. Проверка контрактов выявила несоответствие ID: пользователь вводит `supply_id`, тогда как оба метода принимают ID заявки `order_id`.
- Исправление выполняет ограниченный поиск через `/v3/supply-order/list` (до 2 страниц по 100 ID) и `/v3/supply-order/get` (пакеты по 50), затем принимает только точное совпадение вложенного `supplies[].supply_id`. Сводка акта вызывается с найденным `order_id`; при отсутствии точного совпадения детали не подставляются.
- Общий поиск ограничен 60 секундами; каждый запрос поиска выполняется максимум с одной попыткой. HTTP статус отображается в безопасном виде, response body не выводится.
- Добавлены регрессии, где `supply_id` намеренно отличается от `order_id`, и проверка перехода на следующую cursor-страницу. Live Seller API повторно не вызывался. Расчёт кросс-докинга не изменён; X00/X01 остаются заблокированы прежними бизнес-evidence требованиями по дате приёмки и значению количества.
- `tests/test_experimental_supply_act_diagnostic.py`: **19 passed in 0.43s** на Python 3.12 из `.venv` с изолированным basetemp и `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. Syntax-only compile трёх изменённых Python файлов и `git diff --check` прошли. Полный local pytest не запускался из-за зафиксированной ACL/shared-storage проблемы. Exact-head Verify **39419764407** для code SHA `7784d457528dd7b8c3f0b433668ed30768bb25ab` прошёл Windows и full-verification: полные тесты, compilation и production Docker build/runtime smoke успешны.

## X00 evidence update — 2026-10-20

- Пользователь прислал текст официальной документации Seller API для `POST /v3/supply-order/list` и `POST /v3/supply-order/get`. `list` принимает `filter.states`, `last_id`, `limit` (1–100), `sort_by` (`ORDER_CREATION`, `ORDER_STATE_UPDATED_AT`, `TIMESLOT_FROM_UTC`, `TIMESLOT_FROM_LOCAL`) и `sort_dir` (`ASC`, `DESC`); ответ возвращает `order_ids[]` и `last_id` для продолжения. Пример фильтра использует `states=["COMPLETED"]`.
- `get` принимает не более 50 `order_ids` за запрос. В `orders[]` документированы `order_id`, `created_date`, `state`, `state_updated_date` и вложенные `supplies[]`; в примере каждой поставки есть `supply_id`, `state`, `is_crossdock`, `bundle_id`, `storage_warehouse.arrival_date` и `supply_tags`. Это подтверждает официальный признак кросс-докинга и способ связать заявку с отдельными поставками.
- Схема не утверждает, что `state_updated_date` является датой фактической приёмки каждой поставки в заявке с несколькими `supplies[]`; поле названо датой обновления статуса заявки. `storage_warehouse.arrival_date` помечено устаревшим в официальном канале и не считается датой завершения. До привязки расчёта к периоду нужен фактический ответ для принятой заявки/акта, сверенный с датой акта в кабинете Ozon.
- Список возвращает только идентификаторы заявок, а заявленные/фактические количества находятся в отдельном API актов. Ранее для одного принятого акта `fact_quantity=500` совпал с кабинетом, но `approved_quantity=0`; нужны ответы по частичной или split-поставке, чтобы удостовериться, что построчный `fact_quantity` применим как знаменатель без включения плана или дублей.
- Части X00 по list/detail contract и cross-dock discriminator закрыты на основании первичного документа; этап остаётся PARTIAL/BLOCKED по датировке actual acceptance и универсальной семантике фактического количества. X01 остаётся заблокирован до этого evidence. Изменений кода, внешних запросов и API вызовов в этом шаге не было; проверка документации — ручное сопоставление схемы с source matrix.

- Официальная схема, вставленная пользователем из документации Seller API, описывает `/v1/supply-order/act/summary/get` с `order_id` и ответом `supplies_acts[].supply_acts[]`, включая `supply_id`, `act_state`, `created_date`, `deadline_utc`, `summary` и `type`. Для `/v1/supply-order/act/product/get` описаны построчные `declared_quantity`, `approved_quantity`, `fact_quantity` и `sku_info.sku`. Запросы `act/accept` и `act/accept/status` не используются.
- Пользователь запустил продуктовую диагностику для известного принятого акта из акта приёмки/Excel: UI показывает 500 принятых единиц, API вернул `declared_quantity=500`, `fact_quantity=500`, `approved_quantity=0`. Это реальное подтверждение `fact_quantity` для одного принятого акта с совпадающим заявленным и принятым количеством; значение `approved_quantity` при этом нельзя использовать как accepted denominator. Идентификаторы в журнал не записаны.
- Изменён diagnostic helper: после успешного `product/get` он выполняет одну bounded read-only попытку `summary/get`, используя введённое число как `order_id`, и сообщает, совпал ли возвращённый `supply_id`. При несовпадении он не показывает состояние/дату чужого акта. Неподтверждённый `created_date` явно не трактуется как completion date. `tests/test_experimental_supply_act_diagnostic.py` — **10 passed** (Windows Python 3.12, isolated pytest basetemp, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=app`).
- Follow-up code SHA `770839eb28edaf9d4f3fce207f89449f55684059`, PR #710: Verify run **39400776436** succeeded; Windows/Linux each **3,530 passed**, compile and production Docker build/runtime smoke succeeded. This confirms the diagnostic follow-up; the full 56-day calculation remains blocked on source contract evidence.
- Публичный официальный канал ранее подтвердил наличие `/v3/supply-order/list` и `/v3/supply-order/get` ([анонс 17.09.2025](https://t.me/s/OzonSellerAPI?before=561), [анонс переноса 30.10.2025](https://t.me/s/OzonSellerAPI?after=564)). На тот момент полную схему получить не удалось; пользователь позже предоставил её текст из официальной документации. Схема подтверждает cursor pagination и `supplies[].is_crossdock`, но сама по себе не определяет per-supply completion timestamp и accepted-quantity semantics.
- В текущей ветке код только read-only и не использует diagnostic values в юнит-экономике. Прогнозные, planned и прямые FBO количества запрещены как fallback. X01 остаётся заблокирован только по неразрешённым вопросам фактической даты и quantity mapping, а не по отсутствию list/detail схемы.

## X00 closure — user-confirmed one-product supplies — 2026-10-20

- Пользователь предоставил фактическую API-диагностику для частично принятой поставки: заявлено `200`, `fact_quantity=100`, строковое `approved_quantity=100`, при этом summary-level `approved_quantity=0` и `fact_quantity=100`. В кабинете поставка завершена 29.09.2026; `/v3/supply-order/get` вернул `state=COMPLETED` и `state_updated_date=2026-09-29T09:22:15Z`; акт создан 28.09.2026. Тем самым `created_date` не является датой завершения, а `state_updated_date` совпал с датой завершения UI для проверенной заявки с одной вложенной поставкой.
- Ранее проверенный полный акт: 500 заявлено/принято, построчный `fact_quantity=500`, `approved_quantity=0`; дата акта и состояние согласуются с завершённой cross-dock поставкой. Два наблюдения показывают, что для завершённой single-supply заявки построчный `fact_quantity` отражает фактическое принятое количество, включая частичный приём, тогда как `approved_quantity` и summary totals нельзя брать как знаменатель.
- Пользователь уточнил доменное правило: **1 поставка = 1 товар**. Поэтому подтверждённую привязку API `supply_id → items[].sku_info.sku → fact_quantity` можно агрегировать по SKU. В коде требуется fail closed при нескольких разных SKU в одной поставке, нескольких неразрешённых/непринятых acceptance acts, отсутствующем SKU/количестве или другой неоднозначности.
- Дата завершения в X01 берётся по `orders[].state_updated_date` только у `COMPLETED` заявки с единственной вложенной supply, которая сама `COMPLETED` и `is_crossdock=true`. Это доказано на проверенном UI/API примере с точностью до календарной даты `Europe/Moscow`; `created_date`, плановая дата и устаревший `arrival_date` не используются. Заявки с несколькими nested supplies пока обозначаются неполным покрытием и не попадают в знаменатель: одна проверка не доказывает individual completion date для split/multi-supply заявок.
- X00 закрыт только в указанной границе. Универсальная семантика для нескольких supplies в одном order не утверждается; ограничение будет отражено в DTO/coverage и журнале. Зависимый X01 начат.

## X01 — read-only supply evidence collection — 2026-10-20

- Added `app/services/cross_docking_supply_evidence_service.py`, a pure normalizer returning immutable per-SKU records and a total only for fully covered input. It accepts product-row `fact_quantity`, requires an exact accepted `ACCEPTANCE` act and agreement completion, requires matching act summary total plus `unidentified_quantity == 0`, and rejects multiple SKUs per supply. Order and supply IDs are reduced to a SHA-256 identity fingerprint in output; raw response payloads are not persisted.
- Added `app/services/cross_docking_supply_source.py` over existing `OzonClient` read-only adapters. It follows `/v3/supply-order/list` cursor pages (`COMPLETED`, `ORDER_STATE_UPDATED_AT DESC`), reads `/v3/supply-order/get` in 50-ID batches, then exact act summary and product endpoints for in-window single supplies. It validates list/detail coverage, cursor progress, duplicate/conflicting orders and Moscow local date boundaries. No write/accept endpoints are called.
- Source caps each collection slice at 64 HTTP attempts and 60 seconds; each endpoint call has one attempt and is constrained by the remaining source deadline. The underlying Ozon client still enforces inherited request-trace budgets. If pagination, detail, act, product or budget coverage is incomplete, normalized `total_units` is `None`; no partial denominator is offered. Durable continuation/checkpoint is explicitly X03.
- Added `tzdata>=2025.1,<2027` because the local Windows Python lacked IANA timezone data; the named project timezone is `Europe/Moscow` per the task. Tests inject the configured +03 offset for deterministic local boundaries; deployment uses IANA data from the dependency.
- New focused tests: `tests/test_cross_docking_supply_evidence_service.py` and `tests/test_cross_docking_supply_source.py`: **34 passed in 0.54s**, Python 3.12, isolated basetemp, pytest plugin autoload disabled/cache provider disabled. Combined with `tests/test_experimental_supply_act_diagnostic.py`: **53 passed in 1.03s**. Syntax-only compile and `git diff --check` passed. Full local pytest not run (known ACL/shared-storage incident); no live Ozon API calls or bot launch.
- X01 complete as the source/projection stage. Known boundary: a multi-supply order has no proven per-supply date and keeps total unavailable. The no-cache source can complete small windows in one slice; cold windows that exceed limits stay incomplete until X03 resume support.

## X00 implementation update — 2026-10-20

- Message output is capped by showing at most 4 product rows, 4 supplies, and 4 summary acts; aggregate totals and truncation notes remain. Stress regression builds 50 large rows/acts/supplies and confirms the result stays under Telegram's 4,096-character limit.
- Добавлен read-only client adapter к `POST /v3/supply-order/get` с ограничением на один положительный int64 `order_id`, one-attempt timeout budget и документированным `order_ids: [id]` payload.
- Существующая экспериментальная диагностика после ввода ID дополнительно проверяет детали заявки. Она показывает только безопасные типы полей, совпавший order status/state_updated_date, количество вложенных supplies, их state и boolean `is_crossdock`; идентификаторы, названия склада, SKU и другие значения payload не выводятся. Устаревший `storage_warehouse.arrival_date` помечается как ненадёжная дата приёмки.
- Добавлены regressions, что несовпавший order ID не раскрывает status, даты, supply IDs и складские поля из чужого ответа, а большой ответ остаётся короче лимита Telegram. `tests/test_experimental_supply_act_diagnostic.py`: **14 passed in 0.51s** с isolated storage/basetemp и отключённым plugin autoload; `git diff --check` прошёл. Обычная автозагрузка тестового плагина на Windows показала все тесты как PASSED, но процесс не завершился штатно; результат не использован как чистое завершение. Exact-head Verify **39407794793**, SHA `e9e2f2cec4c55b763660af8dca07ef6f9f8bed10`: Linux и Windows по **3,534 passed**, compile и production Docker build/runtime smoke успешны.
- Этот helper остаётся диагностикой: `state_updated_date` не назначается датой приёмки, `arrival_date` не используется как completion date, а единицы не подключены к стоимости в калькуляторе. X00/X01 остаются заблокированы до сверки фактического detail+act ответа, особенно для split/partial supplies.

## X00 — источник и фактические результаты

### Подтверждено официальными объявлениями Ozon

- Seller API канал Ozon объявил 11.08.2026 бета-методы `/v1/supply-order/act/summary/get` и `/v1/supply-order/act/product/get` для работы с актами FBO после поставки на склады: [официальная запись канала](https://t.me/s/OzonSellerAPI?before=685). В той же группе присутствует изменяющий метод `/v1/supply-order/act/accept`; его не использовать.
- Официальный канал пометил `storage_warehouse.arrival_date` в `/v3/supply-order/get` устаревшим 09.02.2026: [история официального канала](https://t.me/s/OzonSellerAPI?before=620). Это поле не используется как completion date.
- Официальная документация `docs.ozon.ru/api/seller/` не загрузилась в web и браузере из-за redirect loop / browser transport failure.

### Кандидаты из зеркала OpenAPI (не самостоятельное официальное доказательство семантики)

- Индекс зеркала заявляет, что выгружен из официального `docs.ozon.ru/api/seller/swagger.json`, проверен 18.10.2026: [индекс схемы](https://github.com/MissiaL/ozon-api/blob/main/references/index.md). Доступная схема подтверждает `/v3/supply-order/list`, `/v3/supply-order/get`, `/v1/supply-order/bundle`, но не содержит отдельных схем двух новых beta-методов актов.
- Отдельная генерация схемы `/v3/supply-order/get` показывает `orders[].state`, `state_updated_date`, `supplies[].is_crossdock`, `supply_id`, `bundle_id`, `state`. При этом `state_updated_date` относится к заявке, не доказывает время приёмки каждого split supply.
- Схема `/v3/supply-order/list` использует `filter.states`, `last_id`, `limit`, `sort_by`, `sort_dir`; список идентификаторов заявок сам по себе не содержит дату исполнения и фактическое SKU quantity.
- Historical note: до получения официальной документации и фактического ответа акта `fact_quantity`, `approved_quantity` и `created_date` рассматривались как непроверенные поля из сторонней схемы. Сейчас поля `fact_quantity`/`approved_quantity` подтверждены официальным текстом и наблюдением для одного принятого акта; их общая семантика для partial/split supplies и `created_date` как completion date остаются неподтверждёнными. Production calculation на этих предположениях не основан.

### Что обязательно подтвердить перед X01

Требуемые для single-supply формы evidence получены. Для X01 использовать per-SKU `fact_quantity` только после точного сопоставления принятого acceptance act с `supply_id`; использовать `state_updated_date` лишь для completed order с одной completed cross-dock supply. Multi-supply order остаётся неполной частью выборки до отдельного подтверждения индивидуальных дат. Не использовать даты создания/планирования или summary-level quantity как fallback.

## Проверки

- Проверены baseline и branch managed worktree: `6496f0d5`, `codex/cross-docking-unit-economics`. Корневые `data/tasks.json`, `data/users.json`, их lock и main checkout не редактировались.
- Подтверждены официальные объявления методов supply list/get v3 и beta FBO acts. Live Ozon/Telegram запросов не делалось.
- После появления точной пользовательской схемы `/v1/supply-order/act/product/get` добавлены endpoint adapter, Telegram input flow в существующий experimental runtime и кнопка. Запрос требует ручного `supply_id` только для диагностики; рабочий расчёт по-прежнему должен находить поставки автоматически.
- `tests/test_experimental_supply_act_diagnostic.py`: **6 passed**. Связанный bounded профиль из 6 модулей (включая menu discovery) — **67 passed in 3.43s** на проектном Python 3.12 с отдельными `AI_ASSISTANT_STORAGE_ROOT` и pytest basetemp. Выполнены только fake API тесты.
- Дополнительный exploratory run, включавший legacy `test_assistant_button_handler_flow.py`, дал 59 passed / 4 failed: ошибки в старых `analyze/history/memory/plan` тестах из-за несовпадения сигнатуры `FakeAssistant.ask`; новая диагностическая callback/input regression в том же профиле прошла. Причину не приписываем коду этой ветки без отдельного baseline run.
- `compileall` не смог записать `__pycache__` в ACL-ограниченном worktree (`WinError 5`). Syntax-only compilation всех 6 изменённых Python файлов прошла; `git diff --check` прошёл. Первый exact-head CI (`39312704457`) на Linux нашёл одно устаревшее ожидание callbacks экспериментального меню (3 525 passed, 1 failed). Исправлена проверка `tests/test_telegram_help_discovery.py`. Follow-up Verify run **39313014256** для code SHA `37c07dfb7779eece976210fb3dba6ac4ead27f8f` завершился успешно: Linux и Windows по **3 526 passed**, compile, Docker build и runtime smoke successful. Полный pytest локально не запускался.

## Следующий шаг

PR #710 с `summary/get` прошёл Verify run **39400776436** для code SHA `770839eb28edaf9d4f3fce207f89449f55684059`: Windows и Linux по **3,530 passed**, compile/Docker build/runtime smoke successful. Схемы list/get теперь подтверждены официальным текстом пользователя; следующий шаг — получить через read-only Seller API и сопоставить фактический order detail для известного принятого кросс-докинга. Не включать неизвестный числитель или неподтверждённую дату в юнит-экономику. Реальный бот автоматически не запускать.

## Дополнительное подтверждение пользователя — акт приёмки в кабинете Ozon

Пользователь прислал скрин карточки акта поставки (идентификаторы товара и поставки не копируются в журнал). На нём видно:

- статус акта «Принят»;
- дата документа 16 октября и отдельно запланированная дата поставки 13 октября;
- точка отгрузки с явным текстом «КРОССДОКИНГ»;
- по строке SKU: заявлено 500 шт., принято на складе 500 шт., расхождение 0.

Это подтверждает, что кабинет Ozon показывает фактически принятое количество по SKU и позволяет отличить cross-docking supply по сведениям карточки. Сам присланный XLSX содержит то же фактическое количество, но не включал дату/вид отгрузки. Нельзя использовать planned date вместо даты завершения/акта без соответствующего API-поля.

Пользователь подтвердил продуктовое требование: эти данные должен автоматически получать бот через Seller API; ручная выгрузка актов не подходит для штатного пути.

Официальный канал Ozon подтвердил наличие beta read-only endpoints `/v1/supply-order/act/summary/get` и `/v1/supply-order/act/product/get` для актов FBO: [объявление Ozon Seller API](https://t.me/s/OzonSellerAPI?before=685). Точные поля актов и product quantity получены из официальной документации и фактического ответа; через предоставленную позже официальную схему также подтверждён `supplies[].is_crossdock`. Остаётся фактически сверить per-order/per-supply дату и количество на `/v3/supply-order/get`, особенно для split/partial supply. `/v1/supply-order/act/accept` и `/v1/supply-order/act/accept/status` не нужны для чтения; согласующие методы исключены.

### Обновлённый статус X00

X00 частично подтверждён пользовательским UI evidence и официальной схемой. Список/детали, cursor pagination и `is_crossdock` документированы. Для безопасной автоматической интеграции остаётся подтвердить фактическую дату события и универсальную семантику SKU quantity по API ответу, прежде всего для split/partial supplies. X01 остаётся заблокирован до такого evidence; расчёт пока не изменён.

### Следующий шаг

Проверить фактический ответ `/v3/supply-order/get` и связать его с уже доступной актовой диагностикой по совпадающему supply. Для этого нужен ID заявки из акта в экспериментальном боте; оставить в присланном результате только структуру, поля, типы, статусы и даты. Не запускать Ozon API из этой рабочей копии и не включать неуточнённые данные в расчёт.

Historical note: before the user supplied the official list/get documentation, direct retrieval from the official docs page failed because of a redirect loop and browser payload limits. That retrieval limitation is resolved for the list/get schema; the remaining uncertainty concerns runtime field values and their meaning for a completed split/partial supply.

## Пользователь прислал схему методов актов FBO

В pasted official documentation подтверждены `POST /v1/supply-order/act/summary/get` с `order_id` int64 и `POST /v1/supply-order/act/product/get` с `supply_id` int64. Продуктовый ответ содержит `supply_acts[].items[]`, `sku_info.sku` и количества `approved_quantity`, `declared_quantity`, `fact_quantity`, `unidentified_quantity`; сводка акта содержит `act_state`, `created_date`, `summary` и `supply_id`. Изменяющие `/v1/supply-order/act/accept` и `/accept/status` не вызываются.

Добавлен bot diagnostic helper для `product/get`: пользователь явно вводит `supply_id` из карточки; вызов выполняется один раз с ограниченными повторами и timeouts; output ограничен количеством и типами полей и не раскрывает идентификаторы/товарные атрибуты. Этот helper не выдаёт дату/статус и не заменяет будущий automatic supply collection. Focused test file `tests/test_experimental_supply_act_diagnostic.py`: **6 passed**. Остальные проверки и CI ожидают следующего связанного этапа.

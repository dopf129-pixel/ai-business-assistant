# Средний расход кросс-докинга — журнал выполнения

Дата начала: 19.10.2026  
ТЗ: `LUNA_CROSS_DOCKING_UNIT_ECONOMICS_TASK_2026-10-19.md`, редакция 3.  
База: `main` / `6496f0d5e277df9a3f9690dfa0f1abc8c7c4b832`.  
Ветка: `codex/cross-docking-unit-economics` (изолированный managed worktree).

## Правила сохранности

- Основная пользовательская папка не используется для кода; `data/tasks.json` и `data/users.json` остались только в исходной рабочей копии.
- Бот и Ozon API не запускались; `.env` не читался.
- Полный локальный pytest запрещён из-за зафиксированного ACL/shared-storage инцидента; допустимы только bounded targeted profiles с изолированными test-storage и basetemp.
- Merge/deploy не выполнялись.

## Этапы

| Этап | Статус | Результат |
|---|---|---|
| X00 | PARTIAL / BLOCKED — list/detail contract и cross-dock flag подтверждены официальной схемой; фактическая дата приёмки и quantity mapping ещё требуют live evidence | Официальная документация подтверждает `/v3/supply-order/list` cursor `last_id` и `/v3/supply-order/get` с `state`, `state_updated_date`, вложенными `supplies[]`, `is_crossdock`, `supply_id`, `state`. По одному принятому акту ранее `fact_quantity=500` совпал с кабинетом, а `approved_quantity=0` не совпал. Семантика completion time и применимость `fact_quantity` к split/partial supplies не подтверждены. |
| X01 | BLOCKED BY X00 | Без подтверждённых actual quantity/status/date нельзя безопасно считать denominator. |
| X02 | BLOCKED BY X01 | Pure calculation не включён в production path до определения DTO/coverage контракта. |
| X03 | BLOCKED BY X00–X02 | Не проектировать checkpoint/cache до подтверждения completion date и actual-quantity mapping. |
| X04 | BLOCKED BY X03 | Нельзя добавлять непроверенную ставку в текущую модель/Telegram. |
| X05 | BLOCKED BY X04 | Нет подтверждённого snapshot и версии компонента X. |
| X06 | PENDING | Регрессии, документация, CI и review handoff после X00–X05. |

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

Для X01 нужен обезличенный read-only ответ `/v3/supply-order/get` для заявки с известным принятым кросс-докингом, сверенный с кабинетом. Для проверки даты сопоставить `state_updated_date` и дату акта из `/v1/supply-order/act/summary/get`; для quantity проверить `fact_quantity` по каждому `supply_id` в `/v1/supply-order/act/product/get`, включая частичную или split-поставку, если такая уже есть. Оставить имена полей, типы, enum-статусы, shape и формат дат; скрыть идентификаторы, SKU и названия. Не присылать Client ID, API key, заголовки авторизации, `.env` или полную карточку товара. Схемы list/get уже получены и повторно не нужны.

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

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
| X00 | PARTIAL / BLOCKED — актовый schema частично подтверждён; нужен контракт списка/деталей и фактической даты | Реализована one-shot диагностика `/v1/supply-order/act/product/get` по введённому `supply_id`. Точный контракт endpoint получен из присланной пользователем официальной документации. Дата и статус в этом методе отсутствуют; для автоматического периода всё ещё не подтверждены list/detail pagination, scheme flag и completion timestamp. |
| X01 | BLOCKED BY X00 | Без подтверждённых actual quantity/status/date нельзя безопасно считать denominator. |
| X02 | BLOCKED BY X01 | Pure calculation не включён в production path до определения DTO/coverage контракта. |
| X03 | BLOCKED BY X00–X02 | Не проектировать checkpoint/cache вокруг неподтверждённого запроса/пагинации актов. |
| X04 | BLOCKED BY X03 | Нельзя добавлять непроверенную ставку в текущую модель/Telegram. |
| X05 | BLOCKED BY X04 | Нет подтверждённого snapshot и версии компонента X. |
| X06 | PENDING | Регрессии, документация, CI и review handoff после X00–X05. |

## X00 — источник и фактические результаты

### Подтверждено официальными объявлениями Ozon

- Seller API канал Ozon объявил 11.08.2026 бета-методы `/v1/supply-order/act/summary/get` и `/v1/supply-order/act/product/get` для работы с актами FBO после поставки на склады: [официальная запись канала](https://t.me/s/OzonSellerAPI?before=685). В той же группе присутствует изменяющий метод `/v1/supply-order/act/accept`; его не использовать.
- Официальный канал пометил `storage_warehouse.arrival_date` в `/v3/supply-order/get` устаревшим 09.02.2026: [история официального канала](https://t.me/s/OzonSellerAPI?before=620). Это поле не используется как completion date.
- Официальная документация `docs.ozon.ru/api/seller/` не загрузилась в web и браузере из-за redirect loop / browser transport failure.

### Кандидаты из зеркала OpenAPI (не самостоятельное официальное доказательство семантики)

- Индекс зеркала заявляет, что выгружен из официального `docs.ozon.ru/api/seller/swagger.json`, проверен 18.10.2026: [индекс схемы](https://github.com/MissiaL/ozon-api/blob/main/references/index.md). Доступная схема подтверждает `/v3/supply-order/list`, `/v3/supply-order/get`, `/v1/supply-order/bundle`, но не содержит отдельных схем двух новых beta-методов актов.
- Отдельная генерация схемы `/v3/supply-order/get` показывает `orders[].state`, `state_updated_date`, `supplies[].is_crossdock`, `supply_id`, `bundle_id`, `state`. При этом `state_updated_date` относится к заявке, не доказывает время приёмки каждого split supply.
- Схема `/v3/supply-order/list` использует `filter.states`, `last_id`, `limit`, `sort_by`, `sort_dir`; список идентификаторов заявок сам по себе не содержит дату исполнения и фактическое SKU quantity.
- В сторонней схеме актов встречаются предполагаемые `fact_quantity`, `approved_quantity` и `created_date`, но источник/семантика этих полей и enum `act_state` не удалось подтвердить официально или фактическим response. Production код на этих догадках не основан.

### Что обязательно подтвердить перед X01

Нужен один обезличенный ответ реального completed cross-docking supply для read-only методов актов: поля и типы, перечисления `act_state`, идентификатор/связь supply и SKU, значение фактически принятого количества (отличить `fact_quantity` от declared/approved/planned), дата акта или события приёмки и полная пагинация. Идентификаторы/названия/числа SKU можно заменить; названия полей, типы, enum-статусы, shape и формат дат оставить. Не присылать Client ID, API key, заголовки авторизации, `.env` или полную карточку товара.

## Проверки

- Проверены baseline и branch managed worktree: `6496f0d5`, `codex/cross-docking-unit-economics`. Корневые `data/tasks.json`, `data/users.json`, их lock и main checkout не редактировались.
- Подтверждены официальные объявления методов supply list/get v3 и beta FBO acts. Live Ozon/Telegram запросов не делалось.
- После появления точной пользовательской схемы `/v1/supply-order/act/product/get` добавлены endpoint adapter, Telegram input flow в существующий experimental runtime и кнопка. Запрос требует ручного `supply_id` только для диагностики; рабочий расчёт по-прежнему должен находить поставки автоматически.
- `tests/test_experimental_supply_act_diagnostic.py`: **6 passed**. Связанный профиль из 5 целевых модулей (`test_experimental_store_economics`, factory, analytics data client, request-attempt diagnostics и новый тест) — **58 passed in 3.12s** на проектном Python 3.12 с отдельными `AI_ASSISTANT_STORAGE_ROOT` и pytest basetemp. Выполнены только fake API тесты.
- Дополнительный exploratory run, включавший legacy `test_assistant_button_handler_flow.py`, дал 59 passed / 4 failed: ошибки в старых `analyze/history/memory/plan` тестах из-за несовпадения сигнатуры `FakeAssistant.ask`; новая диагностическая callback/input regression в том же профиле прошла. Причину не приписываем коду этой ветки без отдельного baseline run.
- `compileall` не смог записать `__pycache__` в ACL-ограниченном worktree (`WinError 5`). Syntax-only compilation всех 5 изменённых Python файлов прошла; `git diff --check` прошёл. Полный pytest не запускался. Exact-head CI не запускался.

## Следующий шаг

После слияния этой ветки и обновления бота пользователь сможет нажать «Эксперименты» → «Проверить товары в акте поставки», ввести видимый в акте ID поставки и получить безопасную сводку ответа `product/get`. В текущем методе нет даты/статуса. После получения этой диагностики продолжить X00: получить официальный контракт `/v3/supply-order/list`, `/v3/supply-order/get` и `/v1/supply-order/act/summary/get`; подтвердить enum/status, cross-dock identity, фактическую дату, actual quantity и пагинацию. Не включать неизвестный числитель в юнит-экономику. Действующий бот не запускать и не обновлять автоматически.

## Дополнительное подтверждение пользователя — акт приёмки в кабинете Ozon

Пользователь прислал скрин карточки акта поставки (идентификаторы товара и поставки не копируются в журнал). На нём видно:

- статус акта «Принят»;
- дата документа 16 октября и отдельно запланированная дата поставки 13 октября;
- точка отгрузки с явным текстом «КРОССДОКИНГ»;
- по строке SKU: заявлено 500 шт., принято на складе 500 шт., расхождение 0.

Это подтверждает, что кабинет Ozon показывает фактически принятое количество по SKU и позволяет отличить cross-docking supply по сведениям карточки. Сам присланный XLSX содержит то же фактическое количество, но не включал дату/вид отгрузки. Нельзя использовать planned date вместо даты завершения/акта без соответствующего API-поля.

Пользователь подтвердил продуктовое требование: эти данные должен автоматически получать бот через Seller API; ручная выгрузка актов не подходит для штатного пути.

Официальный канал Ozon подтвердил наличие beta read-only endpoints `/v1/supply-order/act/summary/get` и `/v1/supply-order/act/product/get` для актов FBO: [объявление Ozon Seller API](https://t.me/s/OzonSellerAPI?before=685). Неизменяющий путь возможен по назначению методов, но точные request/response fields, pagination, actual/completed timestamp и scheme discriminator пока не подтверждены доступной официальной схемой. `/v1/supply-order/act/accept` и `/v1/supply-order/act/accept/status` не нужны для получения факта; согласующий endpoint исключён.

### Обновлённый статус X00

X00 частично подтверждён пользовательским UI evidence: actual accepted SKU quantity существует, UI показывает статус/дату документа и точку cross-dock. Этого недостаточно для безопасной автоматической интеграции без API schema, включая получение списка исторических завершённых поставок, дату для окна, точный cross-dock flag и пагинацию. X00 остаётся BLOCKED до получения подтверждённой официальной схемы/фактического API response; X01–X06 не начаты.

### Следующий шаг

Продолжить поиск читаемой official API schema. Если она недоступна, необходим один обезличенный response от read-only `/v1/supply-order/act/summary/get` и `/v1/supply-order/act/product/get` плюс supply detail/list, сохраняя имена полей, типы, enum статусы, даты и pagination. Live запрос из этой рабочей копии не выполнялся; бот/API не запускались.

Official schema retrieval was retried after receiving the screenshot. Direct official docs fetch still returns a redirect loop in the web reader; the official page opens in the in-app browser, but its full accessibility payload exceeds the browser bridge frame limit. No exact operation schema was recovered. The official Ozon API announcement remains the only available primary-source confirmation for the two beta read-only act endpoints. No production code or tests have been added because X00 acceptance criteria require the actual API contract before implementation.

## Пользователь прислал схему методов актов FBO

В pasted official documentation подтверждены `POST /v1/supply-order/act/summary/get` с `order_id` int64 и `POST /v1/supply-order/act/product/get` с `supply_id` int64. Продуктовый ответ содержит `supply_acts[].items[]`, `sku_info.sku` и количества `approved_quantity`, `declared_quantity`, `fact_quantity`, `unidentified_quantity`; сводка акта содержит `act_state`, `created_date`, `summary` и `supply_id`. Изменяющие `/v1/supply-order/act/accept` и `/accept/status` не вызываются.

Добавлен bot diagnostic helper для `product/get`: пользователь явно вводит `supply_id` из карточки; вызов выполняется один раз с ограниченными повторами и timeouts; output ограничен количеством и типами полей и не раскрывает идентификаторы/товарные атрибуты. Этот helper не выдаёт дату/статус и не заменяет будущий automatic supply collection. Focused test file `tests/test_experimental_supply_act_diagnostic.py`: **6 passed**. Остальные проверки и CI ожидают следующего связанного этапа.

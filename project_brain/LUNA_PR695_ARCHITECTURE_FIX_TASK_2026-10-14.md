# ТЗ для GPT Luna — исправления архитектурного review PR #695

Дата: 14.10.2026. Статус: **R1–R7 исправлены в рабочей ветке; локальный full pytest и targeted regression зелёные. Новый PR head, CI и повторный review — этап V08 в работе**.

## 1. Цель и исходный код

Исправить только подтверждённые R1–R7 калькулятора плановой юнит-экономики. Довести существующий PR #695 до повторного review. Согласованную формулу прибыли и налоговую модель сохранять.

- PR: https://github.com/dopf129-pixel/ai-business-assistant/pull/695
- Review SHA: `6d472145fe4586a5fe2a4da0e7b0b796900b8fac`.
- Ветка реализации: `codex/unit-price-calculator`.
- Review evidence: `project_brain/ARCHITECTURE_REVIEW_PR695_2026-10-14.md`.
- Исходное feature ТЗ: `project_brain/LUNA_UNIT_ECONOMICS_PRICE_CALCULATOR_TASK_2026-10-14.md`.

Начать с V00 и двигаться по зависимостям небольшими изменениями. После каждого этапа обновлять фактические статусы и результаты проверок. Новое бизнес-решение для перечисленных исправлений не требуется.

## 2. Ограничения

- Сохранять существующие локальные изменения, `data/users.json`, `data/tasks.json`, lock-файлы, базы, credentials и временные каталоги. Не добавлять их в Git и не использовать их в fixtures.
- Не делать `reset --hard`, широкие `restore/clean/stash` и не переписывать чужие коммиты. Если PR head изменился, прочитать новый diff и проверить, какие R ещё актуальны.
- Сохранить один калькулятор, действующий каталог и composition. Не создавать второе меню каталога, конкурирующий router/state framework или постоянное хранилище сценариев.
- Изменения калькулятора не должны записывать seller price, cost/history, tax policy, external expenses, finance facts или factual unit-economics results.
- Сохранить формулу: баллы уменьшают базу налога один раз; profit/margin используют существующий `TaxService` и согласованные inputs. NONE/USN и unknown не подменяются друг другом.
- Сохранить FBO limitation, ручные L/M/E, явный advertising=0, tenant-scoped weighted 28-day points source, budget 60 seconds / 64 actual HTTP attempts и bounded source cache.
- Сетевой read нельзя держать под общим runtime lock. После read требуется проверка актуальности перед публикацией.
- Не выполнять live Ozon calls, merge или production restart для проверки этих ошибок.

## 3. План и зависимости

`V00 → V01 → V02 → V03 → V04 → V05 → V06 → V07 → V08`.

V05 зависит от навигационной очистки V04: обработка текста активным калькулятором не должна перехватывать текст другого раздела. V06 математически независим, но выполняется после исправления стадий ввода.

### V00 — baseline и красные регрессии

1. Прочитать AGENTS, CURRENT_STATE, DECISIONS, TEST_MAP, исходное ТЗ и review.
2. Записать актуальные branch/head/base и `git status`, не выводя бизнес-содержимое файлов.
3. На review SHA существующие math/source/runtime modules дают 26 passed; полный CI Verify run `38604649833` success. Это baseline, а не доказательство исправления R1–R7.
4. Добавить meaningful regressions правильного поведения для случаев ниже и показать red на исходном коде. Использовать injected clocks, bounded `Event` waits и минимальные fake catalog/source. Не копировать пользовательские данные и не делать timing-based sleeps вместо управляемого interleaving.
5. Не фиксировать тесты, которые просто утверждают текущее ошибочное поведение. В частности `None` на результате, принятие старого store callback и generic numeric error должны быть failing expectations. Review подтвердил 8 случаев для 7 находок; R2 относится к обязательному concurrent runtime contract, текущий polling сериализует updates.

### V01 — R1: привязать выбор каталога к его происхождению

Точки: `AssistantButtonHandlerService._open_unit_economics_menu`, `handle`, runtime catalog-selection methods, существующий keyboard builder.

Требуемое поведение:

- Сохранить существующий SKU picker и обычный factual route. Для выбора калькулятора использовать callback с коротким opaque token, связанным с user, origin store, canonical product/SKU и id/version текущего выбора.
- Повторное открытие выбора инвалидирует старый выбор того же пользователя. Старая кнопка A не может потребить selection state B, даже когда offer id или SKU совпадают.
- Проверить owner/store/generation до catalog/source reads и до потребления токена. Неверный callback не должен уничтожать токен действующего другого пользователя.
- Не использовать `unit_economics:<offer_id>` как неявное подтверждение текущего calculator-selection mode. Legacy factual callback не меняет калькулятор.
- Callback data ≤64 UTF-8 bytes. Token storage ограничен по TTL/capacity.
- В calculator result/edit/assumptions показывать различимый магазин и товар/SKU, используя уже имеющуюся store identity; не раскрывать credentials.

Минимальные регрессии:

1. Calc picker A → picker B с одинаковым offer id → callback A: безопасный отказ и **0 reads для B**; действующая кнопка B работает.
2. Старый picker → новый picker в том же магазине → старый callback: новый режим не потреблён; новый callback работает.
3. Normal factual unit-economics menu/detail route сохранён; вход из карточки и каталога создаёт один и тот же тип сценария.

### V02 — R2: инвалидировать незавершённые операции

Точки: runtime `_start_product_selection`, `_refresh`, `clear_pending`, смена scope и callback entry methods.

Требуемое поведение:

- До source read выдать operation ticket/generation в runtime state. Новый товар, новый picker, выход, смена/отключение магазина инвалидируют прежний ticket, в том числе до создания первого scenario record.
- После source read проверить owner/store/SKU, ticket/generation, active identity/version и expiry под lock. Публиковать только актуальный результат; поздняя операция не восстанавливает закрытый сценарий и не заменяет новый.
- Проверку актуальности применять также к ошибочному refresh: он не должен возвращать рабочий старый экран после ухода пользователя.
- Same-scenario concurrent open/refresh дедуплицировать либо безопасно завершать вторую операцию. Не увеличить сетевой бюджет и не сериализовать всех пользователей общим сетевым lock.
- Сохранять manual overrides и использовать coherent копию входов/версии при render/refresh. Не итерировать изменяемый shared state без согласования с lock.

Регрессии с управляемым interleaving:

1. Заблокировать initial load → navigation/clear → release: late result не активируется, callback не редактирует старый сценарий.
2. Заблокировать A → закончить B → release A: B остаётся активным и его кнопки продолжают работать.
3. Slow refresh → новый товар/магазин/выход → success и failure variants: нет восстановления старого state.
4. Два refresh одной версии не смешивают snapshots/overrides, сетевые attempts остаются ограниченными.

### V03 — R3: не удалять ввод нового сценария при eviction старого

Точка: runtime `_evict_scenarios`.

- Удалять `_pending` только если его `scenario_id` относится к вытесненному record. Проверки для `_active` и pending должны согласованно учитывать id.
- Eviction неактивного A не меняет активный B того же user/store. Ограничение ёмкости остаётся действующим; решения не должны просто отключать eviction.
- Проверить TTL/eviction обработку без `KeyError` и без межпользовательского влияния.

Регрессия: capacity=2; u1 открывает A, затем B и начинает редактирование B; u2 открывает C и вытесняет A; текст u1 `600` принимается ровно в B, кнопки B соответствуют его новой версии. Тот же контракт проверить для завершённого/неактивного record одного пользователя.

### V04 — R6: очистить калькулятор до early-return навигации

Точки: существующая Telegram adapter/command boundary, `SellerCostTelegramAdapter`, `ReturnInventoryTelegramAdapter`, runtime lifecycle hook из V02.

- Вход в другой раздел должен очистить calculator pending и инвалидировать его незавершённые операции до того, как внешний adapter вернёт собственный ответ.
- Покрыть seller-cost menu/table/select/confirm, return-inventory menu, start/navigation и команды смены/отключения магазина.
- Использовать узкий hook в существующем composition/adapter boundary. Не вводить новый framework и не помещать формулы в adapters.
- Действующие callbacks текущего калькулятора и его scoped picker сохраняют свой сценарий.
- Существующие cost/date/whole-history confirmations и return-inventory confirmations сохраняют свои id/store checks и write rules.

Регрессии через реальные adapters и injected repositories/services:

1. Calc awaiting price → `seller_cost` menu → `600`: цена скрытого calc не меняется, callback старого calc отказан.
2. Calc awaiting price → явный новый cost draft/confirmation: текст и подтверждение принадлежат только cost flow; после его окончания старый calculator input не восстанавливается.
3. Calc → return inventory/store switch/disconnect: тот же отказ старому input/late load. Бизнес-записи возможны только по уже существующему явному подтверждению соответствующего flow.

### V05 — R4: явный текстовый stage результата

Точки: runtime `handle_text`, active-session lookup, handler/adapter integration.

- Если активный сценарий действует, но поле не выбрано, вернуть актуальный экран/кнопки и короткое предложение выбрать параметр. Обычный текст не меняет inputs и не выполняет source reads.
- Не отправлять повторный текст результата/параметров в общий ассистент. Кнопки должны использовать текущую версию.
- Если калькулятор закрыт или пользователь перешёл в другой раздел (V04), вернуть `None`/unhandled и разрешить обычный route.
- Истёкшее состояние обрабатывать явно, без предложения устаревших ставок как текущих.

Регрессии: после successful edit и на READY/assumptions/fee screen повторный текст получает свой working keyboard, scenario id/version/inputs неизменны, HTTP count не растёт. После navigation тот же текст не перехватывается калькулятором.

### V06 — R5: безопасная числовая валидация

Точки: `UnitPriceScenarioService._decimal`, normalization/arithmetic, runtime input formatter.

- Проверять техническую представимость money/rate inputs до арифметики и float-передачи в TaxService. Finite Decimal и ограниченная длина сами по себе недостаточны.
- Неподдерживаемая величина/экспонента/precision должна стать invalid input; `InvalidOperation`, overflow и нечисловой налоговый результат не должны превращать UI в generic error без кнопок.
- Не вводить произвольный коммерческий предел цены. Можно явно документировать техническую границу формата/представления; неизвестные источники остаются unknown.
- При отказе сохранить рабочий сценарий, pending field и клавиатуру отмены/повторного ввода. Последующий допустимый ввод работает.
- Result availability не может быть true при отсутствующих tax/profit/margin из-за арифметического отказа.

Регрессии:

1. `1e100` и длинное, но укладывающееся в text limit конечное число дают обычный invalid-input prompt с working keyboard, без записи значения.
2. Экстремальная положительная/отрицательная экспонента и переход в float не приводят к overflow/NaN/готовому пустому результату.
3. `600`, `600,50`, `1 200,50`, NBSP, явные C=0/a=0/b=0 и обычные дробные проценты работают; отрицательные/нулевые цены, bool/NaN/Infinity отвергаются.
4. Независимые контрольные P=500/600 остаются 186 ₽ / 37,20% и 258,20 ₽ / 43,03%. Разрешённый убыток при высокой себестоимости остаётся корректным.

### V07 — R7: разделить session inactivity и source freshness

Точки: runtime session lookup, snapshot metadata, render/comparison и refresh.

- Продолжение редактирования может продлить жизнь ручного сценария, но не срок актуальности source snapshot. Сохранить отдельное время успешной загрузки/истечения automatic sources; чтение/редактирование не обновляет это время.
- После source TTL явно предложить refresh; старую цену/ставку не называть текущей. Сохранить manual overrides и возможность сравнивать как явно обозначенные исторические допущения либо сделать current comparison unavailable до refresh.
- Не делать автоматический HTTP при каждом локальном пересчёте. Refresh остаётся отдельным ограниченным read и сохраняет пользовательские допущения.
- Указывать source period/as-of/freshness понятным образом. По завершении настоящего успешного refresh source age сбрасывается; failure не создаёт ложную свежесть.

Регрессии с injected clock: initial snapshot t=0, callbacks t=590 и t=1180 при TTL=600; старый source не становится свежим из-за callbacks, comparison не заявляет текущую цену, сеть не растёт. После успешного refresh источники свежие и overrides сохранены. Проверить также failure и переход календарной даты среднего баллов.

### V08 — приёмка, документация и повторный review

1. Запустить новые regressions и существующие calculator modules, production wiring, tax/tenant, seller-cost/return-inventory и связанные Telegram routes.
2. Выполнить обязательный полный `pytest` и compileall; получить Windows/Linux/Docker CI на новом PR head. Фиксировать точный SHA/run и фактические results, а не переносить прежние 3 119 passed как результат нового кода.
3. Обновить CHANGELOG, CURRENT_STATE, TEST_MAP, исходное ТЗ, этот документ и review acceptance table. В DECISIONS добавлять только реально принятое новое architectural decision; существующую Decision 045 сохранить.
4. В отчёте перечислить commit hashes/messages, files, architecture impact, сохранённые компоненты/данные, tests, docs и remaining limitations.
5. Перед слиянием пройти повторный review R1–R7 на exact new head. Не объявлять bugs закрытыми только по зелёному старому suite или только по mock happy path.

## 4. Критерий завершения

Все R1–R7 воспроизводятся как red на исходной ревизии и проходят как green после исправлений; существующие потребители сохранены; current-head full CI зелёный; документы содержат реальные результаты; повторный review подтверждает отсутствие открытых блокеров. Слияние/production запуск — отдельное действие после review.

## 5. Статус этапов

| Этап | Статус | Результаты |
|---|---|---|
| V00 | Завершён | Ветка `codex/unit-price-calculator`, baseline head `496f620`; данные пользователя уже изменены и исключены из тестовой копии/будущего коммита. Добавлены regressions с red evidence для R1–R7; старые 8 probes задокументированы в review. |
| V01 — R1 | Завершён | Picker callbacks — opaque token по user/store/generation/SKU; stale callback не читает каталог-источник и не расходует актуальный токен. Проверены магазин/повторное открытие, callback ≤64 bytes, factual маршрут сохранён. |
| V02 — R2 | Завершён | Operation ticket проверяется после чтения; late initial/older load и refresh success/failure не публикуют закрытый или старый сценарий. Управляемые `Event` interleavings включены в regression suite. |
| V03 — R3 | Завершён | Eviction чистит pending только для вытесненного `scenario_id`; тест подтверждает, что ввод активного сценария B сохраняется при вытеснении A. |
| V04 — R6 | Завершён | Очистка calculator state подключена до early-return Seller Cost/Return Inventory adapters, `/start` и store switch/disconnect command boundary. Старые callbacks и text stage после перехода не работают. |
| V05 — R4 | Завершён | Текст на READY-сценарии возвращает его актуальную клавиатуру без изменения inputs/version и без source reads; после навигации калькулятор текст не перехватывает. |
| V06 — R5 | Завершён | Decimal inputs ограничены документируемым техническим диапазоном до арифметики/float; некорректный налоговый результат закрывает итог и сохраняет клавиатуру повторного ввода. |
| V07 — R7 | Завершён | `source_loaded_at` отделён от sliding inactivity timestamp; старый snapshot скрывает comparison, а assumptions screen явно показывает source as-of и STALE. Успешный refresh обновляет freshness, ошибка оставляет STALE; ручные допущения сохранены. |
| V08 | В работе | Targeted tests **61 passed** на текущем коде. Полный suite **3 137 passed** и GitHub CI run `38615340159` относятся к предшествующему code commit `0e41263`; повторяются после последней правки stale assumptions label. Текущий exact-head CI и повторный review ещё не выполнены. |

### Фактические проверки перед публикацией нового PR head

- Целевой набор calculator/runtime/UI/routing: **61 passed in 2.70s** на рабочем дереве.
- Полный `pytest -q`: **3 137 passed in 18.57s** на копии текущего кода без `data/`, `.env` и пользовательского хранилища; sandbox ACL для Python-created temp/SQLite путей обойдён разрешённым запуском в изолированной копии. Assertions и тесты не менялись.
- `python -m compileall -q app tests`: завершился успешно; показал одну существующую `SyntaxWarning` в `tests/test_unit_economics_returns_impact_integrity_v971_v980.py:177` (`is not 0.0`).
- `git diff --check`: успешно. Локальные `data/tasks.json`, `data/users.json`, lock и старые temp-каталоги не добавлялись в изменения.
- Изменения пока не опубликованы; после push нужно зафиксировать exact head, GitHub CI runs и повторный review. До этого R1–R7 локально исправлены, но PR acceptance не завершена.

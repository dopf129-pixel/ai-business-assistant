# Архитектурный review PR #695 — 14.10.2026

## Вердикт и проверенная ревизия

**Повторный review 15.10.2026 на head `9185f65fa75ca0b7dc4d333cc362997209a5cd59` подтверждает R1–R10, но выявил один P2 R11: строка POSTING без разрешённого SKU молча исключается из среднего баллов, после чего неполная когорта считается подтверждённой. Слияние отложить до узкого исправления, regression, нового CI и повторной проверки.**

Актуальное ТЗ: `LUNA_PR695_DISCOUNT_IDENTITY_FIX_TASK_2026-10-15.md`. R10 и предыдущие результаты сохранены ниже как история; новое finding R11 описано в конце документа.

- PR: https://github.com/dopf129-pixel/ai-business-assistant/pull/695
- Head первичного review: `6d472145fe4586a5fe2a4da0e7b0b796900b8fac`.
- Base: `655b3a0c46acb258a5e884cccc8da6728a5216a7`.
- Ветка: `codex/unit-price-calculator`.
- GitHub Verify run `38604649833`: completed / success на этом head.
- Изучены все новые math/source/runtime/factory компоненты, изменения finance/handler/keyboard/composition и существующие внешние Telegram adapters, через которые проходит production-навигация.
- Первая приёмка исправлений в `LUNA_PR695_ARCHITECTURE_FIX_TASK_2026-10-14.md` проверила code SHA `3f4942b6c2e01238cabfd9fda7c274ab479bcba7`: 62 целевых теста, полный pytest 3 138 и GitHub Verify run `38616115735`. Дополнительная проверка текущего head выявила две межсервисные ошибки; её фактические результаты приведены в конце документа.

Разделение чистой математики, источников и временного Telegram-сценария соответствует архитектуре проекта. Замена архитектуры не требуется. Подтверждённые блокеры находятся в привязке callback, жизненном цикле сценария, маршрутизации текста и проверке числового ввода.

## Подтверждённые находки

| ID | Приоритет | Ошибка | Основная точка кода |
|---|---|---|---|
| R1 | P1 | Кнопка каталога старого магазина принимается как выбор товара нового магазина | `assistant_button_handler_service.py:1183`, `:4682`; runtime `:85` |
| R2 | P2 | При параллельных вызовах поздняя загрузка восстанавливает закрытый сценарий или заменяет более новый товар | runtime `:251–282` |
| R3 | P2 | Вытеснение неактивного сценария удаляет pending input другого активного сценария того же пользователя | runtime `:682–689` |
| R4 | P2 | Текст на действующем экране результата уходит в общий ассистент вместо возврата текущих кнопок | runtime `:152–169` |
| R5 | P2 | Короткое конечное число `1e100` вызывает `Decimal.InvalidOperation`; ответ теряет клавиатуру ввода | math service `:309–332`, runtime `:183–190` |
| R6 | P2 | Переход в раздел, обработанный внешним adapter, не очищает ввод калькулятора | handler `:535–555`; `SellerCostTelegramAdapter.handle_button` |
| R7 | P2 | Sliding session TTL позволяет бессрочно выдавать старый snapshot/current-price comparison как текущий | runtime `:609–627`, `:452–458` |

Номера строк относятся к проверенному head. Все семь проблем воспроизведены без Ozon-запросов и без записи бизнес-данных.

### R1 — каталог не привязан к источнику кнопки

Калькулятор использует `unit_economics:<offer_id>`. В callback нет opaque token, owner/store, id выбора или версии. `has_catalog_selection` проверяет только наличие режима выбора для текущего магазина. Затем `handle_catalog_selection` потребляет текущий режим и разрешает переданный offer id уже в текущем каталоге.

Воспроизведение через `AssistantButtonHandlerService`:

1. Открыть калькулятор магазина A, сохранить callback товара `item-1`.
2. Переключить tenant на магазин B и открыть новый выбор калькулятора. В B тоже есть offer id `item-1`, но это SKU `sku-B-1`.
3. Нажать сохранённую кнопку A.

Фактический результат probe:

```json
{"same_callback_in_two_stores": true,
 "old_callback": "unit_economics:item-1",
 "accepted_status": "UNIT_PRICE_SCENARIO_READY",
 "result_store": "B", "result_sku": "sku-B-1",
 "reads": [["u1::ozon::B", "sku-B-1"]]}
```

Следовательно, старая кнопка A выполняет чтение для B. Текст результата `Магазин: активный` не позволяет отличить магазины. Тот же callback не различает старый и новый выбор внутри одного магазина. Это нарушает требования исходного ТЗ к origin store и версии до любого чтения данных.

Нужно сохранить существующий picker, но привязать выбор калькулятора к короткому scoped token и текущему id/generation выбора. Обычные callbacks фактической юнит-экономики не должны потреблять режим калькулятора.

### R2 — публикация результата загрузки без проверки жизненного цикла

`_start_product_selection` очищает старое состояние, выполняет source read вне lock, затем без проверки generation создаёт и активирует новый сценарий. `clear_pending` удаляет существующие записи, но не инвалидирует незавершённые загрузки.

Подтверждены два interleaving с `Event` и ограниченным ожиданием в source stub:

1. Загрузка товара A приостановлена; вызывается `clear_pending(user)`; загрузка заканчивается. Поздний ответ имеет `UNIT_PRICE_SCENARIO_READY`, а его кнопка редактирования принимается как `UNIT_PRICE_SCENARIO_INPUT_PENDING`. Закрытый сценарий восстановлен.
2. Загрузка товара A приостановлена; более новый выбор товара B успевает завершиться; затем заканчивается A. Кнопка уже показанного B возвращает `UNIT_PRICE_SCENARIO_STALE`: поздний A заменил B в `_active`.

Probe второго случая:

```json
{"newer_sku": "sku-other", "late_sku": "3921245627",
 "newer_button_after_late_load": "UNIT_PRICE_SCENARIO_STALE"}
```

Область риска: текущий polling `build_application` имеет `max_concurrent_updates=1` (отдельно проверено созданием application с fake token без network). Поэтому обычные updates в нынешней configuration сериализованы; наличие `asyncio.to_thread` само по себе не доказывает их перекрытие. Однако исходное ТЗ явно требует устойчивости runtime к concurrent open/refresh, и параллельный контракт не выполняется. Приоритет этой находки — P2. Нужен operation ticket/generation, выданный до чтения и проверяемый при публикации. Выход, смена магазина и новый выбор должны инвалидировать незавершённые операции даже тогда, когда сценарий ещё не был создан. Аналогичная проверка нужна для успешного и ошибочного позднего refresh.

### R3 — вытеснение чистит pending по user/store, а не по scenario id

`_deactivate` оставляет неактивные сценарии в bounded `_scenarios`. `_evict_scenarios` правильно проверяет scenario id перед удалением `_active`, но безусловно удаляет `_pending` по тому же user/store key.

Воспроизведение с `max_scenarios=2`:

1. Пользователь u1 открывает A, затем B в одном магазине. A неактивен, B активен.
2. u1 начинает редактировать цену B.
3. Другой пользователь u2 открывает C. Из bounded cache вытесняется A.
4. u1 отправляет `600`.

Фактический результат:

```json
{"text_result_after_other_user_eviction": null,
 "active_scenario_is_second": true}
```

Ввод B потерян, хотя B остаётся активным. Для default capacity 128 ошибка возникает тем же способом при заполнении лимита. Pending можно удалять только если его `scenario_id` совпадает с вытесняемым сценарием.

### R4 — действующий результат не владеет повторным текстом

Если `_pending` отсутствует и нет старого scope, `handle_text` возвращает `None` даже при наличии действующего `_active`. `AssistantTelegramAdapter` после этого продолжает обычную обработку сообщения ассистентом.

Probe: открыть полностью заполненный сценарий, находясь на его результате отправить `600` через handler. Получено `null`, при исходном status `UNIT_PRICE_SCENARIO_READY`.

Исходное ТЗ (§9) требует вернуть действующие кнопки своей версии при повторе текста на результате/параметрах. Нужен явный stage contract: обычный текст не меняет параметр без выбора поля; действующий сценарий возвращает свой экран/кнопки. Если пользователь действительно вышел из калькулятора, обработка текста должна вернуться другим маршрутам.

### R5 — проверка finite не гарантирует допустимость расчёта

`_decimal` принимает `1e100` как конечный Decimal длиной меньше 64. `_money_decimal` затем вызывает `quantize(0.01)` в стандартном Decimal context и получает `InvalidOperation`. Общий handler ловит исключение и выдаёт `UNIT_PRICE_SCENARIO_TEXT_FAILED` без input keyboard.

Probe через настоящий handler:

```json
{"input": "1e100", "failure_code": "UNIT_PRICE_SCENARIO_TEXT_FAILED",
 "keyboard_returned": false, "normal_retry_status": "UNIT_PRICE_SCENARIO_READY"}
```

Корректный последующий ввод `600` обрабатывается, но пользователь лишён кнопки отмены/возврата в ответе ошибки. Нужна техническая проверка представимости и арифметических границ всех money/rate inputs; неподдерживаемое число должно стать обычным invalid input с сохранением сценария и клавиатуры. Не требуется выбирать новый бизнес-лимит цены.

### R6 — очистка нового flow находится ниже production adapters

Новый `_clear_unit_price_input_for_new_flow` вызывается только внутри `AssistantButtonHandlerService.handle`. `SellerCostTelegramAdapter` и `ReturnInventoryTelegramAdapter` могут закончить callback раньше и не передать его этому handler.

Воспроизведение с настоящими `SellerCostTelegramAdapter` и `TelegramSellerCostUpdateService`, injected catalog/cost stubs:

1. Открыть калькулятор и начать ввод цены.
2. Через adapter нажать `seller_cost`; показан реальный cost menu.
3. Не выбирая товар cost flow, отправить `600`.

Получено:

```json
{"opened_seller_cost_menu": {"configured": 0, "total": 1, "missing": 1},
 "next_text_status": "UNIT_PRICE_SCENARIO_INPUT_REQUIRED",
 "old_calculator_price_after_text": 600.0}
```

Следовательно, текст нового раздела изменяет скрытый предыдущий сценарий. Очистку/инвалидацию необходимо выполнить на существующей границе Telegram-навигации до early returns внешних adapters. Проверить также return inventory и команды смены/отключения магазина. Новый framework или второй router для этого не нужен.

### R7 — возраст источника подменяется возрастом последнего взаимодействия

`_get_session` проверяет время с `updated_at`, затем обновляет его при каждом callback. Возраст самого source snapshot не проверяется. Достаточно открывать экран чаще 600 секунд, чтобы старые source price/commission/points сохранялись бессрочно; comparison продолжает называться «При текущей цене».

Воспроизведение с injected monotonic clock: snapshot создан в t=0; открытие результата в t=590 и t=1180. Source read выполнен только один раз.

```json
{"snapshot_age_seconds": 1180.0, "ttl_seconds": 600,
 "source_read_count": 1, "status": "UNIT_PRICE_SCENARIO_READY",
 "comparison_available": true, "last_interaction_age_seconds": 0.0}
```

Исходное ТЗ (§9) требует после TTL предложить новый snapshot и не выдавать старые ставки за актуальные. Runtime inactivity TTL и source freshness — разные проверки. Ручные допущения можно сохранять, но просроченные автоматические данные/сравнение нужно явно маркировать историческими или предложить refresh до заявления о текущей цене. Не требуется HTTP при каждом локальном пересчёте.

## Что подтверждено положительно

- Контрольные обычные сценарии P=500/600 соответствуют согласованной формуле: 186 ₽ / 37,20% и 258,20 ₽ / 43,03% соответственно.
- Баллы уменьшают налоговую базу один раз; pure math делегирует налог существующему `TaxService`.
- Snapshot/source cache имеет tenant/user/SKU key и lock; текущая source factory использует request-local finance cache. Нет оснований менять согласованную формулу или подменять неизвестные расходы нулями.
- Ручные изменения ограничены временным сценарием. FBO assumption обозначена; FBS по FBO-тарифу не рассчитывается.

## Проверки и пределы review

- Проверенный код совпадает с PR head `6d472145...`; локальные production files не менялись.
- GitHub Verify `38604649833`: success. Существующий full suite на этом SHA — 3 119 tests; Windows/Linux/Docker checks зелёные.
- Дополнительный targeted pytest трёх scenario modules: **26 passed in 1.38s**.
- Отдельные изолированные probes подтвердили **8 случаев для 7 находок** (два случая R2). Они выполнялись с минимальными фальшивыми каталогами/source, injected clocks и `Event`-interleavings; бизнес-записей, сетевых Ozon calls и пользовательских выгрузок не было.
- Probes проверяли наблюдаемое ошибочное поведение и не добавлялись как зелёные regression tests в CI. Исполнитель исправлений должен добавить тесты ожидаемого правильного поведения: red на review SHA, green после исправления.
- Full pytest повторно в рамках review не запускался: код не менялся, exact-SHA CI уже подтверждён. Наличие зелёного CI не покрывает найденные отсутствующие сценарии.

## ТЗ и отчёт по репозиторию

ТЗ: `project_brain/LUNA_PR695_ARCHITECTURE_FIX_TASK_2026-10-14.md`.

- Change summary: review ветки `codex/unit-price-calculator`, code commit `6d47214` (`Record unit price calculator CI acceptance`). Новый кодовый коммит в рамках review не создан.
- Files changed: добавлены этот review и ТЗ; обновлены review status в CHANGELOG/CURRENT_STATE/TEST_MAP и исходном ТЗ. Production code/tests не изменены; файлов не удалено.
- Architecture impact самого review: **No architectural impact**. Классификация реализации PR: **Architecture Review Required**, review не пройден до закрытия R1–R7.
- Preserved components: формулы, source/API/DB contracts, factual unit economics/Period Profit и пользовательские runtime-данные сохранены.
- Testing: 26 existing targeted tests passed; 8 isolated defect probes подтверждены; exact-SHA CI success прочитан с GitHub.
- Documentation: CHANGELOG, CURRENT_STATE, TEST_MAP и исходное calculator task обновлены. DECISIONS не изменён: новые архитектурные решения не приняты.
- Next recommended step: выполнить V00–V08 из исправляющего ТЗ, получить зелёный CI нового head и пройти повторный review перед слиянием.

## История: первая повторная приёмка исправлений — 14.10.2026

Проверен code-bearing PR head `3f4942b6c2e01238cabfd9fda7c274ab479bcba7` в ветке `codex/unit-price-calculator`. GitHub Verify run `38616115735` завершился успешно: `windows-verification` и `full-verification` success; последний включает Linux full suite, production Docker build и runtime smoke. Локально целевой набор — **62 passed**, полный pytest в изолированной копии — **3 138 passed**.

| Finding | Повторная проверка |
|---|---|
| R1 — callback старого каталога/магазина | Закрыт opaque token с user/store/generation binding; stale callback не выполняет source read. |
| R2 — late initial/refresh и конкурентный выбор | Закрыт атомарным созданием operation ticket при consume picker callback и проверками ticket/active/version после read; interleavings покрыты `Event` tests. |
| R3 — eviction очищает чужой pending | Закрыт связью pending с `scenario_id`; активный сценарий сохраняет ввод при eviction другого. |
| R4 — текст на экране результата | Закрыт возвратом собственного calculator result/keyboard без изменения inputs/version и без source read. |
| R5 — экстремальная Decimal величина/ошибка налога | Закрыт technical input bounds и fail-closed итогом с рабочей клавиатурой повторного ввода. |
| R6 — навигация через early-return adapters | Закрыт очисткой calculator state до Seller Cost/Return Inventory handlers и store switch/disconnect. |
| R7 — возраст source snapshot | Закрыт независимым `source_loaded_at`; stale comparison скрыт, экран допущений показывает as-of/stale; только успешный refresh обновляет freshness. |

Во время повторного просмотра до финального CI выявлены и закрыты два недопокрытых края R2/R7: stale-маркировка экрана допущений и race между consume picker callback и source ticket creation. Оба изменения находятся в проверенном SHA и покрыты regressions. **Нерешённых блокеров по R1–R7 не осталось.** Merge/deploy не выполнялись; PR остаётся открыт для слияния другой моделью.

## Дополнительный повторный review текущего PR head — 14.10.2026

Проверенный PR head: `73c4c74cf786f0a8a38168a27a3a61240d07ce06`, base `655b3a0c46acb258a5e884cccc8da6728a5216a7`. Код совпадает с code SHA `3f4942b6`; более новый commit меняет только документацию. PR открыт. GitHub checks на текущем head: Windows и Linux full verification success, Verify run `38617595326`; Docker build/runtime smoke прошли. Этот зелёный CI не покрывает два случая ниже.

Повторно прочитаны math/source/runtime, scoped picker и lifecycle fixes, реальные Telegram adapter/command boundaries, source factory, Decision 045 и regressions. Существующие четыре calculator test modules повторно выполнены: **45 passed in 1.80s**. R1–R6 по проверенным сценариям закрыты. Для R7 исходная ошибка sliding activity исправлена, но граница source cache → runtime сохраняет ложную свежесть. Дополнительно R5 precision hardening нарушил нормальный автоматический источник баллов.

### R8 — P2: подтверждённое дробное среднее баллов блокирует расчёт

Точки: `unit_price_scenario_source.py:364–366` и `unit_price_scenario_service.py:349–358` на проверенном code SHA.

Источник рассчитывает weighted rate в Decimal и передаёт строку без ограничения точности. Обычная полная выборка sale=300 ₽, bonus=50 ₽ даёт `16.66666666666666666666666667`. Новая общая проверка `MAX_INPUT_DIGITS=15` отклоняет такую корректную ставку. После заполнения ручных L/M/E и рекламы калькулятор остаётся INPUT_REQUIRED; кнопка восстановления среднего возвращает то же недопустимое значение.

Probe использует настоящие `UnitPriceScenarioSource`, `UnitPriceScenarioService`, `TaxService`, runtime и keyboard, с искусственным полным 28-дневным finance evidence. Ввод остальных полей проходит через публичные callback/text методы. Получено:

```json
{"source_complete": true, "auto_rate": "16.66666666666666666666666667", "available": false, "invalid_inputs": ["discount_points_rate"]}
```

Требуется согласовать безопасную точность автоматической ставки с математическим контрактом, сохранив weighted formula, защиту extreme inputs и fail-closed для неполных данных. Регрессия должна пересечь source → math → runtime; отдельные source tests с целочисленной средней долей этого не проверяют.

### R9 — P2: новый сценарий омолаживает уже закэшированный источник

Точки: runtime `:348`, `:634–659`; source `:77–86` на проверенном code SHA.

`UnitPriceScenarioSource.load_snapshot` честно возвращает cache hit и `age_seconds`, но runtime записывает `source_loaded_at=self.clock()` при каждом открытии сценария. Возраст существующего снимка теряется. Воспроизведение: загрузить source в t=0; открыть новый сценарий с cache hit в t=590; показать результат в t=610. Источнику уже 610 секунд при TTL=600, но runtime сообщает возраст 20 и продолжает current-price comparison:

```json
{"cache_age_at_open": 590, "actual_snapshot_age": 610, "runtime_freshness": {"status": "FRESH", "age_seconds": 20, "ttl_seconds": 600}, "comparison_available": true, "underlying_source_reads": 1, "source_as_of_unchanged": true}
```

Нужно сохранить исходный возраст источника при передаче cache hit в новый runtime scenario; открытие, локальный ввод и восстановление среднего не должны сбрасывать его. Source age должен быть одинаковым на результате и экране допущений. Настоящий успешный refresh может обновить возраст; ошибка refresh — нет.

### Проверки, ограничения и итог

- Два дополнительных изолированных pytest probes с assertions правильного поведения — **2 failed in 0.34s**, ожидаемое red evidence R8/R9. Они лежат в ignored scratch `.codex-test-pr695-repeat-review/probes.py`, не добавлены в production/default suite и не используют live API, credentials, пользовательские товары или storage.
- Четыре текущих calculator modules — **45 passed**. Полный pytest повторно не запускался: production code не менялся, full CI проверенного head уже success. После R8/R9 требуется новый full suite и CI нового кода.
- Сохранены пользовательские локальные изменения и данные. Review меняет только документы; merge/deploy не выполнялись.
- **Слияние пока не рекомендуется.** Исправить R8/R9 по отдельному ТЗ, добавить meaningful regressions, получить зелёный CI нового code SHA и повторить review. Бизнес-решение для этих технических исправлений не требуется.

## Отчёт дополнительной проверки

1. **Change Summary:** ветка `codex/unit-price-calculator`; проверенный commit `73c4c74` — `Document PR 695 final CI and review`. На его неизменённом коде проведён дополнительный review; итог — два подтверждённых P2. Новый документационный commit публикует этот вывод и ТЗ, его SHA приведён в итоговом сообщении.
2. **Files Changed:** добавлен `LUNA_PR695_REPEAT_REVIEW_FIX_TASK_2026-10-14.md` — порядок исправлений W00–W03 и acceptance regressions. Изменены этот review, CHANGELOG, CURRENT_STATE, TEST_MAP, исходное feature ТЗ и предыдущий corrective task — текущий статус исправлен, история сохранена. Удалённых файлов нет; production files не менялись.
3. **Architecture Impact:** No architectural impact для этой проверки; новые service/layer/dependency и API/DB contracts не вводились. Будущие R8/R9 должны уточнить существующие numeric/freshness contracts без нового слоя.
4. **Preserved Components:** math formula, TaxService, source budgets/cache isolation, picker/tickets и существующие Telegram flows. Пользовательские data/users.json и data/tasks.json и локальные временные файлы не редактировались и не включаются в commit.
5. **Testing:** production test suite не расширялся в review. Четыре calculator modules выполнены повторно — 45 passed; два scratch probes правильного поведения — 2 failed, red evidence новых ошибок. Полный pytest локально не повторён из-за отсутствия изменений кода; exact-head Windows/Linux full CI `38617595326` success проверен. После исправлений требуется новый полный прогон.
6. **Documentation Updates:** CHANGELOG описывает findings; CURRENT_STATE отмечает открытые blockers; TEST_MAP показывает coverage gaps и фактические результаты; DECISIONS не менялся, Decision 045 сохранён. Review и обе прежние задачи ссылаются на новое ТЗ.
7. **Review Classification:** Architecture Review Required для PR #695; дополнительная проверка требует R8/R9 перед слиянием. Новых blockers R1–R6 не подтверждено, R7 имеет остаточный cache-hit дефект.
8. **Next Recommended Step:** выполнить W00–W03 нового ТЗ, получить зелёный CI исправленного code SHA и повторный review. Слияние выполнит другая модель после приёмки; reviewer не начинает implementation или merge автоматически.

## Статус исправлений R8/R9 — 2026-10-14

- R8: rates используют отдельный precision limit в 28 significant digits (Decimal context); денежные inputs сохраняют прежний 15-digit limit, диапазон процентной ставки остаётся 0–100. Production source → math → runtime regression подтверждает полный расчёт для 50/300: налог 25 ₽, прибыль 280 ₽, маржа 56%. Manual override переживает refresh; восстановление принимает новое среднее 1/7.
- R9: snapshot cache `age_seconds` и `ttl_seconds` переносятся в transient runtime session. Текущая свежесть — cached age + монотонное elapsed; result/assumptions используют одно состояние. Источник истекает на `age >= TTL`, как и reuse в source. Regression доказывает t=0 → t=590 cache hit → t=600/610 stale, один source read, недоступное сравнение и предупреждение; успешный refresh обновляет данные, не теряя ручные значения.
- Red evidence до исправления: обе новые штатные regressions падали; после исправления calculator/source/math/runtime набор — **48 passed**.
- Полный isolated Windows pytest — **3 141 passed in 24.54s**. Compileall завершился с одной существующей SyntaxWarning в `tests/test_unit_economics_returns_impact_integrity_v971_v980.py:177`.
- GitHub Verify run **38621277605** на exact code SHA `9ed3e2d9bee334b54b874f63493f69dc4197d15f` completed/success: Windows and Linux full suite, compile, production Docker build/runtime smoke. Финальный review diff подтвердил исправление R8/R9 без новых блокеров. Merge не выполнялся.

## R10 — P2: недопустимая стоимость из источника ломает показ результата

Повторная проверка: head `060b0e6e57e3fc5e3ba28c42d90a4adcd4f03f6d`, production code `9ed3e2d`; Verify `38621806447` success. Новый вывод уточняет предыдущее заключение без blockers, не переоткрывая R8/R9.

- `TelegramSellerCostUpdateService._cost` и `SellerCostTableService._cost` принимают `1e100` как конечную положительную сумму. Fake getter сохранённой стоимости возвращает её через реальный `UnitPriceScenarioSource`; никаких storage/API writes в probe нет.
- Math service признаёт сумму invalid, но `_format_result` (строка 759) всё равно передаёт raw `session.inputs.cost` в `_money`. На строке 1034 `number.quantize(Decimal("0.01"))` выбрасывает `decimal.InvalidOperation`.
- Публичный picker → callback через `AssistantButtonHandlerService` возвращает `UNIT_PRICE_SCENARIO_CALLBACK_FAILED`, без keyboard и price_scenario. Следующий текст — `UNIT_PRICE_SCENARIO_TEXT_FAILED`, также без keyboard. Вместо предусмотренного ручного исправления сценария пользователь теряет экран калькулятора.
- Это остаточный путь R5 на входе source → presentation. Требуется безопасный formatter/source normalization по существующим техническим ограничениям, не изменение бизнес-формулы, TaxService или сохранённой стоимости.

Existing calculator modules повторены: **48 passed in 1.16s**. Изолированное воспроизведение expected input-required screen падает с указанным traceback. Full pytest локально повторно не запускался: production code в этом review не менялся, exact-head Windows/Linux/Docker CI зелёный; новый случай штатным suite не покрыт.

### Отчёт повторного review

1. **Change Summary:** review ветки `codex/unit-price-calculator` на `060b0e6` (`Record PR 695 R8-R9 verification results`). Закрытие R8/R9 подтверждено; один новый P2 R10 требует исправления. Review меняет только документы.
2. **Files Changed:** добавлен `LUNA_PR695_SOURCE_FORMATTING_FIX_TASK_2026-10-14.md`; обновлены этот review, CHANGELOG, CURRENT_STATE, TEST_MAP и статусы трёх предыдущих задач. Удалённых файлов нет.
3. **Architecture Impact:** No architectural impact этого review. Для исправления ожидается узкое уточнение existing validation/presentation contract, без нового слоя или API/DB contracts.
4. **Preserved Components:** production code, math/TaxService, source cache/budget, transient state, picker/tickets, пользовательские data/DB и локальные runtime artifacts не изменены.
5. **Testing:** targeted existing suite — 48 passed; isolated source→runtime/handler probe подтверждает R10. Exact reviewed SHA CI success; full local suite не повторялся без изменений кода.
6. **Documentation Updates:** статусы и evidence исправлены; DECISIONS не менялся, Decision 045 сохранён.
7. **Review Classification:** Architecture Review Required для PR; merge отложить до R10 regression/fix/new CI и повторной проверки.
8. **Next Recommended Step:** выполнить X00–X03 нового ТЗ. Реализация не начата в рамках запроса исходного review; этот вывод исторический и дополнен итоговой приёмкой ниже.

## Финальный repeat review после исправления R10 — 14.10.2026

Проверенный PR head: `2207ec86ec96012f7911706429fdc1b4dfacde23`; code-bearing commit `872f26a2ae500d179ad4e06a812e1d24ea4512b0`; base `655b3a0c46acb258a5e884cccc8da6728a5216a7`. PR #695 открыт, не слит.

### Review результата

- Source normalizes seller price и сохранённую себестоимость в том же техническом диапазоне, что и calculator money inputs. Значения вне диапазона не становятся нулём: они становятся unknown, provenance неизвестен, source completeness false; `cost_as_of` не выставляется для отклонённой стоимости.
- `_money` и `_percent` fail closed до `Decimal.quantize` и ловят formatting arithmetic errors. `_format_result` и `_edit_prompt` поэтому сохраняют обычный экран и клавиатуру ручного исправления даже для raw unsupported value.
- Реальные source → math → runtime → public handler regressions покрывают stored cost `1e100`, seller price `1e100`, input-required screen, безопасный result/edit rendering, manual correction и расчёт прибыли 280 ₽. Фейковое сохранённое значение после ручного исправления остаётся `1e100`; production storage не вызывается.
- Изменены только нормализация source money и presentation. Бизнес-формула, TaxService, хранение себестоимости, source cache/age, callbacks/tickets, tenant/SKU isolation и операции Ozon не изменены. Повторное выполнение существующих R1–R9 tests входит в полный зелёный suite.
- Открытых blockers R10 не найдено. Для R10 — **No architectural impact**: новый layer, dependency, API/DB contract не вводились. Классификация всего PR остаётся **Architecture Review Required** из-за состава реализуемого калькулятора; этот repeat review не заменяет решение о слиянии.

### Проверки

- Два интеграционных R10 tests дали expected red до фикса: публичный picker возвращал `UNIT_PRICE_SCENARIO_CALLBACK_FAILED` без keyboard.
- После фикса calculator/source/math/runtime/architecture/UI/request-bound-tax-policy набора: **59 passed in 1.51s**.
- Полный изолированный Windows pytest без seller data/.env: **3 144 passed in 16.17s**. Два production-tax-policy tests использовали синтетическую test-only конфигурацию; пользовательские JSON/credentials не копировались.
- `compileall -q app tests` и `git diff --check` успешны; остаётся одна прежняя SyntaxWarning в returns-impact test.
- GitHub Verify runs **38634572358** и **38634565693** на точном head `2207ec86...` — Windows и Linux full suites, compile, Docker image build и runtime smoke успешны.

### Отчёт повторной приёмки

1. **Change Summary:** ветка `codex/unit-price-calculator`; code commit `872f26a` (`Fix unsupported unit price scenario sources`), docs commit `2207ec8` (`Record R10 isolated verification results`). R10 исправлен, результат не падает при отображении неподдерживаемых source money.
2. **Files Changed:** R10 код и regressions находятся в commits `872f26a` и `2207ec8`; финальный review обновляет review/status artifacts. Пользовательские `data/tasks.json`, `data/users.json`, lock/temp данные исключены из кодовых коммитов.
3. **Architecture Impact:** no new layer, service, dependency или contract. Расширен только validation/presentation boundary существующих source/runtime.
4. **Preserved Components:** формула калькулятора, TaxService, cost persistence, callbacks/tickets, freshness/cache budgets, tenant isolation, Decision 045 и factual finance workflows.
5. **Testing:** 59 targeted passed; isolated Windows suite 3 144 passed; exact-head Windows/Linux/Docker CI runs выше success; compileall и diff check passed.
6. **Documentation Updates:** CHANGELOG, CURRENT_STATE, TEST_MAP, feature task, R10 task и этот review обновлены. DECISIONS не менялся; нового архитектурного решения нет.
7. **Review Classification:** Architecture Review Required для PR #695; финальный repeat review не нашёл открытых технических blockers.
8. **Next Recommended Step:** PR открыт для решения о слиянии другой моделью; этим чатом слияние не выполнялось.

## Дополнительный review 15.10.2026 — R11, P2

Проверенный head `9185f65fa75ca0b7dc4d333cc362997209a5cd59`; base `655b3a0c46acb258a5e884cccc8da6728a5216a7`. Production code после R10 не менялся. Verify runs `38635120280` и `38635112065` на этом SHA — success, Windows/Linux/Docker. Review threads GitHub пусты; PR открыт, не слит.

### Неизвестный SKU ошибочно равен известному другому товару

Точка: `app/services/finance_service.py:532–534`, новый метод `get_daily_discount_points_evidence`.

`str(product.get("sku") or "").strip()` превращает отсутствующую/null/пустую/пробельную identity в пустую строку. Следующий `if product_sku != target_sku: continue` исключает её без увеличения `malformed`. Поэтому `complete = malformed == 0 and conflicts == 0` объявляет день полным, а source уже не может применить свою защиту `FINANCE_DISCOUNT_POINTS_IDENTITY_UNRESOLVED`: строки нет в records.

Изолированная проверка использует реальный FinanceService evidence и UnitPriceScenarioSource с fake raw daily responses за 28 дат. В одном дне известная продажа выбранного SKU составляет 100 ₽/20 баллов; ещё одна положительная строка 900 ₽/0 баллов не содержит разрешённого SKU. Получено:

```json
{"daily_complete": true, "malformed_record_count": 0, "record_count": 1, "auto_rate": "20", "period_complete": true, "days_loaded": 28}
```

Принадлежность второй строки неизвестна; подтверждать среднее по оставшемуся подмножеству нельзя. Исходный feature contract §6 требует unavailable при неразрешённом SKU. Это условный дефект обработки неполного ответа, а не утверждение о наличии таких строк в live Ozon данных пользователя. Нужно различать явно другой непустой SKU и отсутствие identity; второй случай должен делать evidence incomplete и сохранять ручной fallback.

### Проверки и решение

- Пять существующих calculator/source/math/runtime/review modules повторены: **51 passed in 1.53s**.
- Изолированные assertions ожидаемого unknown для `None`, `""`, `"   "` дали **3 failed in 0.28s**. Probe находится вне репозитория в `pr695-r11-review-20261015/test_unresolved_identity_probe.py` в разрешённой папке визуализаций; live API, credentials и business storage не использовались.
- Full pytest локально повторно не запускался: production code не менялся, full CI reviewed SHA уже зелёный. Эти существующие проверки не покрывают R11; после исправления требуется новый full suite и CI.
- **Требуется исправить R11 перед слиянием.** Создано отдельное ТЗ Y00–Y03. R1–R10 не переоткрыты.

### Отчёт review

1. **Change Summary:** review ветки `codex/unit-price-calculator` на `9185f65` (`Record R10 CI and repeat review acceptance`); найден один P2. Новый commit содержит только evidence/документы, SHA указывается в итоговом сообщении.
2. **Files Changed:** добавлено corrective ТЗ R11; обновлены review, CHANGELOG, CURRENT_STATE, TEST_MAP и статус feature ТЗ. Production files и штатные tests не менялись; удалений нет.
3. **Architecture Impact:** No architectural impact для review; будущая правка должна уточнить существующую evidence validation без нового service/layer/API/DB contract.
4. **Preserved Components:** формула, TaxService, cost storage, tenant/callback isolation, source budgets/freshness и пользовательские JSON/locks/temp сохранены.
5. **Testing:** 51 existing tests passed; 3 expected-red isolated cases; exact reviewed SHA CI success. Full local run не повторён без изменений production code.
6. **Documentation Updates:** CHANGELOG/CURRENT_STATE/TEST_MAP и review/feature task отражают R11; DECISIONS не менялся.
7. **Review Classification:** Architecture Review Required для PR #695; один P2 блокирует приёмку текущей реализации.
8. **Next Recommended Step:** выполнить Y00–Y03, получить новый зелёный CI и повторный review; слияние выполнит другая модель.

## Локальная повторная проверка R11 после исправления — 15.10.2026

- В `FinanceService.get_daily_discount_points_evidence` неизвестный/пустой SKU теперь учитывается как malformed до сравнения с target SKU. Явный другой SKU по-прежнему исключается из когорты; его недостающий bonus не делает evidence выбранного товара неполным.
- Штатные regressions покрывают absent/null/empty/whitespace identity и контрольный другой SKU. Сквозной тест проходит через raw fake FinanceService, настоящий weighted source, math/runtime и public handler: неполный cohort оставляет auto-b unknown, а ручное допущение восстанавливает расчёт.
- Целевые шесть модулей: **63 passed in 1.32s**; `compileall -q app tests` и `git diff --check` прошли. Изменение не затрагивает формулы, финансовые итоги, TaxService, cache, tenant/callback contracts или хранилище.
- Предварительная оценка: локально R11 исправлен, новых архитектурных проблем в узком diff не выявлено. Финальная приёмка зависит от полного Windows/Linux/Docker CI и review опубликованного SHA; до них merge blocker остаётся открытым. R1–R10 этим изменением не переоткрываются.

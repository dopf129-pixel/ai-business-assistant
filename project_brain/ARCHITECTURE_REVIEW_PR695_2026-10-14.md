# Архитектурный review PR #695 — 14.10.2026

## Вердикт и проверенная ревизия

**Не сливать PR до исправления R1–R7 и повторной проверки нового SHA.**

- PR: https://github.com/dopf129-pixel/ai-business-assistant/pull/695
- Проверенный head: `6d472145fe4586a5fe2a4da0e7b0b796900b8fac`.
- Base: `655b3a0c46acb258a5e884cccc8da6728a5216a7`.
- Ветка: `codex/unit-price-calculator`.
- GitHub Verify run `38604649833`: completed / success на этом head.
- Изучены все новые math/source/runtime/factory компоненты, изменения finance/handler/keyboard/composition и существующие внешние Telegram adapters, через которые проходит production-навигация.

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

# ТЗ для GPT Luna: партия по правилу отправок SKU, без ручного подсчёта всех поставок

Дата: 13.11.2026. Статус: спецификация; реализация НЕ выполнена.
Исходный main: 7965dcddffa50bd4e0f175cd18c32929b6a845d0, PR #728–#732 слиты.
Исполнитель: GPT Luna. Этапы FB00–FB31, три зависимых implementation PR.

## 1. Результат и границы задания

Владелец вводит позднюю себестоимость партии. Мастер требует вручную посчитать все отправленные единицы, хотя отправки продолжаются. Старого товара дома и в отдельном транзите перед первой отправкой новой партии уже не осталось.

Реализовать:

1. Однократное подтверждение владельцем правила для магазина и SKU: начиная с согласованной границы все последующие поставки относятся к новой стоимости до следующей подтверждённой смены партии/стоимости.
2. Сохранение полной стоимости упаковки и правила без ручного общего количества отправок и без обязательного пересчёта новой партии дома.
3. Автоматический поиск доступных поставок, получение состава точного SKU, подсчёт документальных количеств с раздельными статусами.
4. Автоматическое присоединение поставок с доказанной принадлежностью правилу. Если источник не доказывает дату отправки — подтверждение выбранного найденного списка одним действием, без ввода каждого ID и количества.
5. Сохранение старой стоимости товара, уже находящегося на Ozon. Отправка новой партии не переоценивает старый остаток.
6. Продолжение уже сохранённого черновика, остановившегося на вопросе общего количества.

Разделить три независимых результата:

- RULE_CONFIRMED — подтверждено правило принадлежности партии.
- SUPPLY_COVERAGE — доказано, какие поставки и количества прочитаны.
- FIFO_APPLY_READINESS — доказаны начальный остаток, физические движения, финансовые identities и прочие основания фактического применения.

Правило партии не доказывает полный журнал движений. Существующий R1 остаётся отдельным блокером фактического FIFO, пока поддержанный полный источник не установлен. Не закрывать R1 подтверждением правила, нулевым старым транзитом, суммой поставок или завершением API-пагинации.

Это расширение существующего FIFO. Не создавать вторую систему себестоимости, новый scheduler, отдельный bot/router либо обходной apply. Не менять алгоритм TaxService и полномочия Return COGS. Обнаруженная при локальном обновлении ошибка резервирования assistant_session.json (list против ожидаемого dict) — отдельный follow-up, вне scope этого задания.

## 2. Бизнес-правила, уже принятые владельцем

### 2.1. Реальный случай — описание, не fixture и не команда записи

| Поле | Значение |
|---|---|
| Товар | hook-2, SKU 3921245627 |
| Единица | Продаваемая упаковка |
| Старая итоговая себестоимость | 21.00 ₽ |
| Новая итоговая себестоимость | 14.65 ₽, включая доставку до владельца и упаковку |
| Первая известная отправка новой партии | 05.11.2026 |
| Старый товар дома на момент первой отправки | Явно подтверждённый 0 |
| Старый товар в отдельном транзите на тот момент | Явно подтверждённый 0 |
| Первая известная отправленная группа | 6 982 упаковки |
| Последующие отправки | Были, из той же новой партии; общий итог неизвестен |
| Новая партия дома | Количество неизвестно |

6 982 больше не считать полным текущим количеством партии. Не требовать посчитать дополнительные отправки ради сохранения цены. Числа 1 191/1 192/3 712 из прежних снимков не использовать как автоматически доказанный FIFO opening. Их исторические ограничения сохраняются.

Владелец сейчас находится в сохранённом мастере на вопросе «Введите известное общее количество единиц новой партии, отправленных в Ozon». После обновления продолжить тот же case, сохранив цены, дату и подтверждённые нули.

Реальные owner/store/ID, файлы, данные и базы владельца не добавлять в тесты/Git. Synthetic scope: store=test-store-a, SKU=1000000001, product=101, offer=test-a. Другой owner/store/SKU задавать явно.

### 2.2. Правило принадлежности

Режим PER_SKU_AFTER_DISPATCH_BOUNDARY разрешён только после отдельного owner confirmation:

> С указанной границы все новые поставки выбранного SKU — из новой партии. Старого товара дома и в отдельном транзите на эту границу не осталось.

Scope: owner + tenant/store + product identity + точный SKU. Не распространять правило на магазин целиком. Не сопоставлять по названию, первой строке состава или неподтверждённому offer mapping.

Предпосылки: old_home=0 и old_transit=0 должны быть явными подтверждениями владельца. Положительное или неизвестное значение запрещает автоматическое правило; сохранить cost draft и предложить прежнюю явную привязку. Старые единицы на Ozon допустимы и продолжают учитываться по старой FIFO-стоимости.

Правило действует до следующего подтверждённого изменения партии/стоимости этого SKU. Дополнительная отправка не требует новой записи цены. Одинаковая цена сама по себе не доказывает одну физическую партию.

Клиентские возвраты, вывозы, повторная отправка возвращённого старого товара, межскладские перемещения не становятся закупками новой партии. Сохраняются их исходная стоимость и lineage существующего FIFO.

### 2.3. Граница, первый день и следующая партия

Хранить дату в подтверждённом часовом поясе магазина; не использовать timezone компьютера. При неизвестном timezone сохранить draft и запросить его подтверждение через существующий механизм.

Дата первой отправки не означает автоматически весь календарный день:

- спросить: «Все отправки этого SKU за ДД.ММ.ГГГГ были из новой партии?»;
- YES сохраняет OWNER_ALL_DISPATCHES_ON_START_DATE; доказанные отправки этого дня входят в правило;
- NO/UNKNOWN оставляет первый день пограничным: выбрать подходящие поставки из найденного списка; доказанные даты строго позже start_date могут классифицироваться автоматически;
- точное время использовать только при доказанном источнике/подтверждении; не придумывать 00:00:00 как физическое время отправки;
- следующая граница закрывает предыдущую интервалом [start, next_start); пересечения запрещены;
- две стоимости в один день без доказанного времени или явного поставочного разделения дают REQUIRE_REVIEW; последняя запись не побеждает автоматически;
- исправление границы/стоимости — новая версия, устаревшие preview отклоняются; APPLIED история меняется только через существующий correction/replay.

Дата отправки не является датой физической приёмки, продажи или финансового признания.

### 2.4. Разделение количеств

| Поле | Значение |
|---|---|
| owner_control_total | Необязательный контроль владельца на конкретный период/срез и вид количества |
| declared_in_found_supplies | Количество целевого SKU по текущим версиям составов найденных поставок |
| declared_in_shipped_supplies | Состав только поставок с доказанным статусом отправки; подпись «По составу отправленных поставок» |
| accepted_units | Подтверждённое принятое количество SKU по актам через существующую reconciliation |
| pending_units | Только при сопоставимых известных величинах без конфликта; иначе UNKNOWN |
| planned_units | Отдельно, не входит в отправленные/принятые |
| known_subtotal / unknown_quantity_supply_count | Известная часть и число поставок без количества; не подменять полным итогом |

Размер закупленной партии и количество дома могут оставаться UNKNOWN. Не создавать бесконечный запас и не считать неизвестное нулём.

Будущие поставки увеличивают найденную сумму без требования владельцу исправить цену или ручной итог. Контроль 6 982 на историческую дату не является вечным cap. Сравнивать контроль только с тем же окном/срезом и видом количества; реальное расхождение в совпадающем окне блокирует factual apply.

Legacy control без окна сохраняется как UNBOUNDED_LEGACY_CONTROL. Не изобретать дату из updated_at и не считать его текущей суммой. Старые ручные declarations не удалять.

Приёмка cumulative 40→70→100 равна 100. Независимые части актов суммируются по действующему контракту; повторы не дублируют приход. Correction 100→90 требует отдельного review, не затирает историю.

Поставочные quantities не подменяют sellable stock, sales units, ordered_units или COGS.

## 3. Проверенные точки расширения

| Существующий компонент | Факт | Изменение |
|---|---|---|
| telegram_fifo_cost_transition_runtime_service._next_field/_prompt_next/handle_text | Общий итог обязателен в мастере | Выбор auto/control и восстановление текущего шага |
| TransitionCase в fifo_cost_transition_contracts.py | declared_shipped_units уже допускает None с UnknownValue | Явный supply_total_mode и совместимость старых payload |
| fifo_cost_transition_service.get_supply_manifest | Суммирует owner declarations | Сохранить legacy-поля; добавить отдельный automatic manifest |
| fifo_cost_transition_store.append_supply_declaration | Превышение owner_total запрещено | Не применять бессрочный legacy cap к новым automatic observations |
| fifo_cost_transition_supply_reconciliation_service | None даёт OWNER_DECLARED_TOTAL_UNKNOWN | Отдельный auto путь со своими proof gates |
| fifo_cost_transition_readiness_service | owner_total=None делает manifest неполным | Typed auto manifest вместо обязательного ручного итога; R1 сохраняется |
| fifo_cost_transition_supply_refresh_service | Обновляет выбранную вручную supply | Переиспользовать normalizer/reconciliation в массовом сборе |
| api/ozon_client.py | List v3 <=100, details v3 <=50 orders, act methods | Переиспользовать read-only методы; bundle после проверки FB02 |
| cross_docking_supply_source.py | Только COMPLETED; специальная семантика одного crossdock supply и state_updated_date | Не переносить эту семантику на новую партию; действующую экономику кросс-докинга не менять |
| fifo_cost_source_normalizer.py | Акт: sku_info.sku, declared_quantity, fact_quantity | Переиспользовать; summary multi-SKU не считать количеством выбранного SKU |
| fifo_cost_repository.py | FIFO schema version 16 | Additive v17; Planning PRAGMA user_version не менять |
| telegram_assistant_factory.py | Общая production assembly transition workflow | Единственная точка подключения новых сервисов |

Новые файлы и ответственность зафиксированы:

- services/fifo_cost_batch_rule_contracts.py — immutable types раздела 5.
- services/fifo_cost_batch_rule_service.py — rule preview/confirm, версии, чистая классификация.
- services/fifo_cost_batch_supply_store.py — scoped persistence поверх существующего repository.
- services/fifo_cost_batch_supply_source.py — bounded enumeration, состав SKU, source normalization.
- services/fifo_cost_batch_supply_manifest_service.py — чистая сборка quantities/coverage.
- services/telegram_fifo_cost_batch_rule_service.py — UI делегат существующего runtime.

Не добавлять всю реализацию в уже большой Telegram runtime. Использовать существующие tenant cipher, callback tickets, lifecycle и operation trace.

## 4. Контракт источников и обязательная проверка формата

Автор ТЗ проверил 13.11.2026:

- существующие wrappers list/get/acts присутствуют в коде;
- официальный гайд Ozon от 10.06.2026 описывает list/get и /v1/supply-order/bundle для состава SKU и количества;
- официальное сообщение от 19.01.2026 указывает, что storage_warehouse.arrival_date соответствующих crossdock методов всегда null с 16.02.2026;
- полный JSON schema bundle, точные raw state enum и поле фактической отправки в этой проверке не извлечены и не считаются известными.

Первоисточники:

1. https://dev.ozon.ru/start/526-Gaid-integratsiia-metodov-Seller-API-FBO-so-skanerom/
2. https://dev.ozon.ru/news/647-Izmeneniia-v-metodakh-Seller-API-pri-rabote-s-postavkami-FBO/
3. https://dev.ozon.ru/news/643-Izmeneniia-v-metodakh-dlia-zaiavok-na-postavku-v-Seller-API/
4. https://docs.ozon.ru/api/seller/ — актуальные schemas нужных operations.

В FB02 перенести точные request/response shapes, pagination и raw enum из официального описания в source-contract note и синтетические fixtures. Это сверка формата, не разрешение менять бизнес-правила. Наличие bundle endpoint в гайде не доказывает произвольный payload с supply_id/bundle_id.

Допустимые источники:

- list/details — доступные заявки и все вложенные supplies, все подтверждённые raw states профиля, включая in-flight/receiving/completed/dispute/cancelled/planned;
- bundle — состав конкретной supply, точный SKU, заявленное количество, документированная собственная пагинация;
- act summary/products — принятие и версии актов через существующие нормализаторы;
- owner selected set — принадлежность строго показанного множества поставок с provenance OWNER_CONFIRMATION.

Не использовать created_date, state_updated_date, timeslot, act.created_date или числовой порядок ID вместо фактической отправки. ORDER и SUPPLY не взаимозаменяемы; в заявке может быть несколько supplies.

Если dispatch date не доказана, возвращать UNKNOWN и предлагать точный найденный список для группового owner confirmation. Не требовать общий ручной итог или ввод каждого ID. Если состав/акт/поставка не получены, количество UNKNOWN, не 0.

При недоступном/неподтверждённом bundle контракте продолжить независимые этапы и реализовать нормализованную adapter boundary с честным UNKNOWN. Не придумывать поле quantity. В финале отметить source gap; не заявлять полную автоматизацию количеств без доказанного production adapter.

## 5. Фиксированные типы, методы и хранение

### 5.1. Типы

Frozen dataclass, tuple/immutable mappings; Decimal и существующие валидаторы scope/date/timezone/money/quantity. bool не является int. Количество SKU в supply: 0..1 000 000, суммы проверяются отдельно; деньги строго положительные в действующих пределах.

SupplyTotalMode = LEGACY_OWNER_TOTAL | AUTO_FROM_SUPPLIES | OWNER_CONTROL.
Старый payload без mode читается как LEGACY_OWNER_TOTAL; отсутствие поля не активирует правило.

BatchRuleRevision:

- scope, case_id, rule_id, rule_revision>=1, policy_version=1;
- start_local_date, store_timezone, start_day_policy=ALL_OWNER_CONFIRMED|EXPLICIT_SUPPLY_SET;
- new_unit_cost_rub, cost_input_fingerprint, old_home_confirmed_zero, old_transit_confirmed_zero;
- boundary_supply_digests, predecessor_rule_id/revision или None;
- event_kind=CONFIRM|REPLACE|CLOSE|CANCEL, end_local_date_exclusive или None;
- owner_confirmation_fingerprint, confirmed_at_utc, rule_fingerprint;
- applied_rate_reference=None до обычного apply; после — ссылка, не отдельная ставка.

SupplySkuObservation:

- scope, record_key (scoped digest SUPPLY+SKU), order_ref_digest, supply_ref_digest;
- encrypted_lookup_payload, без raw IDs в общедоступных JSON/log/callback;
- source_profile_version, source_fingerprint, captured_at, source_as_of или None;
- source_status, normalized_status существующего normalizer, is_crossdock True/False/None;
- dispatch_local_date/time или None, dispatch_time_status=CONFIRMED|UNKNOWN;
- planned_declared_quantity, shipped_composition_quantity, accepted_quantity — независимые nullable;
- quantity_source_kind/coverage, acceptance_fingerprint/version, explicit_zero_fields;
- membership=ELIGIBLE|NEEDS_CONFIRMATION|OUTSIDE_RULE|EXCLUDED|CONFLICT, issues.

BatchMembershipDecision:

- decision_id/revision, exact scope/case/rule_id/rule_revision;
- INCLUDED|EXCLUDED, source=RULE_WITH_CONFIRMED_DISPATCH|OWNER_SELECTED_SET;
- sorted record_keys и relevant source fingerprints, previous decision refs;
- candidate_set_fingerprint, membership_binding_fingerprint, idempotency_key, confirmed_at.

membership_binding_fingerprint включает scope, supply+SKU, rule id/revision/границы, доказательство даты либо exact owner inclusion, но не текущие accepted quantities/транспортный статус/captured_at. candidate_set_fingerprint для кнопки подтверждения дополнительно связывает весь показанный observation set. Поэтому изменение показанных данных до confirm отклоняет stale кнопку, а обычная смена статуса после сохранённого решения не заставляет повторно подтверждать принадлежность партии.

API observation не превращать в SupplyDeclaration с provenance OWNER_INPUT.

SupplyScanCoverage:

- scan_id/revision, scope/case/rule_revision, requested_from/through, captured_at;
- supported_state_profile, list_pagination_complete, details_complete, sku_composition_complete;
- historical_window_proven (default false), membership_complete, quantity_complete;
- physical_receipt_timing_complete, observation_set_fingerprint, source_contract_version;
- unknown counts, issue_codes, resumable_token или None.

Не сводить признаки к одному complete bool. Даже полный supply scan не устанавливает movement_coverage_complete.

AutomaticBatchManifest:

- rule id/revision/fingerprint; scan/observations/decisions seal;
- owner_control_total и explicit window/kind/status или None;
- quantities раздела 2.4, found/included/undecided supply counts;
- отдельные coverage flags, current_through, freshness, issues;
- canonical manifest_fingerprint, независимый от порядка строк и timestamp-only refresh;
- read_only=True; никаких FIFO events/rate writes.

### 5.2. Методы сервисов

- preview_rule(scope, case_id, expected_case_revision, input): валидировать предпосылки и текущую стоимость case; вернуть immutable preview/ticket, без бизнес-записи.
- confirm_rule(scope, case_id, expected_case_revision, preview_id, preview_fingerprint, idempotency_key): exact CAS, в одной transaction сохранить правило/подтверждение/mode; same key/same payload replay, different payload conflict; legacy cost/layers/COGS не писать.
- classify_supply(rule_chain, observation, membership_decisions): pure deterministic, без now/network/DB. Exact scope + proven dispatch boundary → auto membership; unknown date/start-day/overlap → NEEDS_CONFIRMATION. Ручное решение не скрывает противоречащие доказанные scope/date или другой batch.
- collect_supplies(scope, case_id, expected_case_revision, rule_revision, continuation_token=None, operation_trace=None): source staging → immutable observations → exact scoped publish CAS; вернуть новую case_revision/manifest/coverage/opaque continuation; без рекурсивного самовызова.
- preview_membership/confirm_membership: exact selected set, rule/source/case seals, максимум 50 строк на подтверждение, страницы по 8.
- get_manifest(scope, case_id, rule_revision): только чтение, просмотр не запускает API и не пишет ledger.

Новая confirmed successor rule атомарно записывает закрывающую ревизию предыдущей и новую границу; validates обе expected revisions. Не закрывать старое правило молча при простом создании draft.

### 5.3. Схема v17

Additive migration в существующей tenant DB. Если номер уже занят внешним изменением main — остановить миграционный этап для сверки и использовать следующий согласованный номер без downgrade; остальную независимую реализацию продолжить.

1. fifo_cost_batch_rule_revisions: immutable rule events, FK на exact case/stream, unique(rule_id, revision), scoped idempotency.
2. fifo_cost_batch_supply_observations: append-only версии, scoped record_key, encrypted lookup, source hash и связь с case.
3. fifo_cost_batch_membership_decisions: append-only exact set decisions, FK rule revision и observation refs.
4. fifo_cost_batch_supply_scans: transport checkpoint/staging, CAS progress/status. Mutable checkpoint не равен mutable business evidence.
5. fifo_cost_batch_total_controls: optional immutable controls с explicit window/kind.

TransitionCase получает supply_total_mode с legacy default. Обновить все serialize/deserialize/evidence readers и backup schema checks. Старый payload разрешён, неизвестный mode отклоняется.

Constraints: scope/case identity, revision>0, bounded payload/ciphertext/quantities, unique exact keys; update/delete guards для immutable таблиц. Миграция all-or-nothing; future version fail closed; Planning PRAGMA user_version неизменён. Только synthetic/temp DB.

Не помещать каждую поставку отдельной записью в лимитированные 100 bridge-evidence versions. Bridge получает один versioned typed manifest reference; старые evidence остаются читаемыми. При лимите — PARTIAL/LIMIT_REACHED, без скрытого усечения.

## 6. Алгоритм сбора и интеграции

### 6.1. Source и бюджеты

1. Проверить owner/tenant/store/SKU/case/rule и expected revisions до первого HTTP.
2. Один существующий root operation trace: максимум 20 s и 10 фактических HTTP-попыток на действие. Вложенные max_attempts=1, timeout<=8 s и <=remaining. 429/retries/каталог входят в те же 10.
3. List page<=100, details<=50 orders. Собственная bundle pagination только по FB02.
4. Не завершать scan на основании state_updated_date < start_date: это другая дата. Прочитать поддержанный domain в пределах бюджета и continuation.
5. Все вложенные supplies, canonical SUPPLY+SKU dedup; ORDER не считать отдельной товарной поставкой.
6. Количества только exact SKU/mapping; порядок строк и соседние SKU не влияют.
7. Planned/cancelled отдельно. Без доказанной отправки состав не входит в shipped total.
8. Акты сверять существующим normalizer. Accepted quantity может быть известно без точной даты physical receipt; не создавать из этого исторический receipt.
9. Same source content — reuse той же business observation. Изменение quantity/status — новая версия supply, не новая supply.
10. Публикация source set/manifest/case revision только после CAS. Stale/чужое staging не меняет текущий итог.

Накопленные пределы scan: 2 000 orders, 5 000 supplies, 10 000 normalized SKU rows; на case 20 000 observations и 100 rule revisions. Действующие меньшие size limits имеют приоритет. При лимите — PARTIAL, проверенная известная часть и явное ограничение, не «вся партия».

Checkpoint encrypted в существующей tenant DB, TTL 30 min, binding на scope/case/rule/cost/source profile/range и текущие CAS revisions. Restart не теряет продолжение и не дублирует строки. Изменение правила отклоняет старое continuation. 429 не вызывает немедленные безлимитные повторы.

list_pagination_complete означает завершение поддержанного API domain, не атомарный исторический срез. captured_at не подменяет server source_as_of. Изменяющаяся во время scan сортировка требует dedup и честного ограничения coverage.

### 6.2. Membership

Auto include только после подтверждённого правила, точного SKU и доказанной dispatch date в его интервале. Иначе owner выбирает из найденного списка; одно подтверждение связывает весь selected set, не только видимую страницу.

Preview показывает доступные даты с правильными названиями, статус, SKU quantity либо «не получено», причину неопределённости. Старый ручной ввод supply ID остаётся исключением для не найденной поставки.

Совпадающие owner declaration и API supply связываются canonical key; provenance сохраняется, quantity не удваивается. Конфликт нового источника с owner decision даёт REVIEW_REQUIRED, без тихого переноса между партиями.

Ручная ORDER declaration — контейнер/контроль, не дополнительная supply. Если она раскрыта в S1/S2, считать child supplies один раз; не прибавлять ORDER total к их сумме и не копировать его в каждого ребёнка. Неподтверждённое соответствие ORDER→SUPPLY оставлять отдельным unresolved reference.

После сохранённого membership обычные IN_TRANSIT→RECEIVING→ACCEPTED и обновление количества сохраняют принадлежность, пока membership binding не противоречит новым фактам. Они создают новую observation/manifest и при необходимости делают финансовый preview stale. Новая доказанная дата вне интервала, другой SKU или партия — конфликт, не автоматическое повторное подтверждение.

Изменение rule/observation делает affected READY seals устаревшими. Prepare/apply recheck включает manifest fingerprint и rule revision в действующую transaction.

После APPLIED новые observations не переписывают allocation. События в закрытом complete_through требуют existing correction/replay, более поздние идут через существующую подтверждаемую incremental обработку. Действующее правило не является разрешением на автоматический commit истории.

### 6.3. Totals и readiness

Считать последние непротиворечивые версии один раз на supply+SKU. Автоматическую сумму не записывать в owner input.

В AUTO отсутствие owner_total не блокирует сохранение/показ rule. SUPPLY_MANIFEST может стать READY без owner_total лишь при exact scope/membership/quantity и доказанном нужном coverage AutomaticBatchManifest. Пустой список, all(declarations), known subtotal или cursor exhausted недостаточны.

Пример partial UI: «Известно принято: 680 упаковок. В 1 поставке количество не получено. Чтение списка ещё не завершено».
Пример supported coverage: «По составу отправленных поставок: 1 000; принято: 680». Не писать «размер закупленной партии 1 000».

Остальные gates сохраняются: cutoff/остатки/reserved/receiving, физические продажи/возвраты/выбытия, exact finance identities/monthly COGS/tax и R1. Подтверждённый control conflict нужного окна блокирует применение. Source gap объяснять конкретно, без требования необязательного owner total.

## 7. Фиксированный UI

1. Ввод old/new total cost, first dispatch date, old home/transit остаётся.
2. Вместо mandatory quantity: «Как учитывать последующие поставки этой партии?»; кнопки «Считать по поставкам Ozon», «Добавить контрольное количество», «Вернуться».
3. Auto проверяет old zero/timezone и задаёт вопрос первого дня раздела 2.3.
4. Preview: SKU, новая ₽/упаковка, граница/действие до следующей смены, старые остатки по прежней FIFO-стоимости, unknown home, manual total не указан. Отдельная кнопка «Подтвердить правило». Сохранение не применяет FIFO.
5. Карточка: «Обновить поставки», «Проверить найденные», «Изменить правило», «Контрольное количество»; прежние readiness/preview/documents/history.
6. Список по 8, максимум 50 на confirm, opaque callbacks; exact whole selected set независимо от страниц.
7. Дата чтения/coverage видны; открытие карточки без сети.
8. Новые доказанные поставки при refresh присоединяются автоматически без новой цены/total. Неизвестная дата — групповое подтверждение.
9. Manual control получает explicit period/cutoff/kind и остаётся дополнительным.
10. Existing case на quantity step переходит к выбору п.2 без сброса. Текст «не знаю» открывает auto preview, но не означает согласие с правилом.
11. Старые numeric callbacks действуют лишь для точного текущего шага/ticket. Смена режима/SKU/store/revision делает их stale; чужой draft не меняется.
12. APPLIED case — read-only receipt; следующая партия через existing new/correction workflow.

Обычный экран без API-ключей/Client ID/raw JSON/SQL/endpoint деталей. Не просить owner создавать CSV, пересчитывать общий итог или вводить каждый найденный ID для штатного пути. При source gap — конкретное объяснение и действие, без обещания готового FIFO.

## 8. Обязательная матрица регрессий

Каждый Bxx связать с именованным тестом в review packet. Все источники синтетические.

| ID | Вход | Ожидаемый результат |
|---|---|---|
| B01 | Existing case ждёт quantity, old=21/new=14.65, home/transit=0 | Продолжение на auto choice, значения сохранены |
| B02 | AUTO, owner total None | Rule preview/confirm доступны, None с UnknownValue, не0 |
| B03 | new home unknown | Нет обязательного пересчёта, finite/infinite stock не создан |
| B04 | old home1 или transit1/None | Auto rule не подтверждается; manual mapping и cost draft сохранены |
| B05 | 05.11 и ALL_OWNER_CONFIRMED | Доказанная отправка этого дня может войти |
| B06 | Первый день смешанный/unknown | Same-day требует выбора; доказанная отправка06.11 может войти автоматически |
| B07 | Только created/state_updated/act.created_date | Dispatch UNKNOWN, не auto include |
| B08 | В supply SKU A100 и B900 | Только A100; порядок строк не влияет |
| B09 | ORDER declaration300 раскрыта в S1 A100 и S2 A200 | Две supplies, сумма300, не600; ORDER не прибавляется |
| B10 | Дубли страниц/details/manual declaration одной supply A100 | Один supply,100 |
| B11 | Planned composition100 без доказанной отправки | planned100; shipped/accepted не100 |
| B12 | S1 declared500 accepted500; S2 declared300 accepted180; S3 declared200 acceptedNone | Found declared1000, accepted subtotal680 и missing1; accepted не1000 |
| B13 | Cumulative40→70→100, повтор70 | Accepted100 |
| B14 | Две независимые части40+60, повтор первой | Accepted100 |
| B15 | Correction100→90 | Conflict/review, предыдущая история сохранена |
| B16 | Явный fact_quantity0 против отсутствующего поля | Known0 против UNKNOWN |
| B17 | Receiving148 исчезло из API | Сохранённая supply/presence MISSING; не accepted0/списание |
| B18 | Разные supported statuses и crossdock true/false | Все читаются; не только COMPLETED/crossdock |
| B19 | Полная страница100 без надёжного cursor/end proof | PARTIAL |
| B20 | Повтор cursor/429/timeout/retry | <=10 HTTP и20s одного действия, безопасное продолжение |
| B21 | Restart посреди list/details/bundle | Durable resume, нет дублей, итог как единого прохода |
| B22 | Статус переместил строки пагинации | Dedup, не заявлено atomic historical coverage |
| B23 | Control6982 на05.11; позднее ещё100 | Current found7082 без вечногоcap; контроль05.11 отдельно |
| B24 | Control1000 и доказанный тот же window1100 | Видимое расхождение100, factual apply blocked |
| B25 | Legacy control6982 без окна | Сохранён как legacy; не присвоены фиктивная дата/новые поставки |
| B26 | Новое правило16.00 с12.11 | До границы14.65, после16.00, same-day ambiguity проверена |
| B27 | Rule/cost/source изменился после preview | Старый confirm rejected, неверных записей нет |
| B28 | Backdate/cancel послеAPPLIED | История неизменна, correction/replay draft |
| B29 | Другой owner/store/SKU/source supply | Нет чтения чужого ciphertext/записи/totals |
| B30 | Double confirm/timeout послеcommit | Одна rule/decision; replay исходного результата |
| B31 | Stale callback другого draft/mode/store | No write; текущий draft сохранён |
| B32 | Старых3×21, принято новых100×14.65, sale5 | COGS92.30, old0/new98 после доказанного physical event |
| B33 | Новых отправлено1000, принято100 | Запас1000 не создан |
| B34 | Accepted100 без доказанной physical receipt date | Количество видно, исторический receipt не придуман |
| B35 | Rule + full supply pages, нет полного movement ledger | R1/SOURCE_BLOCKED, noREADY/apply |
| B36 | Полные synthetic cutoff/movements/finance/manifest/tax | Production prepare→explicit apply→restart→retry, один commit |
| B37 | Источник/manifest изменился послеprepare | Stale apply rejected, no partial write |
| B38 | Возврат старой единицы после новой партии | Исходная стоимость21/lineage, не закупка14.65 |
| B39 | Старый saved plan и новая cost revision | План frozen; новый расчёт использует только verified cost |
| B40 | v16→v17 + fault; backup/restore | Additive rollback, тот же rule/history, planning version неизменён |
| B41 | Пустая partial выборка/все quantities unknown | UNKNOWN/PARTIAL, не подтверждённый total0 |
| B42 | Те же rows переставлены/новый captured_at; обычная смена транспортного статуса | Timestamp-only версия не создана; новая status observation не требует повторного membership при неизменном binding |
| B43 | Отмена после фактической отправки/возврат поставки | Не вычтено молча из historical shipped; отдельный status/movement |
| B44 | Новый неподтверждённый raw state/source field | UNKNOWN/unsupported, не accepted default |
| B45 | Неполный SKU composition | Нет обязательного manual quantity; rule можно сохранить с source gap |

## 9. Этапы FB00–FB31

После каждого этапа: небольшой коммит, запись функций/файлов, SHA, команд и фактических проверок в progress. Статусы NOT_STARTED / IN_PROGRESS / DONE / BLOCKED. Наличие файла само по себе не означает DONE.

### PR A. Контракты, хранение, необязательный общий итог

**FB00 — исходная точка и сохранность.** Зависимости: нет.
Прочитать AGENTS, CURRENT_STATE, DECISIONS/066, TEST_MAP, это ТЗ и FL/FR progress/review. Зафиксировать ветку/HEAD/base/diff, hashes данных без содержимого. При dirty work сохранить существующее отдельным checkpoint. Сохранить .fl12-deps/. Не работать в папке запущенного Desktop-бота. Создать Resume/таблицу стадий; полноту тестов не заявлять заранее.

**FB01 — воспроизвести лишнее требование.** Зависит FB00.
Регрессии B01/B02/B23: _next_field требует total, readiness блокирует None, cap не ограничен датой. Зафиксировать baseline failures. Legacy assertions менять только для нового explicit mode.

**FB02 — проверить source schema.** Зависит FB00.
Создать FIFO_BATCH_SUPPLY_SOURCE_CONTRACT_2026-11-13.md: exact states, list/details/bundle/acts shapes и pagination, quantity/date semantics, официальные ссылки/дата проверки, явно missing fields. Synthetic fixtures. Без owner API. Недоступное поле — source gap, независимые этапы продолжаются.

**FB03 — типы и pure validators.** Зависит FB01.
Реализовать раздел 5.1, canonical fingerprints/ordering. Проверки B02/B03/B05–B07/B26/B29/B44; никакого IO.

**FB04 — additive v17.** Зависит FB03.
Таблицы раздела 5.3, indexes/FK/immutable guards, scoped store methods, совместимые readers. Fresh/v12/v16 synthetic DB, rollback/future version B40; Planning PRAGMA user_version сохранён.

**FB05 — rule preview/confirm.** Зависит FB04.
Exact CAS/idempotency/cost binding, timezone/первый день/old-zero. Owner rule не пишет actual rate/layers. B04/B27/B30/B31.

**FB06 — classifier и интервалы.** Зависит FB05.
Pure rule chain, first-day selection, next boundary/same-day ambiguity, mixed batch, cancellation, конфликт owner/source. B05–B07/B26/B28/B38/B43.

**FB07 — optional control.** Зависит FB04.
supply_total_mode, UnknownValue для manual total, control window/kind. Нет бессрочного cap в auto; legacy manual declarations и проверки сохранены.

**FB08 — продолжение мастера.** Зависит FB05–FB07.
Выбор auto/control вместо mandatory total, existing quantity step и «не знаю», preview/confirm. Пока source не подключён — честный UNKNOWN/«не обновляли», без фиктивного total. B01–B04/B31.

**FB09 — интерфейс auto manifest в readiness.** Зависит FB07.
Typed interface, absent manifest даёт source gap; None owner total в auto не единственный блокер. Cutoff/R1 не обходятся. B35; legacy mode продолжает старый путь.

**FB10 — PR A checkpoint.** Зависит FB08–FB09.
Targeted contracts/schema/UI/legacy, compile/diff, isolated full pytest, exact-SHA CI. Документировать выполненные контракты и ещё не подключённый источник. PR A по разделу 10.

### PR B. Поиск поставок, состав SKU, акты, суммы

**FB11 — bounded source skeleton.** Зависит FB02/FB10.
collect_supplies, root trace20s/10 attempts, request allowlist; fake client считает фактические попытки. Просмотр UI без сети.

**FB12 — list/details.** Зависит FB11.
Все raw states проверенного профиля, cursor proof, все nested supplies, details batch<=50 и накопленные limits. Не использовать COMPLETED/crossdock-only или state_updated cutoff. B09/B18–B20/B22.

**FB13 — SKU composition.** Зависит FB12.
get_supply_order_bundle только по exact schema FB02; pagination, exact scope/mapping, planned против shipped composition. При отсутствии schema — поддержанный adapter boundary и UNKNOWN, без invented field. B08/B11/B41/B44/B45.

**FB14 — фактическая приёмка.** Зависит FB13.
Existing act normalizer/reconciliation; cumulative/partial/correction/missing receiving, даты не выдумывать. B12–B17/B34.

**FB15 — durable checkpoint/publish.** Зависит FB12–FB14.
Encrypted TTL/range/rule/source/case binding, staged CAS publish и корректное обновление continuation revision. Restart без дублей. B20/B21/B29/B42.

**FB16 — dedup manual/API.** Зависит FB15.
Canonical supply+SKU, manual provenance сохранён, одна ORDER не одна supply. B09/B10/B13/B14.

**FB17 — manifest/totals.** Зависит FB16.
Pure quantities/known subtotal/missing counts/coverage, exact window controls, legacy control labels. B12/B23–B25/B41/B42.

**FB18 — негативные источники.** Зависит FB17.
Denied API/no acts/partial bundle/invalid quantities/bool/overflow/duplicate pages/profile change. Ошибки не пишут FIFO. B18–B22/B44/B45.

**FB19 — PR B checkpoint.** Зависит FB18.
Targeted source/normalizer/budget/manifest и существующий crossdock, isolated full pytest, exact-SHA CI. Показать supported source matrix и незакрытые source gaps.

### PR C. UI, следующие поставки, FIFO-интеграция и сдача

**FB20 — production assembly.** Зависит FB19.
Единая existing factory/workflow с rule/source/store/manifest. Temp real SQLite и fake network; без второго composition root.

**FB21 — карточка и bounded refresh.** Зависит FB20.
Кнопки раздела 7, continuation/progress/safe message splitting/конкретные issues, existing inflight/double-click protection.

**FB22 — групповое подтверждение.** Зависит FB21.
Страницы8, confirm<=50, exact whole-set seal, selected include/exclude. Без raw IDs в callback, owner decision не Ozon fact. B07/B27/B29–B31.

**FB23 — следующие поставки и следующая стоимость.** Зависит FB22.
Доказанные новые supplies присоединяются без цены/total; unknown-date — grouped review. Следующая граница через отдельный preview/confirm; same-day ambiguity. B23/B26/B28.

**FB24 — readiness/bridge.** Зависит FB17/FB23.
Typed manifest в existing evidence/reconciliation; supplier quantities не movement ledger. Все UNKNOWN/provenance объяснимы, legacy path совместим. B33–B35/B45.

**FB25 — prepare/apply seals.** Зависит FB24.
Rule revision/manifest/source fingerprint в existing atomic recheck. Ownership replay/TaxService/Return COGS сохранён. B35/B37; новые observations после APPLIED не изменяют историю автоматически.

**FB26 — history и consumers.** Зависит FB25.
Различать rule и FIFO status, source coverage/as-of, причину версии. Unit economics/Period Profit/current cost/saved plans получают только canonical verified cost. B32/B38/B39.

**FB27 — положительный production E2E.** Зависит FB26.
Paused case→auto choice→rule confirm→paginated multi-SKU source→group membership при необходимости→полный synthetic cutoff/movements/finance→prepare→explicit apply→restart→retry, один commit. B01/B08–B10/B21/B30/B32/B36. Fake только сеть; repository/validator/apply не заменять success stub.

**FB28 — crash/migration/backup.** Зависит FB27.
До/внутри/после commit, CAS race, quota, key unavailable, stale first-day selection, migration rollback и backup/restore public APIs. B27–B31/B37/B40. Owner session file не исправлять под fixture.

**FB29 — полный профиль.** Зависит FB28.
Все B01–B45 + FIFO/Telegram navigation/tenants/budgets/Period Profit/Tax/returns/crossdock/saved plans; compileall/diff; полный pytest в disposable copy с synthetic configuration, без owner data/credentials. Не skip/deselect ради зелёного. Data hashes/diff сверить с FB00.

**FB30 — документация и owner guide.** Зависит FB29.
CHANGELOG/CURRENT_STATE/TEST_MAP, DECISIONS066 implementation note только по выполненной работе; user guide про rule/unknown/group review/continuation/control window/R1. Resume с фактическими SHA/results.

**FB31 — CI и пакет независимого review.** Зависит FB30.
Текущие SHA всех PR: Windows/Linux full suite, production Docker build/runtime smoke. Новый commit требует нового CI. Пакет: PR/base/head/CI URLs, source matrix, Bxx→tests, migration/rollback, privacy, trace текущего quantity prompt, owner limitations. OWNER_CASE_VERIFIED=false без реального разрешённого прогона/полных источников. Merge/deploy/live API/startbot запрещены.

## 10. Git, проверки и Definition of Done

Спецификация поставляется отдельным PR от main. Luna начинает от опубликованной головы spec branch; если spec уже в main — от актуального main после сверки. Фактическую базу записать в FB00.

| PR | Ветка | База | Этапы |
|---|---|---|---|
| A | codex/fifo-auto-batch-foundation-20261113 | spec branch либо main, если spec слит | FB00–FB10 |
| B | codex/fifo-auto-batch-sources-20261113 | A | FB11–FB19 |
| C | codex/fifo-auto-batch-integration-20261113 | B | FB20–FB31 |

Каждый PR содержит свой diff. Если другая модель слила base — безопасно обновить topology и записать фактические связи. Не force-push чужую историю, не reset/clean/stash-pop owner data.

Commit/push/создание PR разрешены. Слияние, развёртывание, изменение локального работающего Desktop-бота, реальные Ozon/Telegram-запросы и запуск бота запрещены.

- [ ] В новом и возобновлённом auto flow нет обязательного ручного общего количества.
- [ ] Scoped rule, первый день, следующая граница и история версий реализованы.
- [ ] Production wiring поддерживает known-date auto и unknown-date grouped review без обязательного ручного количества.
- [ ] Поддержанные states, вложенные supplies и точные SKU читаются с bounded continuation.
- [ ] UNKNOWN/known0/partial/correction и provenance различаются.
- [ ] Следующие отгрузки не вызывают новый ввод цены или бессрочный cap.
- [ ] Положительный synthetic production E2E и отрицательные gates пройдены; R1 не обойдён.
- [ ] B01–B45 связаны с тестами; isolated full pytest и CI текущих SHA зелёные.
- [ ] Source gaps явно NOT_VERIFIED; неполный adapter не назван полной автоматизацией.
- [ ] Документация/журнал/review packet готовы, owner data не изменены.
- [ ] Merge/deploy/live API/startbot не выполнялись.

Если source format нельзя подтвердить официальной schema или имеющимся обезличенным примером, продолжить независимую реализацию и synthetic normalized boundary. В финале указать конкретный unresolved source blocker. Не придумывать контракт ради завершения; неподтверждённый production adapter не объявлять готовым.

## 11. Resume и команда запуска

После каждого этапа обновлять LUNA_FIFO_AUTO_BATCH_RULE_PROGRESS_2026-11-13.md: branch/HEAD/base, status, функции/контракты, exact checks/results, source gaps, data hashes, PR/CI, next stage.

После сокращения контекста перечитать Resume, ТЗ, git status/diff; продолжить, не начинать уже выполненное заново. Не откладывать независимые этапы из-за ещё отсутствующих отчётов владельца. Бизнес-выбор вне ТЗ запросить; техническую реализацию заданных контрактов выполнять самостоятельно.

Команда для Luna:

Выполняй project_brain/LUNA_FIFO_AUTO_BATCH_RULE_TASK_2026-11-13.md. Начни с FB00 и двигайся по зависимостям до FB31. Следуй зафиксированным бизнес-правилам, контрактам, схеме v17, алгоритму источников, UI и матрице B01–B45. Сохраняй существующую работу и данные; после каждого этапа обновляй журнал и фактические результаты проверок, после сокращения контекста продолжай по Resume. Работай автономно до необходимого бизнес-решения или неустранимого блокера. Заверши на трёх зависимых PR с зелёным CI текущих SHA и пакетом независимого review. Слияние, развёртывание, изменение работающего бота, реальные Ozon/Telegram-запросы и запуск бота не выполняй.

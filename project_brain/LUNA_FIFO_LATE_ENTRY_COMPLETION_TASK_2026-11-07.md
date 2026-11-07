# ТЗ для Luna: завершение позднего ввода себестоимости и поставок FIFO

Дата: 2026-11-07. Этапы: FL00–FL35. Статус: SPEC_READY, реализация NOT_STARTED.
База подготовки: main d8d4ba00c85acf14ba9a960f56a755fbe30b555c, PR #726 слит.
Это задание продолжает FC00–FC35 и ADR 066. Архитектурные решения ниже зафиксированы: Luna исполняет их, а не выбирает новый способ учёта.

## 1. Результат для владельца

Владелец сообщает полную себестоимость новой закупки после того, как часть товара уже отправлена через кросс-докинг. FIFO может быть ещё не настроена. Бот сразу сохраняет подтверждённые владельцем сведения, список поставок и неизвестные значения, позволяет возобновить работу после перезапуска, собирает доказательства и проводит через сверку до подтверждаемого применения истории.

Поставка не исчезает из учёта, когда при смене статуса её количество пропало из агрегированного ответа. Новая стоимость не назначается всем продажам по дате отправки. Старый товар, ранее отправленный покупателям, не списывается второй раз после появления финансового начисления. Прошлые отчёты меняются только через новую проверенную ревизию.

Обязателен положительный сквозной путь: создание случая до начальной FIFO → сведения о незавершённых поставках → импорт документов → сверенный bridge остатков и продаж → preview влияния → отдельное подтверждение → атомарное применение → новый расчёт и восстановление после перезапуска. Одной кнопки, черновика или сообщения SOURCE_BLOCKED недостаточно для реализации задания.

Два результата оцениваются отдельно:
- IMPLEMENTATION_VERIFIED: весь путь реализован и пройден через production wiring на синтетических, проверяемых источниках.
- OWNER_CASE_VERIFIED: реальный случай сверён владельцем по документам/разрешённой диагностике. До этого статуса никакой синтетический флаг не включает фактическую FIFO-прибыль реального магазина.

Отсутствие ещё не опубликованного отчёта не останавливает независимую разработку. Оно запрещает применение непроверенной истории и остаётся конкретным требованием к данным владельца.

## 2. Зафиксированные бизнес-правила

1. Метод FIFO: сначала наиболее старые единицы. Это правило распределения затрат, а не физическое отслеживание выбранной Ozon упаковки.
2. Единица — продаваемая упаковка SKU. Вложенные штуки не умножают количество.
3. Полная себестоимость включает закупку, доставку до владельца и упаковку. Комиссия, налог, реклама, логистика Ozon и кросс-докинг не включаются повторно.
4. Поддержать два режима стоимости: TOTAL_LANDED и COMPONENTS. В первом хранить итог и отсутствие разбивки. Нельзя записывать итог как «закупку», а неизвестные компоненты как подтверждённые нули.
5. Новая закупка дома может иметь неизвестный общий размер. Не требовать пересчёта дома. UNKNOWN не равен 0.
6. Ставка стоимости, заявленная отгрузка, документальная приёмка, доступный остаток и финансовая продажа — отдельные сущности.
7. Дата отправки, дата сообщения, дата создания акта, плановый слот и обновление статуса не доказывают дату физического поступления/выбытия.
8. Товар «в пути / на приёмке» сохраняет идентичность поставки и последнюю известную информацию. Его отсутствие в агрегате — MISSING_OBSERVATION, не ноль и не продажа.
9. Перемещение дом → транзит → Ozon не создаёт дополнительные единицы одной партии. Частичные приёмки учитываются по идентифицированным версиям документов.
10. Подтверждённая отмена поставки не равна уничтожению товара. Возврат владельцу/перенаправление требуют отдельного движения.
11. Возврат продажи сохраняет стоимость исходного распределения. Восстановление пригодного остатка и признание возвратного COGS — существующие независимые gates.
12. Изменение ставки само по себе не меняет финансовые начисления Ozon и налоговую политику.
13. Сохранять current/model/historical provenance. План и экспорт остаются снимками своей ревизии.
14. Один SKU ведётся внутри точного owner/store scope. Подтверждённые finance-SKU aliases сопоставляются существующим механизмом; отдельную identity-модель не создавать.
15. Нет разрешения автоматически применить что-либо к реальным данным. Любой финансово значимый переход требует действительного preview и отдельного подтверждения владельца.

Граница выпуска: один пропущенный переход стоимости, существующие старые слои, несколько поставок новой партии, частичная приёмка и дальнейшие обычные ставки. Несколько перекрывающихся пропущенных переходов не угадывать: сохранить сведения и перечислить конкретную неоднозначность. Не строить универсальный складской ERP.

## 3. Реальный случай как обезличенный контроль

Полная таблица происхождения и числовая матрица: FIFO_LATE_ENTRY_CASE_AND_ACCEPTANCE_2026-11-07.md.

Подтверждено владельцем: old_cost=21.00 RUB/уп.; new_cost=14.65 RUB/уп.; первая отправка новой партии 2026-11-05; всего отправлено 6982 уп.; старый домашний остаток и старый отдельный транзит на эту дату — 0. Часть новой партии дома имеет неизвестное количество. FIFO ещё не инициализирована.

Отчёт текущих остатков: available=1191, из них обычные 1182 и возврат FBS 9; preparing=18; checking=5; supplier_in_transit=6234; planned_supply=600; buyer_delivery=1689; buyer_return_transit=43. Отдельно removed_from_sale=41. Эти buckets нельзя складывать в «старый доступный остаток».

Дополнительно владелец объяснил отсутствующие 148 уп.: поставка в Беларусь, состояние «приёмка на складе». Контроль 6234+600+148=6982 не превращает все три числа в одинаково подтверждённый транзит. Агрегат API не доказывает список ID поставок, независимость buckets или принятое количество.

Ведомость 04–05.11: opening=4492; receipts=0; redeemed=775; seller_withdrawals=5; closing=3712; control_difference=0. В closing уже есть buyer_delivery=1646 и customer_return_transit=70. 3712 нельзя записывать как физический остаток очереди без классификации и bridge. Движений 06–07.11 в этой ведомости нет.

1192 из Google-таблицы и 1191 из Excel — разные наблюдения. Нельзя выбрать одно произвольно или назвать расхождение доказанной частотой обновления.

Реальных ID поставок и полного списка количеств по каждой пока нет. Их нельзя выдумывать из суммы. Производственные записи не создавать из этого раздела.

## 4. Существующие компоненты и обязательные точки интеграции

Использовать:
- app/services/fifo_cost_repository.py: schema v12, append-only события, аллокации, CAS/idempotency.
- fifo_cost_source_normalizer.py и fifo_cost_source_collection_service.py: существующие DTO, ограниченные read-only запросы, checkpoints.
- fifo_cost_supply_evidence_service.py: принятая поставка остаётся документальным доказательством, а не автоматическим приходом.
- fifo_cost_late_entry_reconstruction_service.py, fifo_cost_late_entry_impact_service.py, fifo_cost_late_entry_correction_service.py: расширить существующий путь. Не создавать второй вычислитель влияния/налога.
- fifo_cost_rate_service.py, fifo_cost_allocation_service.py, fifo_cost_replay_service.py: каноническая ставка и FIFO-математика.
- fifo_cost_period_profit_source_service.py и period_profit_fifo_explanation_view_service.py: фактическая интеграция и объяснение.
- fifo_current_unit_cost_adapter.py и существующие planning adapters: плановые потребители.
- telegram_fifo_cost_history_service.py, telegram_fifo_cost_late_entry_service.py, seller_cost_telegram_adapter.py, telegram_assistant_factory.py: текущие маршруты UI.
- BotBackupService, существующий tenant SQLite, криптография OzonAccountRepository и canonical TaxService.

Не менять: финансовую выручку/нетто, источник комиссии Ozon, налоговую формулу, 56 завершённых дней кросс-докинга, authority Return COGS, версионность сохранённых планов, lifecycle реального бота.

Разрешены новые узкие модули:
- fifo_cost_transition_contracts.py — DTO, enums, лимиты, нормализация полной стоимости.
- fifo_cost_transition_store.py — SQL helpers внутри соединения и транзакции существующего FIFO repository.
- fifo_cost_transition_service.py — создание случая, состояние, сборка preview, координация.
- fifo_cost_supply_observation_service.py — наблюдения конкретных поставок.
- fifo_cost_report_import_service.py — ограниченный read-only XLSX и его preview.
- fifo_cost_transition_reconciliation_service.py — чистая сверка buckets и покрытия.
- fifo_cost_cutoff_bridge_service.py — чистая валидация связи физического среза и продаж.
- telegram_fifo_cost_transition_runtime_service.py — возобновляемый UI.
Имена новых тестов повторяют имена сервисов. Дополнительный framework, база данных, scheduler, денежный движок или сторонний учётный контур запрещены.

## 5. Точные контракты

### 5.1. Общие правила

Время: UTC timestamp, timezone магазина Europe/Moscow по существующему default; отдельно recorded_at, captured_at, source_as_of, period_from/to, effective_at и precision. Date-only не превращать в точный timestamp. Суммы — Decimal и точное хранение, округление ROUND_HALF_UP. Количества — int, bool отклонять, 0..1000000; неизвестное — null плюс reason/provenance.

Любой DTO содержит schema_version, owner/store/SKU scope, source_kind, completeness, source_fingerprint. Финансовые previews привязаны также к FIFO revision, case revision, evidence-set fingerprint, allocation revision и tax-policy fingerprint.

### 5.2. TransitionCase

Поля: case_id (opaque), case_revision, identity, state, created_at, updated_at, dispatch_date (date-only допустима), old_unit_cost_rub, new_unit_cost_rub, cost_input_mode, nullable cost_components, owner_old_home_units, owner_old_transit_units, new_home_quantity (nullable), declared_shipped_units (nullable), opening_evidence_ref (nullable), source_watermark (nullable), reason_codes, supersedes_case_id (nullable).

state ∈ DRAFT, AWAITING_EVIDENCE, READY_TO_CONFIRM, APPLIED, CANCELLED.
Прогресс ввода отдельно от state; одновременные мастера не должны назначать новую бизнес-сущность по последнему текстовому шагу.

DRAFT/AWAITING_EVIDENCE разрешены без FIFO queue_initialized. Их сохранение не создаёт cutoff, FIFO-слой, аллокацию, legacy switch или активную финансовую стоимость. «Сохранено» в UI явно означает сведения/черновик, а не применение.

old_unit_cost_rub не заменяет цены уже существующих старых слоёв. Для неинициализированного SKU единая старая цена допустима только как явное подтверждение владельца для соответствующего opening proposal. Несогласие с имеющейся историей не исправлять автоматически. Если старых цен несколько, использовать существующий ввод отдельных начальных слоёв, не среднюю цену и не стоимость последней партии для всех.

READY_TO_CONFIRM — только производный результат полной проверки; владелец не может установить этот флаг. После изменения evidence/identity/tax/revision становится AWAITING_EVIDENCE, предыдущий preview устаревает.

### 5.3. SupplyDeclaration и SupplyObservation

Declaration: case_id, declaration_id, immutable revision, typed order/supply reference, exact SKU, declared_shipped_units, dispatch_date, owner provenance. Общая сумма случая и список поставок различаются. Если известна только сумма 6982, допускается сохранить case с нераспределёнными единицами; нельзя создавать фиктивную поставку на остаток.

Для повторного API-чтения сохранить lookup ID зашифрованным существующим Fernet/key provider. Fingerprint доменно разделить по owner/store/source-type. ID не помещать в callbacks, логи, обезличенные diagnostics или CSV history. Не создавать новый ключ/секретный файл. Если шифрование недоступно — сохранить остальные сведения как AWAITING_EVIDENCE с LOOKUP_REFERENCE_UNAVAILABLE; не терять ввод и не выдавать возможность обновления ID. Небольшое выделение существующего cipher provider допустимо без изменения credential-контракта.

Observation: declaration_id, captured_at, source_as_of nullable, raw_status allowlist, normalized_status, declared_quantity nullable, accepted_quantity nullable, accepted_quantity_kind (CUMULATIVE/DOCUMENT_LINES), act reference/version nullable, scope_complete, pagination_complete, presence=PRESENT/MISSING, source fingerprint.

Normalized statuses: DECLARED, AT_DROPOFF, IN_TRANSIT, RECEIVING, PARTIALLY_ACCEPTED, ACCEPTED, CANCELLED, UNKNOWN. Маппинг конкретных строк API брать только из проверенного текущего контракта; неизвестная строка → UNKNOWN с сохранённым безопасным кодом, не ACCEPTED.

Последнее наблюдение не удаляет прошлые наблюдения. MISSING не перезаписывает known declared/accepted quantity нулём. UI показывает раздельно последнее известное количество и отсутствие свежего подтверждения. confirmed accepted 0 допустим только как явное поле источника с подтверждённой семантикой.

Кумулятивные 40→70→100 означают 100 всего, не 210. Два действительно разных акта не склеивать; повтор одного акта не добавляет товар. Уменьшение принятого количества — конфликт/версионная корректировка, а не игнорирование или отрицательный автоматический приход.

### 5.4. BucketSnapshot и ReportEvidence

Раздельные buckets: available, reserved, preparing, checking, supplier_planned, supplier_transit, supplier_receiving, buyer_delivery, buyer_return_transit, internal_transfer, defective, removed_from_sale, seller_withdrawal. Неизвестные reserved/overlap не выводить из названия «Готовим к продаже». Возврат FBS — признак происхождения, не дополнительный товар поверх той же строки.

Отчёт содержит type, period, period_provenance, capture time, SHA-256 файла, версию parser, точные cell references и нормализованные поля. Исходный Excel в Git и таблицы событий не сохранять. Хранить allowlisted evidence и checksum; экспорты не содержат сырые идентификаторы.

Имя файла может предложить период/время, но владелец подтверждает его отдельно. Download/captured time не равен server-as-of. Формулы, Excel errors, пустые qty и неподдерживаемые headers не превращаются в нули.

Если в документе нет идентификатора магазина, импорт требует явного подтверждения владельцем текущего store. Оно хранится как OWNER_IMPORTED, а не как API-проверка магазина. Явное расхождение идентичности в документе отклоняется.

### 5.5. CutoffBridge

Обязательные поля: cutoff descriptor с timezone/precision, stock_scope, confirmed quantity buckets, pre_cutoff_outflow mappings, post_cutoff physical events, finance-to-sale identity mappings, linked returns/non-sale movements, complete_through watermark, source-set fingerprint, unresolved issues и provenance для каждого основания.

Bridge доказывает:
- какие единицы уже выбыли физически и отсутствуют в opening stock;
- какие ещё должны расходовать очередь после cutoff;
- как позднее финансовое начисление получает прежнюю COGS без повторного списания;
- как трактуются резерв, доставки покупателям, возвраты и несостоявшиеся поставки;
- полноту событий от cutoff до согласованного конца данных.

Агрегированная оборотная ведомость может быть контролем количества, но не доказательством identity/даты каждой продажи. Не создавать posting IDs или порядок событий из номера строки. При неизвестном порядке внутри дня применять сумму только если результат доказанно инвариантен для всех допустимых порядков; иначе блокировать.

Owner confirmation подтверждает действительно известные владельцу стоимость/остаток/состав. Простая галочка не превращает неизвестную дату, пагинацию или семантику API в доказанный факт. Запрещены hardcoded field_semantics_confirmed=True и снятие INVENTORY_CUTOFF_UNRECONCILED по наличию любого Excel.

### 5.6. Хранение и атомарное применение

Версия FIFO schema 12→13, расширяющая migration в существующем tenant DB. Planning schema и PRAGMA user_version не менять.

В текущей fifo_cost_rate_changes компоненты TEXT NOT NULL. Для TOTAL_LANDED не заполнять их ложными суммами: в v13 добавить cost_input_mode с default COMPONENTS, разрешить nullable components только для TOTAL_LANDED. Выбранный способ SQLite migration — контролируемый rebuild этой таблицы, сохранив все прежние primary keys, строки, значения, связи, индексы и immutable triggers. Использовать существующий migration guard; на собственном соединении временно выключить foreign_keys до BEGIN IMMEDIATE, создать replacement, скопировать прежние строки с mode COMPONENTS, заменить таблицу, восстановить triggers/индексы и проверить foreign_key_check до commit; вернуть foreign_keys в finally. Никакие бизнес-события не удаляются/не переписываются. Ошибка любого шага даёт rollback старой схемы. Проверить все child FK и raw hashes прежних значений в migration tests. Старую fifo_cost_late_entry_drafts не переделывать под pending: она остаётся совместимым читателем старых принятых черновиков; новые случаи идут через новые таблицы.

Новые таблицы в authority FifoCostRepository:
- fifo_cost_transition_cases — стабильная identity и версия схемы случая;
- fifo_cost_transition_case_revisions — неизменяемые входы/статусы, current revision выбирается CAS;
- fifo_cost_supply_declarations — неизменяемые версии привязки поставки;
- fifo_cost_supply_observations — append-only наблюдения;
- fifo_cost_report_evidence — append-only нормализованные документы;
- fifo_cost_transition_previews — ограниченные, fingerprint-bound previews/expiry;
- fifo_cost_transition_commits — append-only результат применения/idempotency/audit.

Использовать существующие scope/денежные ограничения, triggers, транзакционные helpers, quotas и backup. SQL helpers вынести в fifo_cost_transition_store.py; они не открывают собственное соединение, не коммитят внешний transaction и не создают второй repository authority.

Публичные методы repository: save_transition_case, append_supply_declaration, append_supply_observation, append_report_evidence, read_transition_case, list_transition_cases, prepare_transition_preview, commit_transition_case, cancel_transition_case. Входы keyword-only, tenant scope берётся тем же механизмом, что у FIFO; отсутствие scope — отказ.

commit_transition_case обязан в одной BEGIN IMMEDIATE транзакции:
1. проверить owner/store/SKU, case/FIFO/allocation revisions, preview, TTL, fingerprint источников и idempotency;
2. повторно проверить completeness и отсутствие конфликтующих активных переходов;
3. сохранить новые факты/ставку и необходимый opening cutover только для подтверждённого proposal;
4. записать полную новую allocation/projection revision и commit audit;
5. перевести case в APPLIED ровно один раз.
Любая ошибка откатывает все пять шагов. Нельзя публично commit rate, затем отдельным запросом replay и при этом писать «готово». Время API и ожидание пользователя не входят в SQLite write transaction.

APPLIED относится к подтверждённой ревизии до её complete_through, а не обещает полноту будущих данных. Позднейшие receipts/returns продолжают append-only движения по существующим validators и создают новую allocation revision. Нельзя менять applied snapshot или автоматически повторно добавить ранее учтённый транзит. Обнаруженная корректировка прошлого требует нового impact/confirm; отсутствие будущего источника явно закрывает только непокрытый расчёт.

## 6. Внешние источники, файлы и ограничения

- Все Ozon вызовы read-only, только через существующий клиент и operation-budget. Не менять старую семантику find_supply_by_id для cross-docking/accepted-act consumers.
- Добавить отдельный collector для конкретной незавершённой поставки и наблюдений. Нельзя искать только COMPLETED, а отсутствие в этом списке считать отменой.
- Операция UI: общий бюджет 20 секунд, максимум 10 реальных HTTP-попыток, максимум 2 страницы за шаг. Retry входит в тот же бюджет; continuation сохраняет scope и уже просмотренные страницы. При исчерпании — сохранённый прогресс и кнопка продолжения. Performance/рекламные запросы этому мастеру не нужны.
- Фоновый polling/scheduler не добавлять. Обновление по явной кнопке владельца, только в рамках выбранного случая.
- Для XLSX добавить openpyxl>=3.1.5,<4 и defusedxml>=0.7.1,<1 в runtime requirements. Только read_only, data_only; до чтения ZIP preflight: файл ≤10 MiB, распакованные данные ≤100 MiB, ≤2048 entries, запрет macro/external relationships, path traversal и suspicious compression ratio >100. Если существующий общий лимит строже — соблюдать его.
- Максимум 50000 строк, 100 колонок на лист, 15 секунд hard worker deadline и 3 одновременных import операции процесса. XLSX читает отдельный управляемый subprocess, parent прерывает только свой worker по deadline; отмена Future/thread не считается остановкой parser. Ограничения контролируются при фактическом чтении, а не только по dimension. Parser не блокирует Telegram event loop.
- Поддержать только две версии источников ниже. Не добавлять универсальный Excel importer и не исполнять формулы.
- «Управление остатками»: authoritative sheet «Товары», SKU/Артикул + двухстрочные headers; «Товар-склад» — отдельный контроль, а не ещё одно слагаемое. «Товар-склад снято с продажи» — отдельный bucket. Листы «Кластеры»/«Товар-кластер» не прибавлять к SKU итогу.
- «Оборотная ведомость»: SKU, opening buckets, receipts, redeemed, withdrawals/writeoffs и closing buckets. Итого сверять: opening + receipts - expenses - closing=0 с точностью целой единицы. Не заменять redeemed суммой ordered units.
- При смене headers показать неподдерживаемый формат, нужные поля и не изменять case. Исходные значения и подписи не «исправлять» догадками.
- Уже заданный legacy CSV flow сохраняется. XLSX обрабатывается новым importer только в подтверждённом контексте выбранного case; случайная загрузка не создаёт переход.

## 7. Этапы реализации

Каждый этап: небольшой commit, meaningful regressions, обновление журнала и фактических проверок. Зависимости ниже обязательны. Буквы модулей — упаковка PR, а не разрешение пропустить checks.

### Модуль A — основание (FL00–FL05)

**FL00 — чистая исходная точка.** Зависимость: нет.
Прочитать CURRENT_STATE, DECISIONS/066, TEST_MAP, исходное FC-ТЗ и этот документ. Проверить main, изменения, существующий PR. Не reset/stash/удалять чужую работу. Создать codex/fifo-late-entry-foundation-20261107 от актуальной головы PR спецификации, если он ещё не слит, сохранив документы; base foundation PR — main. Если ТЗ уже в main — начать от main. Записать HEAD, baseline checks и storage manifest в журнал. Отсутствие нового реального отчёта не блокирует этот этап.

**FL01 — карта текущих швов.** Зависимость: FL00.
В коротком FL01_IMPLEMENTATION_MAP.md перечислить существующие функции записи, source gates, production wiring и regression suite; сопоставить каждый новый контракт с конкретной точкой в коде. Не перепроектировать ADR 066. Любое объективное несовпадение с текущей веткой документировать и адаптировать названия, сохраняя заданные responsibilities и инварианты.

**FL02 — DTO, reason codes и часы.** Зависимость: FL01.
Реализовать раздел 5 в contracts. Все clock providers инъецируются. Добавить typed коды CASE_NOT_READY, SUPPLY_OBSERVATION_MISSING, SUPPLY_IDENTITY_CONFLICT, RECEIPT_CONFLICT, STOCK_SCOPE_UNPROVEN, INVENTORY_CUTOFF_UNRECONCILED, EVENT_COVERAGE_INCOMPLETE, PREVIEW_STALE, IDEMPOTENCY_CONFLICT, REPORT_FORMAT_UNSUPPORTED. Tests: null/zero/bool, Decimal, точные даты/зоны, fake source-proof отказ.

**FL03 — schema v13 и cipher.** Зависимость: FL02.
Добавить заданные таблицы/ограничения/индексы, migration 12→13 и общий доступ к существующему ключу для lookup references. Ни credentials, ни FIFO существующей истории не перезаписывать. Tests: новая DB, upgrade 12, partial-DDL rollback, future-schema refusal, чужой tenant, отсутствие ключа. Обновить ADR 066 как расширение, не альтернативную architecture.

**FL04 — repository commands.** Зависимость: FL03.
Реализовать append/read/CAS/idempotency для case и evidence. Case revision независима от действующего FIFO stream. Квоты: 20 незавершённых случаев на store, 100 declarations на case, 2000 observations на case; лимит не удаляет audit и не разрешает частичную запись. При превышении — понятный отказ и сохранённое предыдущее состояние.

**FL05 — хранение до FIFO и аварийные границы.** Зависимость: FL04.
Доказать: case с новой стоимостью сохраняется при queue_initialized=False, после restart возобновляется; при этом read_cost_mode_status/legacy/history/фактическая прибыль неизменны. Fault injection внутри каждой записи, конкурентный CAS, один idempotency key с разными payload. Зелёный targeted profile.

### Модуль B — новая партия и поставки (FL06–FL11)

**FL06 — полная стоимость без выдуманных компонентов.** Зависимость: FL05.
TOTAL_LANDED/COMPONENTS проходят одинаковый amount contract. Старые component rows читаются без миграционного переприсвоения. Тест 14.65 total сохраняет null-разбивку, экспорт и consumers не показывают purchase=14.65 плюс якобы нулевые остальные расходы.

**FL07 — application service случая.** Зависимость: FL06.
Создание/редактирование/отмена append-only case; фиксировать old cost, new cost, отправку, старый дом/транзит и unknown новую домашнюю партию. Нельзя автоматически выставлять cutoff/применение по dispatch_date. Два активных конкурирующих перехода одного SKU явно конфликтуют; черновики других SKU не подхватываются.

**FL08 — список конкретных поставок.** Зависимость: FL07.
Сохранять typed supply ID и шифрованный lookup, количество по каждой и общую owner сумму. Незакрытый остаток суммы показывается как «не распределено по поставкам», без виртуального supply ID. Тесты: дубликат, same ID другого store, смешанный SKU, orders/supplies/acts не взаимозаменяемы, 3 synthetic declarations 6234+600+148=6982.

**FL09 — наблюдения и временно отсутствующие данные.** Зависимость: FL08.
Добавить отдельный collector active supply и append observations. При исчезновении 148 на RECEIVING durable declaration остаётся, количество не обнуляется, confirmed receipt не создаётся. Пропажа после известной partial receipt тоже не откатывает receipt. Unknown status не фильтровать молча.

**FL10 — частичная приёмка и исправления.** Зависимость: FL09.
Дедуплицировать акты и кумулятивные наблюдения; поддержать 40→70→100, повтор страницы и корректировку. Accepted меньше declared после финального акта создаёт discrepancy, а не автоматическое списание: вывести количество и требуемое подтверждённое движение. Отмена/перенаправление не удаляют cost link. При акте другого SKU — конфликт без inventory write.

**FL11 — общий бюджет и возобновление.** Зависимость: FL10.
Checkpoint и source update привязать к case/owner/store/SKU/revision. Один 20s/10-attempt budget на весь шаг, включая details, acts и retry. PARTIAL сохраняет достигнутый прогресс, а не complete. Tests: timeout,429,broken page,repeated cursor,restart и смена магазина.

### Модуль C — документы и сверка (FL12–FL17)

**FL12 — parser оборотной ведомости.** Зависимость: FL05.
Read-only normalized evidence по разделу 6. Различать продажу775 и непродажное выбытие5, не выдавать итог3712 за физический остаток. Валидировать нужный SKU, общий контроль, период и отсутствие повторных итогов. Синтетическая XLSX fixture воспроизводит проверенные labels и значения без реальных ID/названий.

**FL13 — parser управления остатками.** Зависимость: FL12.
Дать все отдельные buckets и признаки FBS returns, отдельные totals/checks по складам. Тест:1191=1182+9,18 preparing,5 checking,41 removed отдельно. Не складывать пять разных представлений одного SKU. reserved остаётся unknown, если в файле нет независимого поля.

**FL14 — импорт в выбранный case.** Зависимость: FL13,FL07.
Добавить контекстную документную маршрутизацию, bounded worker, preview → явное подтверждение evidence. Import failure/stale ticket не закрывает другой действительный draft. Старый CSV preview/confirm и все навигационные fixes #726 проходят. XLSX без выбранного case даёт безопасную инструкцию, ничего не записывает.

**FL15 — сверка поставок.** Зависимость: FL11,FL14.
Чистый reconciliation service строит declared/observed/accepted/pending/discrepancy отдельно. На контрольном случае объясняет148 RECEIVING owner-linked,600 source-planned и6234 source-in-transit; не называет все6982 принятыми или однородно API-подтверждёнными. Разные as_of не «схлопываются» в атомарный снимок.

**FL16 — proposal начального среза.** Зависимость: FL15.
Для uninitialized FIFO предложить owner-review opening по доказанным buckets и дате, отдельно перечислить buyer deliveries, returns и нераспределённые движения. 4492/3712/1191 не становятся opening stock одним присваиванием. Preview не меняет режим расчётов. Старый дом/транзит0 принимаются как отдельные owner facts.

**FL17 — readiness и очередь уточнений.** Зависимость: FL16.
Детерминированная таблица missing requirements: нет списка supplies; нет периода06–07.11; неизвестен reserved/overlap; нет bridge продаж; конфликт акта; source lag. UI показывает конкретно требуемый документ/поле и уже сохранённое. Отчёт до05.11 не объявляет complete_through=07.11. Случай остаётся сохранённым AWAITING_EVIDENCE.

### Модуль D — восстановление и применение (FL18–FL23)

**FL18 — bridge источников.** Зависимость: FL17.
Реализовать раздел5.5 отдельным pure service и типизированными proof references. Подключить только allowlisted source adapters с установленной семантикой. Не ослаблять sale normalizer. Положительный путь проходит настоящие parser/normalizer/validator через production factory; тест не может напрямую подставлять readiness=True.
Если текущий API не доказывает дату, поддержать документальный evidence input для exact posting/SKU/date/quantity и его отдельное подтверждение, либо оставить конкретный участок закрытым. Общие суммы Excel не заменяют posting evidence.

**FL19 — безопасная начальная активация.** Зависимость: FL18.
Случай может получить полный opening proposal и новую ставку без прежнего manual anchor. До общего commit это только proposal. Неизвестный размер новой закупки дома не мешает сохранить ставку, но не даёт неограниченный физический запас. Принятые supply quantities не добавляются повторно поверх уже покрытого opening/transit.

**FL20 — детерминированный replay.** Зависимость: FL19.
Расширить существующий kernel/replay для одного позднего перехода и дальнейших обычных ставок. Совпадающие dates и unknown порядок блокировать только там, где это влияет на результат. Повторные финансовые строки не создают физическую продажу. Перестановка запросов отчётов не меняет распределение.

**FL21 — возвраты и другие выбытия.** Зависимость: FL20.
Устранить blanket отказ по наличию любого возврата/withdrawal: обработать точно связанные supported события через существующие return/non-sale services. Неизвестный/непривязанный возврат остаётся отдельным blocker. Первоначальная стоимость возвращённой единицы сохраняется; existing Return COGS authorization не обходится. Withdrawal не становится проданной единицей или advertising denominator.

**FL22 — влияние на периоды.** Зависимость: FL21.
Расширить текущий impact service: before/after units, COGS, tax,profit по затронутым финансовым периодам и полному зависимому горизонту. Использовать canonical TaxService с текущей политикой, в том числе USN income-minus-expenses. Физическая дата задаёт FIFO order, финансовая дата — признание по текущим правилам. Без достоверного before нельзя показывать выдуманную delta: объяснить, что доступна только candidate COGS.

**FL23 — атомарное применение и восстановление после сбоя.** Зависимость: FL22.
Реализовать commit_transition_case по разделу5.6, используя подготовленный replay и те же доказательства. CAS повторно внутри транзакции. Не оставлять «ставка уже применена, replay потом». Crash tests до/после каждого write; повтор confirm возвращает тот же результат; новый idempotency payload конфликтует. READY preview с изменившимся отчётом/налогом/stock/return не применяется.

### Модуль E — пользовательский путь и потребители (FL24–FL29)

**FL24 — доступ до настройки FIFO.** Зависимость: FL07,FL17.
В FIFO карточке без очереди добавить «📦 Новая партия уже отправлена» и «🗂 Незавершённые изменения». Сохранить старые начальные/нулевые действия с прежними guards. При zero-start с реальным товаром в пути — отказ. Не прятать late entry за queue_initialized.

**FL25 — возобновляемый мастер.** Зависимость: FL24,FL11,FL14.
Шаги: режим TOTAL/COMPONENTS → старая стоимость при неизвестной basis → новая стоимость → dispatch date → old home/transit → known shipped total → supplies → документы → summary. После подтверждения каждого смыслового блока сохраняется durable revision. Неизвестный новый home не спрашивать как обязательное число. Прерванный ввод возобновляется после restart; текст из другого магазина/формы не сохраняет этот case.

**FL26 — разные подтверждения.** Зависимость: FL25,FL23.
Кнопки строго различимы: «Сохранить сведения о партии», «Обновить данные поставок», «Добавить отчёт», «Проверить готовность», «Посмотреть пересчёт», «Применить подтверждённую историю», «Отменить изменение». Финальная кнопка недоступна без READY, но отсутствие кнопки не единственная проверка — сервер проверяет всё повторно. Preview показывает provenance, дату, старые слои, новую стоимость, missing values, влияние и пределы покрытия.

Использовать существующий Telegram sender с разбиением длинных сообщений; callback payload ≤64 байт, содержит opaque ticket, не input/ID поставки. Разметку и filenames экранировать, клавиатуру подтверждения связывать с точным preview и не дублировать на всех частях длинного сообщения.

**FL27 — текущая экономика и планы.** Зависимость: FL26.
Case draft не меняет current cost, кеши или сохранённые планы. APPLIED инвалидирует связанные текущие кеши по точной cost/allocation revision. FIFO next-unit остаётся21, пока есть старый слой; затем14.65. TOTAL_LANDED корректно отображается без фиктивной разбивки. Старые планы остаются frozen, новый расчёт получает новую basis.

**FL28 — фактическая прибыль и диапазон через cutoff.** Зависимость: FL27,FL22.
Подключить полный bridge/allocation в Period Profit. Проверенный pre-cutoff legacy и post-cutoff FIFO допускается объединить только при полном разбиении и согласованных источниках; иначе явная неполнота без тихого fallback. Экспорт/объяснение показывают одну и ту же revision. Доставленная после cutoff старая посылка получает21 без второго расхода opening.

**FL29 — история, отмена, обновление.** Зависимость: FL28.
Различать draft, неготово по данным, подтверждаемый preview, применено и отменено. Отмена не удаляет evidence. APPLIED исправляется новой revision/case, не UPDATE суммы. Экспорт history bounded и без raw lookup IDs. История после restart совпадает. Последующие async refresh не меняют уже подтверждённый preview задним числом.

### Модуль F — приёмка, документация и передача (FL30–FL35)

**FL30 — вся числовая матрица.** Зависимость: FL29.
Все случаи companion-документа прогоняются через kernel, repository и минимум два end-to-end UI tests. Ожидания считать независимо от SUT, не копировать его результаты. Обязательно проверить полный путь с initialized=False, in-flight declarations и позже появившейся полной доказательной базой.

**FL31 — изоляция, навигация и лимиты.** Зависимость: FL30.
Owner/store/SKU isolation, исторические aliases, source fingerprint conflict, оба типа money inputs, wrong-store callbacks, stale confirmation, race two confirms, /start, новый CSV, переключение из калькулятора, ReturnInventory и external expense. Malicious ZIP/XML, formulas, duplicate headers, нет SKU, скрытые лишние sheets, repeated page/act. Никакой тест не читает Downloads владельца или реальную DB.

**FL32 — migration/backup/restart.** Зависимость: FL31.
Round-trip normal backup/restore со случаями DRAFT/AWAITING/APPLIED, encrypted supply lookup и схемой13. Ошибка ключа не превращается в «поставка отсутствует». Restore не создаёт повторные движения. Совместимость старыхv12 и plan snapshots сохраняется. Изоляция от общей working data проверяется manifest до/после.

**FL33 — руководство и приемка владельцем.** Зависимость: FL32.
Обновить docs/fifo-cost-history-user-guide.md, FIFO_COST_OWNER_ACCEPTANCE, CURRENT_STATE, TEST_MAP, CHANGELOG, DECISIONS/066. Добавить точную последовательность для данного случая, список недостающих документов и безопасную краткую диагностику по кнопке. Не требовать API key, Client ID, raw JSON, платную подписку или Python-команды владельца. Код и реальная приёмка имеют разные статусы.

**FL34 — полный CI последней головы.** Зависимость: FL33.
Targeted tests, compileall и diff-check; полный pytest; Verify на Windows/Linux и production Docker build/runtime smoke на последнем SHA каждой сдаваемой ветки. Не менять реальные data/*.json/tenant DB ради tests; все stateful fixtures во временной папке, реальные исходные файлы сохраняются побайтно. Старый зелёный SHA не является проверкой нового кода. Нельзя массово deselect/skip известных регрессий для зелёного CI.

**FL35 — независимый review package.** Зависимость: FL34.
Сдать PR(s), точные base/head SHA, ссылки CI, changed-files map, архитектурные решения, migration/rollback, числовую матрицу, результаты data integrity и список ограничений по данным. Сравнить ТЗ с implementation function-by-function, включая положительный путь commit. Не называть USER_VALIDATION_PENDING дефектом кода, но и не называть реальный случай применённым. Обновить Resume и конечный stage table. Не merge, не deploy, не запускать реального бота.

## 8. План PR и автономное выполнение

Три небольших зависимых PR:
1. FL00–FL11: foundation/case/supply evidence без подмены действующих UI и финансовых расчётов.
2. FL12–FL23: reports/bridge/replay/atomic apply, base — точная голова PR1.
3. FL24–FL35: UI/consumers/acceptance, base — точная голова PR2.

Каждый PR должен иметь зелёный CI своей текущей головы. В handoff указать как проверить стек относительно main. Если предыдущий PR уже слит другой моделью — переносить зависимую ветку обычным безопасным Git workflow, не переписывая чужие изменения. Один PR на десятки тысяч строк не создавать.

Начать с FL00, выполнять зависимости автономно. После каждого этапа записывать: implemented files, tests/commands и фактический результат, SHA, source-data readiness и следующий шаг. Журнал — LUNA_FIFO_LATE_ENTRY_COMPLETION_PROGRESS_2026-11-07.md. После сокращения контекста читать Resume, git status и последние проверки, не начинать заново.

Не останавливать всю работу из-за отсутствия реального отчёта06–07.11: выполнить независимые этапы и positive synthetic acceptance. Если для реального применения не хватает источника — сохранить конкретный незакрытый gate и owner acceptance request. Если реализация положительного пути невозможна без нового неутверждённого бизнес-правила, описать точную развилку и остановить только зависимую работу, продолжив остальное.

Запрещено: merge/deploy, запуск реального бота, реальные Ozon/Telegram HTTP, чтение .env/ключей ради tests, загрузка личных отчётов в Git, destructive Git, очистка общих временных папок, перезапись data из Git без побайтной копии, предположения вместо неизвестного количества.

## 9. Definition of Done

- [ ] Все FL00–FL35 имеют фактические результаты, а не только отметку «сделано».
- [ ] Ввод pending новой партии работает до начальной FIFO и переживает restart.
- [ ] Полная себестоимость сохраняется без выдуманной разбивки и неизвестной домашней партии.
- [ ] Исчезающие148 не превращаются в0, закрыт manifest контроль6982 с реальными связями либо явными missing refs.
- [ ] Документы дают provenance и раздельные buckets; даты/количества не домысливаются.
- [ ] Положительный bridge/replay/impact/atomic apply доступен через production UI wiring.
- [ ] При неполных данных именно применение закрыто, сведения и работа владельца не теряются.
- [ ] Готовый код не содержит глобального выключателя factual gate или ложной source-complete галочки.
- [ ] Историческая прибыль, возвраты, withdrawals, налоги, current/planned economics и frozen планы проверены.
- [ ] Импорт, миграция, безопасность, конкурентность, restart, backup/restore и latest-head CI пройдены.
- [ ] Финальный пакет годится для независимого review; реальные данные не применены автоматически.

## 10. Команда запуска для Luna

Выполняй project_brain/LUNA_FIFO_LATE_ENTRY_COMPLETION_TASK_2026-11-07.md. Начни с FL00 и двигайся по зависимостям до FL35. Следуй зафиксированным контрактам, бизнес-правилам, числовой матрице и плану трёх зависимых PR. Сохраняй существующие изменения и данные. После каждого этапа обновляй журнал и фактические результаты проверок; после сокращения контекста продолжай по Resume. Работай автономно до необходимого бизнес-решения или неустранимого блокера. Не откладывай независимую реализацию из-за ещё не опубликованных отчётов владельца. Заверши на готовых PR с зелёным CI текущих SHA и пакетом независимого review. Слияние, развёртывание, реальные Ozon/Telegram-запросы и запуск бота не выполняй.

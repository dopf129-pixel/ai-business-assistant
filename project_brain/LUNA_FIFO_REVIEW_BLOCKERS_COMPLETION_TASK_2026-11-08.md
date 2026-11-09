# ТЗ для GPT Luna: завершить FIFO replay и production-путь применения

Подготовлено: 08.11.2026; редакционная проверка: 09.11.2026. Этапы FR00–FR31. Статус исполнения и Resume: в [журнале этапов](LUNA_FIFO_REVIEW_BLOCKERS_COMPLETION_PROGRESS_2026-11-08.md); FR00–FR16 завершены, следующий этап FR17.

Продолжает [FL00–FL35](LUNA_FIFO_LATE_ENTRY_COMPLETION_TASK_2026-11-07.md) и [Decision 066](DECISIONS_066.md). Это исправляющее задание для двух незакрытых замечаний review. Архитектура, алгоритм, бизнес-правила и критерии приёмки ниже зафиксированы. Luna реализует их небольшими изменениями; новый способ учёта не выбирает.

Журнал: [LUNA_FIFO_REVIEW_BLOCKERS_COMPLETION_PROGRESS_2026-11-08.md](LUNA_FIFO_REVIEW_BLOCKERS_COMPLETION_PROGRESS_2026-11-08.md).

## 1. Обязательный результат

1. Последовательные обычные изменения себестоимости после позднего перехода поддерживаются одним детерминированным replay. Остатки прежних партий сохраняются; ставка действует только после доказанной временной границы; возвраты сохраняют исходную стоимость.
2. Пользователь проходит через production assembly весь путь: сохранённые сведения и документы → доказанный cutoff/bridge → фактический предпросмотр COGS/налога/прибыли → отдельное подтверждение → атомарный commit → чтение результата после restart.
3. Положительный сценарий проходит реальные parser/normalizer/validators, application services, repository и Telegram routing. В acceptance-тестах заменять только HTTP-транспорт, часы, доставку Telegram и пути хранения. Fake READY/bridge/impact вместо полной цепочки не доказывает выполнение задания.
4. При нехватке доказательств сведения сохраняются; применение закрывается с конкретным недостающим полем, периодом и действием. Unknown не превращается в ноль.
5. Сдать готовые PR с зелёным CI текущих SHA и пакетом независимого review. Не merge, не deploy, не делать реальные Ozon/Telegram-запросы, не запускать реального бота.

Результат «сервисы есть, production wiring намеренно не подключён» не принимается. Зелёные isolated unit tests не заменяют работающий пользовательский путь.

## 2. Исходное состояние

Проверено при подготовке ТЗ:

| Объект | Состояние |
|---|---|
| Worktree | C:\Users\gelashvilee\.codex\worktrees\daily-readiness-foundation\Ai ассистент |
| Ветка | codex/fifo-late-entry-integration-20261107 |
| HEAD | 0de5522d162b70c569d9272b8e217f524bd4ff67 |
| PR #728 | Открыт; head 5b4f85881301b8d5b4a7977d67fa59e13d2647db; base main d8d4ba00c85acf14ba9a960f56a755fbe30b555c |
| PR #729 | Открыт; head 7abf5d79d608bf377f79df3b425b50d73de4d81c; base — ветка #728 |
| PR #730 | Открыт; head совпадает с HEAD выше; base — ветка #729 |
| Dirty corrections | 17 modified tracked-файлов кода/тестов/документации, ещё без commit |
| Локальные зависимости | Untracked .fl12-deps/; сохранить и не stage |
| Проверки локальных исправлений | 110 targeted; 5115 full Windows pytest во временном worktree, 61.10s; compileall/diff/data PASS |
| CI опубликованной головы #730 | Verify 42481955680 на 0de5522d PASS; dirty corrections им не проверены |
| Merge readiness | NOT READY: R-A/R-B открыты, CI нового кода отсутствует |

Это снимок, а не разрешение перезаписать последующие изменения. FR00 заново проверяет refs и dirty state.

Сохранить локальные review corrections:

- schema v15: отдельное append-only подтверждение периода уже импортированного файла;
- точная проверка origin/количества возврата и non-sale movements;
- READY после restart открывается read-only;
- historical finance SKU требует seller-confirmed mapping точного товара;
- первая обычная смена стоимости после late entry проверяет действующий replay;
- одинаковые инъецированные часы repository/service в lifecycle regression.

Tracked baseline: CHANGELOG; fifo_cost_cutoff_bridge_service; fifo_cost_repository; fifo_cost_transition_store; telegram_fifo_cost_report_import_service; telegram_fifo_cost_transition_runtime_service; CURRENT_STATE; independent review packet; прежний FL-progress; TEST_MAP; семь соответствующих изменённых test-файлов. Снять полный список/diff в FR00. Новые TASK/PROGRESS и ссылки на них также сохранить.

Не использовать reset --hard, git clean, массовые restore/stash, force push, удаление worktree с несохранённой работой. Не менять реальные data/. Не копировать .env/credentials/owner DB/Downloads в fixtures или PR.

## 3. Причины, которые надо закрыть

### R-A: нет production-пути применения

- telegram_assistant_factory.py не подключает сборщик bridge evidence и apply_service.
- FifoCostTransitionReviewService.assess() передаёт cutoff_bridge=None.
- FifoCostTransitionReadinessService всегда возвращает ready_to_apply=False.
- prepare_transition_preview/commit_transition_case вызываются тестами repository, но не рабочим пользовательским путём.
- FifoCutoffBridgeDocumentParser/FifoPhysicalSaleDocumentConfirmation существуют без полноценного durable import/confirm/reconstruction в UI.
- Cutoff/opening composition/semantics нельзя получать из process-memory fake или неподтверждённого параметра функции.

### R-B: replay нескольких ставок отсутствует

- _preview_allocation_from_connection читает максимум две active rate rows и отказывает при нескольких ставках либо existing+hypothetical.
- Replay/kernel поддерживают одну open rate.
- rate_reconciliations содержит остаток прежней ставки на границе, а не размер всей закупленной партии.
- preview_cost_rate_change запрещает уменьшение total относительно прошлого snapshot даже при объясняющих продажах.
- Новый доказанный rate change должен атомарно публиковать rate+replay. Применить ставку, а полный replay оставить «на потом» недостаточно.

Снять count-only guards или поставить latest cost на всю историю запрещено.

## 4. Неизменяемые бизнес-правила

1. FIFO scoped по owner/store/product/offer/current SKU. Finance aliases сохраняют отдельные immutable sale identities.
2. Себестоимость относится к продаваемой упаковке. TOTAL_LANDED — одна сумма, components=null; COMPONENTS — действительная разбивка.
3. Неизвестное количество новой партии дома разрешено сохранить; это не физический неограниченный запас.
4. Open rate — цена при неизвестном количестве закупки. Она оценивает наблюдаемую подтверждённую sale после finite layers, но не увеличивает known_quantity. Non-sale outflow требует finite basis.
5. Transit/receiving не считаются acceptance. Исчезнувшие 148 не превращаются в ноль. Act quantities не прибавляются повторно поверх покрытого opening/transit.
6. Dispatch/status_updated/captured_at/act_created_date не назначаются physical sale/receipt/cutoff автоматически.
7. Cutoff descriptor содержит timezone/precision/boundary. Новый date-only путь использует доказанный END_OF_LOCAL_DATE магазина: события этой местной даты до границы, следующего дня после. UTC-дата timestamp не заменяет local date.
8. Старую запись без boundary evidence не переинтерпретировать. Новый полный multi-rate расчёт без доказанной границы возвращает FIFO_RATE_BOUNDARY_UNPROVEN. Старые frozen reports/plans сохраняются.
9. Owner факт имеет owner provenance. Confirm не доказывает неизвестную семантику/пагинацию API.
10. Physical date задаёт FIFO order; financial recognition — period profit/tax. TaxService и Return COGS authorization сохраняют свои ответственности.
11. Return восстанавливает исходную cost basis, но не автоматически признаёт Return COGS в прибыли.
12. Owner-approved partial-return costing: when source evidence links a return to the sale but not to an individual unit, assign returned units to the latest original FIFO allocation lines first. Earlier partial returns consume that latest-first capacity before later returns. This is a deterministic costing convention, not physical-unit evidence. A full-sale return preserves original allocation order.
13. Пересчёт создаёт новую allocation revision. Applied preview/evidence/saved plans не переписываются.
14. Реальный случай владельца остаётся USER_VALIDATION_PENDING/SOURCE_BLOCKED до собственной сверки. Недостающие реальные документы не блокируют synthetic implementation.

## 5. Фиксированная архитектура и контракты

### 5.1. Ответственности

| Компонент | Обязанность |
|---|---|
| FifoCostRepository/TransitionStore | Единственный tenant FIFO SQL/migration/CAS/append-only authority |
| FifoCostAllocationService | Один чистый kernel, расширяемый rate-boundary events/finite balances |
| FifoCostReplayService | Доказанный temporal order events+boundaries, вызов того же kernel |
| FifoCostTransitionService | Typed case lifecycle и публичное сохранение evidence |
| Новый FifoCostTransitionEvidenceService | Read-only сборка typed immutable CaseEvidenceBundle из сохранённых inputs, без HTTP/write |
| SourceCollectionService | Bounded read-only IO/continuation; возвращает evidence, не READY |
| ReviewService | Read-only readiness по bundle и настоящему bridge |
| Новый FifoCostTransitionApplyService | prepare/read_preview/apply orchestration через существующий atomic repository |
| LateEntryImpactService | Единственный before/after adapter с TaxService/frozen financial summaries |
| Telegram runtime/import/adapter | Owner inputs, context, отдельные confirm, missing/impact UI; без своего SQL/формулы прибыли |
| telegram_assistant_factory.py | Одна общая production assembly |

Не вводить вторую БД/ledger/FIFO engine, competing framework, scheduler, новую формулу прибыли. Pure helpers допустимы как декомпозиция этих сервисов, не параллельный authority.

Новые файлы реализации зафиксированы: app/services/fifo_cost_transition_evidence_service.py, app/services/fifo_cost_transition_apply_service.py и app/services/fifo_cost_physical_sales_import_service.py. Новые typed evidence DTO добавляются в существующий fifo_cost_transition_contracts.py; parser physical rows переиспользуется из fifo_cost_cutoff_bridge_service.py. Worker dispatch расширяется явным разрешённым parser kind. Основные новые acceptance/regression файлы: tests/test_fifo_cost_temporal_rate_replay.py, tests/test_fifo_cost_transition_evidence_service.py, tests/test_fifo_cost_transition_apply_service.py, tests/test_fifo_cost_physical_sales_import_service.py, tests/test_fifo_cost_transition_production_workflow.py. Имеющиеся test-файлы миграции, rate service, Telegram и backup расширяются по месту.

### 5.2. Temporal rate-boundary algorithm

Добавить FifoRateBoundaryEvent в allocation module и dated envelope в replay:

- event_id, new_rate_change_id, new_unit_cost_rub;
- previous_rate_change_id, nullable только для первой open rate;
- previous_rate_remaining_units и expected_older_finite_units, nullable только для первой ставки;
- reconciliation_evidence_fingerprint;
- boundary descriptor/evidence reference в dated envelope; exact stream identity на уровне bundle.

Rate IDs — реальные либо детерминированные hypothetical proposal IDs. UI не задаёт trusted=True.

Kernel исполняет boundary в её хронологической позиции:

1. Первая ставка включает open rate за имеющимися finite layers, не добавляя единицы.
2. Следующая ссылается на текущую open rate. Сумма finite remaining, включая подтверждённые returns, точно равна expected_older_finite_units.
3. previous_rate_remaining_units — независимо доказанный остаток предыдущей open rate на границе. Проверить physical_total=older_finite+previous_rate_remaining.
4. Только этот residual превратить в finite balance в хвосте существующей finite очереди и включить новую open rate. Ноль допустим при доказанном нуле, null блокирует.
5. Не переносить residual в начало replay и не прибавлять к нему будущие продажи. Прошлые продажи уже оценены предыдущим состоянием.
6. Остальные finite units сохраняют стоимость/порядок; sales до boundary сохраняют свои basis IDs.
7. Materialized rate balance связан с rate_change_id и reconciliation evidence. Это derived balance, не новое receipt/закупка.
8. Registry всех rate IDs хранит происхождение basis. Return единицы, проданной через open rate, после её закрытия создаёт finite restored slice исходной стоимости в позиции возврата перед current open rate. Исходная cost basis не меняется.
9. Для возврата из исходного finite layer сохранить действующую политику существующего kernel; глобально менять порядок таких возвратов не требуется.
10. Non-sale outflow потребляет finite balances; неизвестный объём open rate не используется.

allocate(..., open_rate=...) сохранить совместимым wrapper для single-rate callers. Конкурирующие способы задания rates — input conflict.

Порядок определяется proof boundaries, не created_at/rate_sequence/ID. Existing cancellation guards сохраняются; отменённые rates исключаются. Нельзя предполагать previous active sequence=current-1: проверяется точная связь evidence. Поддержанные существующим cancellation contract cases должны проходить; новые способы отмены не добавлять в обход запретов.

Same-day sales используют прежний bounded анализ допустимых порядков. Разные boundaries на одной недоказанной позиции — conflict; exact idempotent duplicate — одна boundary. Лимиты events/order-analysis не снимать; exhaustion — incomplete.

### 5.3. Persistence

Следующая ожидаемая FIFO schema v16 после локальной v15. В FR00 проверить номер; занятый чужим изменением номер не переиспользовать. Planning schema/PRAGMA user_version не менять, существующие миграции не переписывать.

Добавить append-only tables в существующем repository:

1. fifo_cost_transition_bridge_evidence: evidence_id, case_id, scope/identity fingerprints, evidence_kind, schema_version, source_kind/fingerprint, evidence_revision, period_from/to или as_of descriptor, captured_at, completeness, payload_json, encrypted_payload, payload_fingerprint, idempotency_key, recorded_at.
2. fifo_cost_transition_evidence_confirmations: confirmation_id, case_id, exact evidence_id/fingerprint, confirmation_kind, typed confirmed fields, owner/scope fingerprint, expected_case_revision, payload_fingerprint, idempotency_key, confirmed_at.
3. fifo_cost_allocation_rate_balances: allocation_id, ordinal, rate_change_id, remaining_units, unit_cost_rub, reconciliation reference/fingerprint, original basis kind/reference, nullable origin_sale_event_id для restored slice.

FK/unique/indexes/immutability/quotas по действующим conventions. Required evidence kinds: PHYSICAL_SALES_DOCUMENT, FINANCE_IDENTITY_SNAPSHOT, MOVEMENT_COVERAGE, CUTOFF_SELECTION, OPENING_COMPOSITION, RATE_BOUNDARY_PROOF, PERIOD_SUMMARY_SNAPSHOT, TAX_POLICY_SNAPSHOT. У каждого typed validator/allowlist; generic JSON с trusted completeness запрещён.

Это evidence snapshots существующих источников, не новый финансовый ledger. v15 period confirmation остаётся отдельным и immutable. Physical rows/cutoff/opening подтверждаются отдельно и не мутируют исходный документ.

Зафиксированные лимиты новых записей: plaintext metadata payload не более 256 KiB; confirmation payload не более 64 KiB; один physical document не более 50 000 строк и 16 MiB ciphertext; aggregate encrypted evidence одного case не более 64 MiB и 100 document/snapshot versions. Полный выбранный identity/event set не превышает действующий replay limit 100 000. Превышение явно возвращает quota error, без обрезания строк или объявления частичного документа полным. Старые таблицы и их более строгие лимиты не расширять глобально ради нового импорта.

Подтверждение physical document относится ко всем его проверенным строкам. В confirmation payload хранить manifest: document fingerprint, row count и canonical hash отсортированного полного набора row references, а не повторять до 50 000 ссылок в 64 KiB. При reconstruction получить confirmed_row_references для существующего DTO из exact immutable document и проверить manifest. Частичное выделение строк пользователем в это задание не входит; файл с неизвестными датами целиком не подтверждается.

Raw posting/supply references и чувствительные точные lookup/rows шифруются существующим tenant Fernet provider. Plaintext — только разрешённые digests/quantities/periods/provenance. Ciphertext/raw rows не выводить в logs/exports. Missing/wrong key сохраняет несекретные сведения и blocker; plaintext fallback запрещён.

Публичные keyword-only repository methods: append_transition_bridge_evidence, confirm_transition_evidence, read_transition_bridge_evidence, read_transition_preview. Scope берётся из tenant context; SQL helpers не коммитят внешний transaction.

evidence_set_fingerprint включает выбранные versions+confirmations+aliases+boundaries+reports+movements+opening+finance/period/tax. Другое store/case не взаимозаменяемо. Hash рассчитывать из проверенного содержания; owner-provided hash и новое время чтения не доказательства.

### 5.4. Physical-sale document input

Фиксированный новый источник — собственный CSV-шаблон бота, явно OWNER_IMPORTED, не «официальный отчёт Ozon». Произвольный XLSX универсально не распознавать.

UTF-8 CSV, optional BOM, delimiter ;, header в точности:

posting_number;finance_sku;quantity;physical_effective_date;row_reference

Дата YYYY-MM-DD; quantity целое>0 в текущих лимитах; row_reference уникальная безопасная ссылка на строку источника. Period_from/to, timezone, смысл PHYSICAL_OUTFLOW и источник сведений вводятся/показываются отдельно. Finance accrual/payment/order-created date не заменяет physical outflow.

Flow:

1. Точный case/store/SKU и action «Добавить подтверждение продаж». Legacy cost CSV этим parser не перехватывается.
2. Parser проверяет bytes/hash/header/encoding/columns/quoted fields/quantity/date/row refs/identity duplicates и конфликты.
3. Preview показывает row/unit counts, период, source provenance, смысл confirm, без raw posting IDs.
4. «Сохранить документ» сохраняет evidence. Отдельное «Подтвердить сведения документа» связывает exact hash/rows/period/semantics/identity/revision. Неподтверждённый документ не открывает apply.
5. Текст просит подтверждать только действительно известные физические сведения. Предзаполненные даты из финансовых отчётов запрещены.
6. Restart восстанавливает parser-compatible document+confirmation из repository.

Использовать существующий worker: до 10 MiB файла, 50 000 строк, 15s hard deadline и прежняя общая ёмкость. Лимиты контролируются при чтении. NUL, лишние поля и некорректные units отклоняются; formulas не исполняются; spreadsheet exports экранируют formula prefixes.

Один список строк не доказывает полное physical coverage. Assembler сверяет полный finance identity set, documentary periods, turnover controls, pre/post-cutoff partition и movements. Missing row/date/неразобранный buyer-delivery/return bucket — blocker.

Movements переиспользуют typed return/non-sale services: exact origin identity/date/units/reason. Документальный coverage допускается только с явным периодом и независимой сверкой контрольных движений. Пустой список из заглушки или галочка не доказывают отсутствие movements. API pagination flags не создавать для OWNER_IMPORTED.

### 5.5. CaseEvidenceBundle и источники

EvidenceService.load(case_id, identity, expected_case_revision) возвращает immutable typed bundle либо missing/conflict. Bundle содержит case basis, reports/period confirmations, supply declarations/observations/acts, stock semantics/cutoff/opening confirmations, finance identities с confirmed aliases, physical document с confirmation, movement coverage, complete-through/fingerprints.

Выбираются согласованные versions по bindings/supersedes/owner selection. Конфликт не решается «последним временем». source_as_of и captured_at раздельны. complete_through — общий доказанный конец обязательного покрытия, не максимальная дата одного отчёта. Отчёт до 05.11 не покрывает 06–07.11.

Assess/reconstruction/confirm не делают скрытых HTTP. Обновление источников — отдельная явная кнопка с сохранением progress. Общий budget на UI шаг: 20s, 10 actual HTTP attempts, 2 pages, retry внутри. Opaque continuation с TTL bound к case/store/SKU/source/revision.

Finance collector использует BaseOzonClient.get_realization_posting и настоящий CutoffBridgeSourceAdapter. Missing fields дают source-format blocker. Historical alias проверяется по durable seller mapping; строка не теряется. Месячный источник не доказывает полноту ещё не опубликованного периода. Удалённый /v3/finance/transaction/list не использовать.

Новые Ozon endpoints не угадывать. Если нужны semantics, сверить official docs и записать source audit. Во время задания никаких реальных seller API вызовов; synthetic raw responses проходят настоящий adapter.

Cutoff/opening — отдельные durable owner confirmations. Переиспользовать existing initial-layer format cost/location/units. Суммы/disjointness сверяются против snapshot/bridge/acceptance, а не вычисляются из остатка owner shipment total. 6982 — отправлено по owner statement, не accepted.

### 5.6. Application API и N/N+1

FifoCostTransitionApplyService:

- prepare(case_id, identity, expected_case_revision, idempotency_key);
- read_preview(case_id, identity, preview_id);
- apply(case_id, identity, expected_case_revision, expected_preview_id, expected_preview_fingerprint, idempotency_key).

Owner/tenant из context. Telegram не передаёт готовые bridge/impact/ready flags.

prepare:

1. Перечитать case/evidence bundle точной revision.
2. Построить actual proposal/bridge, проверить coverage/stock/aliases/date/movements/owner opening.
3. Построить baseline/candidate тем же repository/kernel read-only. Uninitialized staging только SAVEPOINT с гарантированным rollback; business writes ещё нет.
4. Взять сохранённые полные financial summaries всех затронутых периодов и актуальную local tax policy.
5. Вызвать LateEntryImpactService с реальным reconstruction. Sale digest union и financial periods exact. Legacy before только из historical evidence, не mutable current cost.
6. Missing before -> candidate-only, без fabricated delta и без READY.
7. Полный before/after -> existing prepare_transition_preview сохраняет только preview+READY revision; FIFO/current cost/plans не меняются.

Существующий контракт: basis revision N, sealed READY revision N+1, bridge для N, commit ожидает N+1 и проверяет bridge N. Создать scoped reconstruction basis по seal; UI не обходит state check произвольным replace. Assess read-only; после настоящего seal не должен всегда сообщать ready_to_apply=False.

apply:

1. Проверить identity/READY revision/exact preview ID/fingerprint из confirmation ticket.
2. Перечитать sealed basis/selected evidence и current tax policy, перепроверить deterministic bridge/impact на тех же сохранённых версиях.
3. Изменившееся selected evidence/source/tax делает seal stale. Старой кнопкой нельзя применять «самый новый preview».
4. Existing commit_transition_case снова проверяет scope/revisions/evidence/tax/TTL/idempotency внутри BEGIN IMMEDIATE.
5. Одной транзакцией сохранить rate, initial cutover, events, rate balances, allocation/projection, cutoff mapping, audit, APPLIED. Ошибка откатывает всё.
6. Exact committed retry после restart возвращает тот же commit; changed payload+same key конфликтует. После scope/authorization проверка уже совершённого exact commit выполняется до повторной проверки изменившихся со временем источников/налога/TTL. Эти изменения не отменяют совершённый commit. Для новой неподтверждённой заявки все актуальные проверки обязательны.
7. Cache invalidation только после commit и по exact identity/revision; сбой invalidation не повторяет business writes.

Добавление нового документа к READY выполняется отдельным явным действием обновления сведений: append-only revision переводит case в AWAITING_EVIDENCE и сохраняет прежний seal как исторический. Текущий sealed preview не редактируется; старая кнопка становится недействительной.

HTTP/worker wait внутри write transaction запрещены. Часы repository/application одинаково инъецируются.

## 6. Числовая матрица

Synthetic controls не применяются к owner store. Все boundaries — Europe/Moscow, доказанный END_OF_LOCAL_DATE; продажи после boundary — на последующих днях, источники полны.

| ID | Вход | Ожидание |
|---|---|---|
| MR01 | Cutoff 06.11: finite 3×21 и 100×14.65; R1=14.65 на границе 07.11; sale 5 от 08.11 | COGS 92.30 = 3×21 + 2×14.65; finite remaining 98 |
| MR02 | Затем R2=16: stock 108, existing finite 98, residual R1=10; sale 110 после boundary | Материализовано ровно 10 residual; COGS 108×14.65 + 2×16 = 1614.20; finite 0, open R2 quantity unknown |
| MR03 | Затем R3=18: stock 7, finite 0, residual R2=7; sale 10 | Stock 108→7 допустим с полным bridge; COGS 7×16 + 3×18 = 166.00; aggregate MR01–MR03 = 1872.50 |
| MR04 | После MR03 return 1 из двух open R2 units продажи MR02 | По owner-approved latest-allocation-first convention finite restored unit 16 в позиции return; sales COGS сама не уменьшается |
| MR05 | Продать restored unit MR04 | COGS 16; aggregate 1888.50; origin lineage сохранена |
| MR06 | Независимая ветка от opening MR01: outflow 1 из слоя 21, затем sale 5 | Outflow 21 отдельно; sales COGS 2×21 + 3×14.65 = 85.95 |
| MR07 | Finite 0, open 14.65; подтверждённая sale 4 после boundary | COGS 58.60; known physical quantity остаётся unknown; outflow без finite proof blocked |
| MR08 | Same local date sale и END_OF_LOCAL_DATE boundary | Sale до boundary; timestamp сначала в timezone магазина |
| MR09 | Разные boundaries на недоказанной одинаковой позиции / missing reconciliation | Конкретный order/history blocker; zero business writes |
| MR10 | Duplicate page/row/confirm; переставлены raw pages | Одна sale identity, одинаковый semantic allocation/fingerprint, один commit |
| MR11 | Historical alias без mapping / другой offer/store | Explicit identity blocker, строка не отброшена |
| MR12 | COGS 105→92.30; revenue 1000, points 0, net 400; tax NONE | Profit 295→307.70, delta +12.70 |
| MR13 | Как MR12, points 200, USN_INCOME 6% | Tax 48→48; profit 247→259.70, delta +12.70 |
| MR14 | Как MR12, points 0, USN_INCOME_MINUS_EXPENSES 15%, minimum 1% | Tax 44.25→46.16; profit 250.75→261.54, delta +10.79 с canonical rounding |
| MR15 | Revenue 1000, points 0, net 110, COGS 105→92.30; УСН доходы−расходы 15%, minimum 1% | Tax 10→10; profit −5→7.70, delta +12.70 |
| MR16 | Before не подтверждён | Candidate COGS с ограничением; comparison delta/tax/profit unknown; нет READY/APPLIED |
| MR17 | Physical sale в ноябре, finance recognition в декабре; другой SKU в том же периоде | FIFO задаёт ноябрьский порядок, profit/tax — декабрьские; COGS другого SKU неизменна |
| MR18 | Pre-cutoff physical outflow 2×21, начисление позже | Legacy COGS 42 по exact mapping; opening второй раз не расходуется |
| MR19 | Новый selected report/tax/stock/return между preview/confirm | Старый seal stale, никакого partial apply |
| MR20 | Два concurrent confirms / exact retry после crash | Один commit; CAS conflict или exact idempotent result |
| MR21 | Wrongkey/tenant/expiry/stale callback после смены store/form | Evidence сохранено; apply blocked; другие drafts не потеряны |
| MR22 | Owner 21/14.65/6982/1191/1192/148, отчёт до 05.11 | Provenance сохранена, unknown/receiving не ноль, OWNER_CASE_VERIFIED=false |

MR01–MR05 выполнить на одной цепочке и новом repository/runtime instance после каждого шага. Проверять line-level IDs/units/costs, не только totals. MR14 использует реальный TaxService и независимые Decimal expected; TaxService ради результата не менять. Existing N01–N40 сохраняются.

Для единой цепочки зафиксировать R2 boundary 09.11, sale MR02 от 10.11, R3 boundary 11.11, sale MR03 от 12.11, return MR04 от 13.11 и sale MR05 от 14.11. Часы synthetic окружения установить не ранее полного конца 15.11; реальные часы и даты владельца не подменять. Source evidence покрывает каждый соответствующий интервал и финансовый horizon.

## 7. Этапы FR00–FR31

Каждый этап заканчивается небольшим коммитом и записью в журнале: изменённые функции, SHA, выполненные проверки, фактический результат и следующий шаг. При изменении поведения обязательны значимые регрессионные тесты. Статусы: NOT_STARTED, IN_PROGRESS, DONE, BLOCKED. Наличие файла не доказывает DONE. После нового коммита прежний CI не считается проверкой новой головы.

### Модуль A. Исходная точка и контракты

**FR00 — снять исходное состояние.** Зависимости: нет.

Прочитать AGENTS.md, CURRENT_STATE.md, DECISIONS.md/066, TEST_MAP.md, прежние FL-task/progress и review packet, это ТЗ. Проверить ветку, HEAD, базы PR и полный dirty diff, не выводя секреты. Снять список и hash исходных data/ и существующих изменений. Заполнить Resume и таблицу этапов. Сохранить новые TASK/PROGRESS и .fl12-deps/. Полный pytest из рабочего каталога владельца не запускать.

**FR01 — закрепить уже сделанные исправления.** Зависимости: FR00.

Изучить 17 изменённых tracked-файлов. Проверить целевые регрессии во временном хранилище; сохранить существующий staged state. Создать checkpoint-коммит по явному списку файлов, исключив data/, .fl12-deps/ и посторонние артефакты. Это ТЗ и журнал сохранить отдельным документационным коммитом. Не использовать git add -A. Дополнительную чужую работу перечислить и сохранить. Записать SHA исправлений как исходную точку дальнейших изменений.

**FR02 — воспроизвести оба дефекта.** Зависимости: FR01.

Добавить падающие проверки MR02–MR03 и недостающего production-пути: у фабрики нет apply dependency; assess не строит bridge; сохранённый physical document не достигает подтверждаемого preview. Проверять поведение, не наличие строки исходника. На старом коде проверки должны падать по указанным причинам. Постоянный skip/xfail не является исправлением.

**FR03 — зафиксировать DTO и числовые контроли.** Зависимости: FR02.

Создать FR03_CONTRACTS_2026-11-08.md: поля раздела 5, enum и коды ошибок, модель N/N+1, транзакции, план миграции, независимо рассчитанные MR-контроли. Decision 066 дополнить узким addendum о временных границах ставок и сохранённых доказательствах. Действующий source gate не ослаблять. Этот этап уточняет реализацию заданного дизайна, не открывает выбор другой модели учёта.

### Модуль B. Несколько ставок в существующем FIFO

**FR04 — типы временных границ.** Зависимости: FR03.

Добавить core/dated types раздела 5.2 и строгие проверки денег, количества, дат, timezone, identity и цепочки ставок. bool не считается количеством; null не превращается в ноль. Добавить FIFO_RATE_BOUNDARY_UNPROVEN, FIFO_RATE_CHAIN_CONFLICT, FIFO_RATE_BALANCE_MISMATCH, сохранив прежние error contracts. Проверить неверный ввод, дубликаты, другой scope и совместимость single-rate API.

**FR05 — расширить allocation kernel.** Зависимости: FR04.

Реализовать алгоритм 5.2, registry исходных rate bases и материализацию только остатка на границе, без событий фиктивной приёмки. MR01–MR07 проходят на чистых объектах без SQLite. Проверить неотрицательные finite balances, равенство stock на границе, unknown quantity у open rate, первоначальную стоимость возвращаемой единицы и отдельную оценку outflow. Прежние kernel tests должны проходить.

**FR06 — временная последовательность replay.** Зависимости: FR05.

Объединить boundaries и события по доказанному порядку с timezone магазина и существующим ограниченным анализом неоднозначностей. Не сортировать ставки по created_at. Проверить MR08–MR10 и перестановки сырых входов. Неполнота источников и исчерпание лимитов дают incomplete; использование последней цены для всей истории запрещено.

**FR07 — миграция FIFO.** Зависимости: FR03, FR06.

Новая миграция добавляет таблицы раздела 5.3, индексы, FK, immutable triggers и quotas. Проверить fresh DB и переходы v12/v13/v14/v15 к новой схеме, сохранение строк, связей и hashes. Planning schema и user_version не меняются. Внести ошибки на шагах миграции и доказать rollback. Сохранить v15 period confirmations. Проверить cipher failure и изоляцию tenant.

**FR08 — адаптер последовательности ставок в repository.** Зависимости: FR07.

В поддержанном пути убрать LIMIT 2 и count-only rejection. Загрузить ограниченный полный набор active rates/reconciliations и построить проверенную цепочку. Отменённые ставки исключаются; недостающая граница старой записи не угадывается. Преобразование allocation lines, validation, persistence, remaining reader и source fingerprint учитывают все historical rates и derived balances. MR02–MR05 проходят через repository.

**FR09 — обычное изменение себестоимости после late entry.** Зависимости: FR08.

Расширить preview_cost_rate_change и commit_cost_rate_change. Snapshot сверяется с prefix replay на выбранной границе, а не с остатком после будущих событий. Уменьшение stock допустимо, если объяснено полным bridge; необъяснённая потеря остаётся конфликтом. Полный доказанный путь сохраняет candidate seal и атомарно фиксирует rate, reconciliation, allocation и projection. Старые неполные сценарии не объявляются complete. Цепочка MR01 → MR02 → MR03 работает через публичные application methods без ручной SQL-вставки новых ставок.

**FR10 — возвраты и непродажные движения.** Зависимости: FR09.

Провести существующие ReturnInventory/non-sale services через temporal replay. Проверить частичный возврат по owner-approved latest-allocation-first policy, повтор, превышение исходного количества, origin из закрытой ставки, события до/после границы и неоднозначный день. MR04–MR06 и отрицательные сценарии сохраняют exact lineage, Return COGS authorization и исключение outflow из sales COGS. Blanket-отказ по наличию любого возврата запрещён.

**FR11 — потребители нескольких ставок.** Зависимости: FR10.

Current next-unit выбирает первый finite остаток либо последнюю доказанную open rate с unknown quantity. History/export не показывают residual как новую закупку. Period Profit читает одну полную allocation revision со всеми rate lines. Saved plans остаются frozen. Повтор replay и новые instances после restart дают тот же результат; stale projection не выдаётся за factual. Этот модуль завершить до подключения нового apply UI.

### Модуль C. Сохраняемые доказательства для bridge

**FR12 — typed bundle и evidence API.** Зависимости: FR07, FR11.

Реализовать разделы 5.3/5.5: ограниченные scoped reads/writes, CAS, idempotency и append-only invalidation READY при новых доказательствах. Historical basis читается только через scoped seal. Проверить повреждённый hash/payload, неверный ключ, другой tenant, отмену, restart и повтор confirm.

**FR13 — parser и шаблон physical sales.** Зависимости: FR12.

Реализовать CSV раздела 5.4 через существующий worker. Hash рассчитывается сервером по фактическим bytes и normalized fields; произвольный document_fingerprint не считается подтверждением. Добавить безопасный пустой шаблон и инструкцию. Проверить корректные fixtures, отсутствующие/конфликтующие строки, даты, units, encoding и лимиты. Не добавлять угаданные форматы Ozon XLSX.

**FR14 — отдельное durable подтверждение.** Зависимости: FR13.

Реализовать preview → сохранение документа → отдельное подтверждение semantics/rows. Binding содержит exact hash, period, timezone, source, scope и revision. Повтор того же файла не мешает отдельному confirm; v15 flow сохранён. Restart/wrong key не удаляют evidence. Неподтверждённый документ не открывает bridge.

**FR15 — маршрутизация документов Telegram.** Зависимости: FR14.

Подключить selection в SellerCostTelegramAdapter и FIFO runtime. Physical-sales CSV направляется в новый parser только после action выбранного case; legacy cost CSV сохраняет прежний маршрут. Ошибка, expiry и смена формы не закрывают другой draft. Tickets opaque, не длиннее 64 bytes, привязаны к identity/revision. Проверять размер до скачивания и лимиты worker при чтении. Реального бота не запускать.

**FR16 — ограниченный сбор источников.** Зависимости: FR12.

Добавить finance identity, period и movement snapshots к существующему collection path. Использовать настоящие normalizers, полную пагинацию и зафиксированную семантику, общий budget. Частичные результаты и continuation сохраняются без READY. 429, timeout, broken/repeated page дают missing evidence. Complete zero отличается от unavailable. Синтетические сырые HTTP-ответы проходят реальный adapter. Недостающую семантику не заменять hardcoded True; provider, всегда возвращающий unavailable даже на полном подтверждённом fixture, также не является реализацией.

**FR17 — ввод cutoff, opening и stock semantics.** Зависимости: FR14, FR16.

Добавить отдельные durable owner confirmations: cutoff descriptor; известные reserved/overlap правила со ссылками на evidence; opening layer composition. Переиспользовать текущий initial-layer format. Суммы и отсутствие пересечений проверяются против reports, acceptance и movement bridge. Cutoff из process memory не authority. Полный synthetic случай 3 old + 100 new подтверждается через public flow; реальные 6982 не превращаются в выдуманный opening.

**FR18 — evidence assembler и настоящий bridge.** Зависимости: FR15, FR16, FR17.

EvidenceService и ReviewService читают durable versions, создают реальные finance/document/confirmation/movement DTO и вызывают build_cutoff_bridge с actual proposal. None допустим только при конкретном missing requirement. API flags не хардкодить. Readiness различает missing, conflict, готовность построить preview и действующий READY seal; assess остаётся read-only. Свежие instances восстанавливают тот же bundle и результат.

### Модуль D. Impact, preview и финальное применение

**FR19 — публичная read-only reconstruction.** Зависимости: FR11, FR18.

Выделить безопасный repository seam для baseline/candidate до seal, переиспользуя существующие prepare helpers и kernel. Staging uninitialized queue всегда откатывается, включая ошибки и исключения. Candidate fingerprints совпадают с rebuild в prepare/commit. Результат содержит exact identities, revisions, lineage, COGS и покрытие без business writes.

**FR20 — финансовые summaries и baseline.** Зависимости: FR16, FR19.

Получить frozen summaries из существующей finance/Period Profit цепочки для всех затронутых финансовых периодов. Сохранить bindings/snapshots с financial recognition identities. COGS других SKU и прочие расходы не меняются. Historical before доказан; формула old cost × all sales не подменяет baseline. Missing baseline обрабатывается как MR16. Collection — отдельный ограниченный шаг без HTTP в prepare/confirm.

**FR21 — канонический impact.** Зависимости: FR20.

Передать реальный reconstruction в LateEntryImpactService. Проверить MR12–MR18, NONE, USN_INCOME, USN_INCOME_MINUS_EXPENSES, minimum tax, несколько месяцев и отдельные outflows. Обязательны exact identity union, полный зависимый горизонт и tax binding. При неполноте — candidate-only. Формулы TaxService/Period Profit ради нового пути не менять.

**FR22 — prepare и READY seal.** Зависимости: FR18, FR19, FR21.

ApplyService.prepare по разделу 5.6 получает repository READY N+1 с bridge N. Повтор того же ключа/входа не создаёт новые revisions. Readiness state самостоятельно не устанавливает. Проверить отсутствие FIFO writes до confirm, TTL, changed evidence/tax, initial/existing stream, candidate-only, tampered fingerprints и opening 103 без повторного добавления acceptance.

**FR23 — apply, preview read и restart.** Зависимости: FR22.

Реализовать scoped persisted preview read и ApplyService.apply. READY N+1 проверяет sealed basis N без правки case. Exact retry после APPLIED/restart возвращает тот же commit; apply latest запрещён. Проверить MR19–MR21, ошибки после write/commit/до ответа, новый ключ и конкурирующие соединения. HTTP внутри SQL transaction отсутствует.

**FR24 — общая production assembly.** Зависимости: FR23.

В telegram_assistant_factory выделить create_fifo_cost_transition_workflow с явными repository/history/source/tax/period dependencies. Сам create_telegram_assistant использует этот builder. Создаются реальные Evidence/Review/Apply/runtime с apply_service. Test seam заменяет IO; отдельная тестовая factory с дополнительными возможностями запрещена. create_fifo_cost_transition_service сохраняет совместимость.

**FR25 — UI и точное подтверждение.** Зависимости: FR24.

«Проверить готовность» выполняет read-only оценку. «Посмотреть пересчёт» явно готовит/показывает seal либо candidate/missing result. Финальная кнопка доступна только для READY. Server ticket содержит exact preview ID/fingerprint, case revision и stable idempotency binding; callback opaque. READY после restart показывает тот же persisted preview; APPLIED — commit и complete-through. Использовать existing sender, confirmation keyboard только в последней части.

**FR26 — downstream consumers.** Зависимости: FR25.

Current cache/history/export/Period Profit используют точные stream/allocation/mapping revisions. До apply текущая стоимость берётся прежним разрешённым путём; после — FIFO next-unit. Saved plans immutable. MR18 не расходует opening второй раз. Screen/export/explanation совпадают и показывают complete-through.

### Модуль E. Сквозная приёмка и передача

**FR27 — положительный E2E через production wiring.** Зависимости: FR26.

Добавить test_fifo_cost_transition_production_workflow.py. Последовательность: real builder → public owner inputs → synthetic supply raw responses и настоящий normalizer → import/confirm stock, turnover и physical documents → cutoff/opening confirmation → readiness → actual impact → prepare → owner confirm → atomic APPLIED → свежие factory/repository → current/Period Profit/history/export. Затем MR02–MR05 через публичные rate methods.

В этом acceptance запрещены SQL INSERT READY, ready=True mocks и готовые fake bridge/impact. Low-level fault tests могут отдельно использовать fixtures. Вторая E2E ветка MR22 остаётся source blocked и сохраняет ввод. Третья меняет store/preview перед старой кнопкой. Реальные отчёты владельца для synthetic E2E не требуются.

**FR28 — migration, backup, fault и concurrency.** Зависимости: FR27.

Normal backup round-trip для DRAFT/AWAITING/READY/APPLIED, evidence/cipher, v15 period confirmations и multi-rate balances. Restore не дублирует receipt/sale/rate. Wrong key не означает отсутствие поставки. Два независимых repository одновременно подтверждают: один commit, остальные CAS conflict или точный idempotent result. Fault на каждом write откатывает ledger/projection. Другой tenant не читает запись даже по известному ID.

**FR29 — документация и function-by-function audit.** Зависимости: FR28.

Обновить CHANGELOG, CURRENT_STATE, TEST_MAP, addendum Decision 066, owner guide, FL-progress и review packet. Пересмотреть FL18/20/23/26/35 по фактическим доказательствам, сохранив историю прежних незавершённых состояний. Добавить MR01–MR22 → test → result SHA и R-A/R-B → changed function → check. Удалить ложные claims полной готовности. OWNER_CASE_VERIFIED=false.

**FR30 — isolated full suite и CI текущих голов.** Зависимости: FR29.

Выполнить targeted FIFO/Telegram/Period Profit/Tax/Return COGS/backup/navigation profile, compileall и diff-check. Затем полный pytest в disposable copy/worktree и Verify Windows/Linux + Docker на текущих SHA сдаваемых PR.

Перед pytest проверить resolved cwd и import paths: процесс работает в disposable root, services импортируются из disposable app, worker dependencies доступны там. PYTHONPATH не меняет cwd. Owner data/DB/credentials не копировать; fixtures создаются во временном storage. Снять original data manifests before/after. При несовпадении остановить harness, сохранить точный backup и восстановить побайтно из backup. Не выполнять автоматический restore из Git для неизвестных пользовательских изменений.

Не использовать skip/deselect ради зелёного результата; не менять business code из-за ошибки harness. Новый commit требует нового CI. Если CI получить не удалось, записать конкретный external blocker; PR не объявлять ready.

**FR31 — независимый review package.** Зависимости: FR30.

Сдать PR/base/head/run URLs, changed-files map, исправления R-A/R-B, контракты, migration/rollback, MR01–MR22, production E2E trace без owner IDs, data integrity и owner limitations. IMPLEMENTATION_VERIFIED=true допустим только после всех implementation gates и current CI; OWNER_CASE_VERIFIED=false. Слияние, развёртывание и запуск бота не выполнять.

## 8. Git и упаковка

1. FR00–FR01 выполнять в текущем worktree, сохраняя dirty corrections. Не начинать от main без них.
2. После checkpoint и документации создать codex/fifo-review-rate-replay-20261108. PR A: base — актуальная ветка #730; scope FR02–FR11.
3. Создать codex/fifo-review-production-apply-20261108 от точной головы A. PR B: base — ветка A; scope FR12–FR31. Не дублировать весь стек как diff к main.
4. Порядок #728 → #729 → #730 → A → B сохраняется, пока предыдущие PR открыты. Если другая модель успела слить base, обновить связи обычным безопасным workflow и записать фактическую topology. Не force-push чужую историю.
5. Дополнительный зависимый PR для bounded import/schema допустим при слишком большом diff; dependencies указать явно.
6. Stage только явный список файлов, исключая data/, .fl12-deps/, временные логи, owner files и credentials.
7. При публикации checkpoint исправить описание #730: R-A/R-B пока открыты, существуют зависимые follow-ups, старый CI не покрывает новую голову. Сам checkpoint не делает PR готовым к слиянию.
8. Commit/push разрешены в рамках сдачи PR. Merge/deploy/live API/bot run запрещены.

## 9. Definition of Done

- [ ] Существующие исправления сохранены checkpoint; original data и чужая работа сохранены.
- [ ] MR01–MR05 проходят через реальный kernel/repository/application с тремя ставками.
- [ ] Residual не перенесён в opening; boundaries доказаны; уменьшение stock не blanket blocker.
- [ ] Returns/non-sale сохраняют exact basis и финансовые ограничения.
- [ ] Documents, owner confirmations, cutoff и opening сохраняются и восстанавливаются в точном scope.
- [ ] Рабочая production factory создаёт реальные Evidence/Review/Apply services.
- [ ] UI получает READY через parser → normalizer → bridge → replay → impact → prepare, APPLIED — отдельным exact confirm.
- [ ] Missing before даёт candidate-only без ложной delta/READY.
- [ ] Stale/tax/evidence/expiry/tenant/concurrency защиты работают.
- [ ] Rate/layers/balances/allocation/mapping/audit/case фиксируются атомарно.
- [ ] Current/Period Profit/history/export согласованы; saved plans immutable.
- [ ] Migration/backup/cipher/FK/rollback/concurrency проверены.
- [ ] MR01–MR22 и N01–N40 сопоставлены проходящим тестам.
- [ ] Полный isolated pytest, Verify Windows/Linux и Docker зелёные на current SHA.
- [ ] Реальный owner case не применён; OWNER_CASE_VERIFIED=false; source limitations перечислены.
- [ ] PR и review package готовы; merge/deploy/live API/bot run не выполнялись.

## 10. Автономность и Resume

Работать по зависимостям без промежуточных остановок. После каждого этапа обновлять FR-progress: branch/HEAD, baseline/correction SHA, статус, изменённые функции, команды и результаты проверок, PR/CI, data manifest, remaining requirements, следующий этап. После сокращения контекста перечитать Resume, ТЗ и diff; не начинать выполненную работу заново.

Останавливаться только при необходимом бизнес-решении, невозможности сохранить чужую работу/данные, объективной несовместимости утверждённого контракта или неустранимом внешнем блокере. Реальные owner reports не блокируют synthetic implementation. Отсутствующий код production-пути не называть ограничением данных.

## 11. Команда для Luna

Выполняй project_brain/LUNA_FIFO_REVIEW_BLOCKERS_COMPLETION_TASK_2026-11-08.md. Начни с FR00 и двигайся по зависимостям до FR31. Сохрани и отдельно закрепи существующие локальные исправления. Следуй заданным контрактам rate boundaries, evidence, revision N/N+1, числовой матрице MR01–MR22 и плану зависимых PR. После каждого этапа обновляй журнал и фактические результаты проверок; после сокращения контекста продолжай по Resume. Работай автономно до необходимого бизнес-решения или неустранимого блокера. Не откладывай положительный synthetic E2E из-за недостающих отчётов владельца. Заверши на PR с зелёным CI текущих SHA и пакетом независимого review. Слияние, развёртывание, реальные Ozon/Telegram-запросы и запуск бота не выполняй.

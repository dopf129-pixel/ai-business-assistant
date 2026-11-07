# Luna FIFO late entry — журнал

Дата подготовки: 2026-11-07.
ТЗ: LUNA_FIFO_LATE_ENTRY_COMPLETION_TASK_2026-11-07.md.
Матрица: FIFO_LATE_ENTRY_CASE_AND_ACCEPTANCE_2026-11-07.md.
База спецификации: main d8d4ba00c85acf14ba9a960f56a755fbe30b555c.
Журнал исполнения; содержит фактические результаты ниже. Спецификация не заменяет доказательства владельца.

## Resume

Следующий этап: FL12.
Выполненных этапов:12/36 (FL00 baseline, FL01 implementation map, FL02 typed contracts, FL03 schema v13/cipher, FL04 repository commands, FL05 pre-FIFO/fault boundaries, FL06 full-cost modes, FL07 case lifecycle, FL08 supply declarations, FL09 active observations, FL10 acceptance reconciliation и FL11 bounded refresh/checkpoint resume VERIFIED; documents, runtime integration and owner case ещё не завершены).
IMPLEMENTATION_VERIFIED: нет. OWNER_CASE_VERIFIED: нет.
Рабочая ветка исполнения: codex/fifo-late-entry-foundation-20261107, создана от точной головы PR #727 aef1f1348fca4e7728215b73ddd32004a0540e20; PR #727 открыт, base main d8d4ba00c85acf14ba9a960f56a755fbe30b555c. PR foundation будет основан на main и включит переданные документы спецификации; не начинать от старой ветки реализации #726.
Реальные Ozon/Telegram запросы, запуск бота, изменение owner DB, merge/deploy не выполнялись и не разрешены этим заданием.

Перед продолжением читать git status, актуальный HEAD и последние записи ниже. Не подменять результаты тестов плановыми ожиданиями.

## Этапы

| Этап | Содержание | Статус | Commit / checks |
|---|---|---|---|
| FL00 | Baseline и безопасная ветка | VERIFIED | aef1f134; FIFO regression 307 passed (10.96s), compileall/diff-check PASS; data manifest SHA-256 e9687fed6ce42852eb4398a7425b83b1c544613bf3f4d67d58753c8533d00730 unchanged |
| FL01 | Карта интеграции | VERIFIED | FL01_IMPLEMENTATION_MAP.md; 27 code/test paths exist, static map check and diff-check PASS; no runtime changes |
| FL02 | Контракты и часы | VERIFIED | new FIFO contract profile 13 passed; combined unique FIFO profile 320 passed; compileall/diff-check PASS; data manifest matches FL00 |
| FL03 | Миграция13 и cipher | VERIFIED | 41 passed focused; 348 passed related FIFO profile; compileall/diff-check PASS; data manifest unchanged |
| FL04 | Repository cases/evidence | VERIFIED | `a9b1374eaf96b0262ee854cb68612d6d19241717`; 63 focused / 357 related passed; compileall and diff-check PASS; `data/` unchanged |
| FL05 | До-FIFO хранение и fault tests | VERIFIED | `a5e455f49fb81af7e67bbbd708edab9db8d8e642`; 69 focused / 370 related passed; compileall/diff-check PASS; `data/` unchanged |
| FL06 | Полная стоимость | VERIFIED | `08472f865dedabcda3edf2c4b2e68bfc9ab2465d`; TOTAL_LANDED/COMPONENTS amount parity 14.65; null components; focused 59 / FIFO+Telegram 348 passed; compileall/diff-check/data unchanged |
| FL07 | Lifecycle случая | VERIFIED | `5254efafe05e197564a4913c5123373ca0db13c2`; create/edit/cancel/read/list append-only & idempotent; active store/SKU CAS; focused 25 / FIFO+Telegram 352 passed; compileall/diff-check/data unchanged |
| FL08 | Конкретные поставки | VERIFIED | `363cc5e899f7d01c682e7f4dc8a62a03977b708c`; typed ORDER/SUPPLY, scoped duplicate/SKU/total guards, ciphertext redaction, unknown-key preservation, no synthetic remainder; focused 38 / FIFO+Telegram 358 passed; compileall/diff-check/data unchanged |
| FL09 | Наблюдения и missing | VERIFIED | `f2e2239a109bdc2fee45fdbe5d39bcad815c62a7`; focused 51 passed; full pytest 4907 passed; compileall/diff-check/data restore PASS |
| FL10 | Частичная приёмка | VERIFIED | `9445d8cc`; focused 46 passed; FIFO/Telegram FIFO 379 passed; compileall/diff-check/data unchanged PASS |
| FL11 | Бюджеты/checkpoints | VERIFIED | `66d05d38`; focused 40 passed; FIFO/Telegram FIFO 388 passed; compileall/diff-check/data unchanged PASS |
| FL12 | Ведомость parser | NOT_STARTED | — |
| FL13 | Остатки parser | NOT_STARTED | — |
| FL14 | Контекстный XLSX import | NOT_STARTED | — |
| FL15 | Сверка поставок | NOT_STARTED | — |
| FL16 | Proposal opening | NOT_STARTED | — |
| FL17 | Readiness и missing evidence | NOT_STARTED | — |
| FL18 | Cutoff bridge | NOT_STARTED | — |
| FL19 | Начальная активация proposal | NOT_STARTED | — |
| FL20 | Deterministic replay | NOT_STARTED | — |
| FL21 | Возвраты/выбытия | NOT_STARTED | — |
| FL22 | Period impact | NOT_STARTED | — |
| FL23 | Atomic apply | NOT_STARTED | — |
| FL24 | Меню доFIFO | NOT_STARTED | — |
| FL25 | Durable мастер | NOT_STARTED | — |
| FL26 | Разные подтверждения | NOT_STARTED | — |
| FL27 | Current/plans/cache | NOT_STARTED | — |
| FL28 | Period Profit | NOT_STARTED | — |
| FL29 | History/refresh/cancel | NOT_STARTED | — |
| FL30 | Числовая матрица | NOT_STARTED | — |
| FL31 | Security/isolation/navigation | NOT_STARTED | — |
| FL32 | Backup/migration/restart | NOT_STARTED | — |
| FL33 | Owner guide | NOT_STARTED | — |
| FL34 | Полный CI | NOT_STARTED | — |
| FL35 | Review handoff | NOT_STARTED | — |

## Незакрытые данные реального случая

- Полный per-supply список пока не передан; известна общая отправка6982 и отдельная Беларусь148.
- Ведомость доступна владельцу только до05.11. Наблюдение исчезающих148 не является официальным описанием всех API.
- reserved, cross-source cutoff и привязка физических продаж ещё требуют proof/validation.
- Новая домашняя закупка не пересчитана — допустимый UNKNOWN, не blocker создания case.

## Выполнение FL06 — 2026-11-08

- `FifoCostRateService.preview_new_cost` и repository теперь имеют единый amount contract для `COMPONENTS` и `TOTAL_LANDED`. Компонентный режим сохраняет прежнюю сумму частей; итоговый режим требует полный `unit_cost_rub` и `NULL` всех трёх частей. Смешанные/неполные поля, неверный режим и несовпадение явно переданного component total отклоняются до записи. Поздняя коррекция из существующего component-only draft с TOTAL_LANDED закрывается отдельным кодом, без ослабления старого correction path.
- Rate mutation записывает `cost_input_mode` в существующую schema v13. Чтение истории пробрасывает mode; старые rows в migration проверке остаются `COMPONENTS`. История Telegram и CSV показывают явное отсутствие разбивки; для total-only полной суммой не подменяется закупка, а компонентные CSV-ячейки пусты. Fingerprint входа включает mode; allocation-source fingerprint оставлен совместимым: канонический unit amount и FIFO math не изменились.
- Числовой контроль N02/N03: `10.00 + 3.00 + 1.65` и `TOTAL_LANDED 14.65` дают один `14.65 ₽/шт.`; persisted total row — `cost_input_mode=TOTAL_LANDED`, purchase/delivery/packaging `NULL`. Старый компонентный путь и CSV остаются покрытыми тестами.
- Изменены `app/services/fifo_cost_repository.py`, `fifo_cost_rate_service.py`, `telegram_fifo_cost_history_service.py` и соответствующие rate/history tests. Код commit `08472f865dedabcda3edf2c4b2e68bfc9ab2465d` (`Support total landed FIFO cost rates`).
- Проверки: targeted rate/history/schema **59 passed in 2.36s**; all `tests/test_fifo_cost_*.py` + `tests/test_telegram_fifo_cost_*.py` **348 passed in 13.65s**; `python -m compileall -q app tests`, `git diff --check`, `git diff --exit-code -- data` PASS. SQL fixtures работают в `tmp_path`; файлы владельца и реальные API не читались.
- `IMPLEMENTATION_VERIFIED`: нет (сквозной переход ещё не реализован). `OWNER_CASE_VERIFIED`: нет; список реальных поставок и доказанный cutoff не добавлены. Нет blocker для независимого FL07.
- Следующий этап: FL07 — append-only application service для lifecycle transition case.

## Выполнение FL07 — 2026-11-08

- Добавлен `app/services/fifo_cost_transition_service.py`: typed create/update/cancel/get/list orchestration над существующим `FifoCostRepository`. Create принимает только revision 1/DRAFT; update допускает только DRAFT/AWAITING_EVIDENCE и следующий revision; READY_TO_CONFIRM/APPLIED не устанавливаются владельцем. Cancel восстанавливает исходный typed case из persistent payload и создаёт новую CANCELLED revision; exact retries update/cancel возвращают repository idempotent replay.
- Добавлены `FifoCostRepository.list_transition_cases` и `cancel_transition_case`. SQL list фильтруется текущим owner/tenant/store и опционально SKU/states; лимит — 100. `FifoCostTransitionStore.save_case` атомарно отвергает конкурирующий активный DRAFT/AWAITING/READY по тому же store/SKU; тест с двумя потоками показывает ровно одного победителя. Иные SKU/store и другие owners изолированы.
- Dispatch date остаётся date-only fact в case payload. Lifecycle service не обращается к FIFO stream/projection/rates/events и не формирует cutoff, allocation или profit update. Контрольная запись21→14.65, old home/transit0, shipped6982 и new home NULL переживает restart, при этом `FIFO_HISTORY_NOT_INITIALIZED` сохраняется; cancel audit revision не стирается.
- Обновлена `FL01_IMPLEMENTATION_MAP.md` новой фактической точкой application lifecycle. Изменены `fifo_cost_repository.py`, `fifo_cost_transition_store.py`; добавлены transition service и tests.
- Код commit `5254efafe05e197564a4913c5123373ca0db13c2` (`Add FIFO transition case lifecycle service`). Проверки: focused transition service/store/schema **25 passed in 2.32s**; полный профиль `tests/test_fifo_cost_*.py` + `tests/test_telegram_fifo_cost_*.py` **352 passed in 14.01s**; `python -m compileall -q app tests`, `git diff --check`, `git diff --exit-code -- data` PASS. Тестовые БД — `tmp_path`; owner data/live API не использовались.
- `IMPLEMENTATION_VERIFIED`: нет; полный supply → document → bridge → impact → atomic apply путь впереди. `OWNER_CASE_VERIFIED`: нет; реальные связи supply IDs и cutoff не подтверждены. Нет blocker для FL08.
- Следующий этап: FL08 — typed declarations конкретных поставок, защищённое сохранение lookup reference и честный нераспределённый shipped total.

## Выполнение FL08 — 2026-11-08

- `FifoCostTransitionService.declare_supply` принимает только typed `ORDER`/`SUPPLY` reference для точного owner/store/SKU case. Lookup ID нормализуется, превращается в domain-separated digest (owner/store/reference type) и шифруется существующим `tenant_cipher_provider`; raw ID не попадает в persistent payload или manifest. Тип `ACT` не является ORDER/SUPPLY reference.
- `FifoCostTransitionStore.append_declaration` в существующей `BEGIN IMMEDIATE` транзакции отклоняет duplicate reference в owner/store, привязку к другому SKU и сумму известных деклараций сверх owner-declared total. Количество перепроверяется из актуальных declaration revisions в write transaction. Отменённый case освобождает reference; активные и APPLIED cases не позволяют повторный учёт.
- Если master key отсутствует/невалиден, declaration и количество сохраняются с `LOOKUP_REFERENCE_UNAVAILABLE`; ID нельзя обновить по сохранённому lookup. `get_supply_manifest` исключает digest/ciphertext/внешний ID и показывает owner total, known assigned units, полноту назначения и numeric `undistributed_units`. Виртуальная declaration не создаётся.
- Synthetic matrix: `6234 + 600 + 148 = 6982`; остаток при одном известном declaration `6982 - 6234 = 748`; duplicate и mixed SKU отвергаются; тот же numeric ID в другом store допускается; ORDER/SUPPLY различаются, ACT отвергается. Missing cipher сохраняет 148 и помечает refresh недоступным.
- Добавлен `tests/test_fifo_cost_transition_supply_declarations.py`, обновлены DTO/store tests. Изменения остаются в существующих `FifoCostTransitionService`, `FifoCostRepository`, `FifoCostTransitionStore` и cipher provider; новая persistence authority/schema не добавлялась.
- Код commit: `363cc5e899f7d01c682e7f4dc8a62a03977b708c` (`Add scoped FIFO supply declarations`). Проверки: focused contracts/store/service/declaration profile **38 passed in 2.67s**; full FIFO + Telegram FIFO profile **358 passed in 14.52s**; `python -m compileall -q app tests`, `git diff --check`, `git diff --exit-code -- data` PASS. SQLite fixtures — `tmp_path`; `data/` не менялась.
- Реальные Ozon/Telegram запросы и owner data не использовались. Числа 6234/600/148 остаются synthetic и не подтверждают IDs или источник каждой реальной поставки. `IMPLEMENTATION_VERIFIED: нет`, `OWNER_CASE_VERIFIED: нет`; blocker для FL09 отсутствует.
- Следующий этап: FL09 — active-supply observations, PARTIAL/MISSING semantics и сохранение последнего известного количества при исчезновении агрегированной строки.

## Формат записи после этапа

~~~text
Этап:
Статус: IMPLEMENTED / VERIFIED / DATA_PENDING / BLOCKED
Изменённые файлы:
Commit:
Команды и фактические результаты:
Сохранность данных (manifest/путь изолированных fixtures):
Source readiness:
Что не доказано:
Следующий этап:
~~~

## Результаты подготовки

- Зафиксированы архитектура, scope, DTO, schema13, state machine, транзакционная граница, UX и36 этапов.
- Составлена независимая матрицаN01–N40.
- Runtime код и реальные записи не изменялись.
- Статическая проверка подготовки:36 уникальных этаповFL00–FL35,36 строк журнала,40 уникальных сценариевN01–N40 и7 независимых числовых контролей — PASS. git diff --check — PASS. Runtime tests локально не повторялись: изменения только Markdown; полный Verify документационного PR фиксируется на точном SHA в описании PR.
- Проверка документационного PR не считается реализациейFL00–FL35 или проверкой источников реального магазина.

## Выполнение FL00 — 2026-11-07

- Исходная точка чистая: checkout `codex/fifo-late-entry-completion-spec-20261107`, HEAD `aef1f1348fca4e7728215b73ddd32004a0540e20`, спецификация PR #727 открыта/mergeable на base `d8d4ba00c85acf14ba9a960f56a755fbe30b555c`; существующих изменений в рабочем дереве не было.
- Создана `codex/fifo-late-entry-foundation-20261107` от точного HEAD PR #727. Основание будущего PR — `main`; branch содержит документы #727 согласно плану исполнения.
- Baseline: существующие FIFO repository/allocation/anchor/rate/replay/sources/late-entry/supply/returns/Period Profit/Telegram tests — **307 passed in 10.96s**; `python -m compileall -q app tests` PASS; `git diff --check` PASS. Полный suite до реализации не запускался; exact-head CI документационного PR уже был зелёным, но не подменяет implementation CI.
- Файлы `data/`: **5 файлов**, 3,168 байт; aggregate manifest SHA-256 `e9687fed6ce42852eb4398a7425b83b1c544613bf3f4d67d58753c8533d00730` до и после тестов совпал. Ни тесты, ни FL00 не изменили данные.
- Source readiness: факты владельца остаются на уровне подготовки; supply IDs и доказанный cutoff не добавлены. Это не блокирует FL01.
- Следующий этап: FL01 — карта интеграции и явное сопоставление контракта с существующими швами.

## Выполнение FL01 — 2026-11-07

- Создан `project_brain/FL01_IMPLEMENTATION_MAP.md`: существующие FIFO repository/authority, v12 migration seam, supply source limits, поздний мастер, Period Profit/TaxService, planning readers, returns/outflows, cipher, backup и Telegram factory сопоставлены с точными FL-этапами и regression tests.
- Подтверждены ожидаемые ограничения текущей реализации: late UI требует initialized queue; pending текст in-memory; supply lookup ограничен COMPLETED/accepted актом; rate components имеют NOT NULL; cutoff gate ADR066 остаётся обязательным. Это адаптация имён к фактическому коду, не изменение контракта/ADR.
- Static map check: **27** перечисленных Python code/test paths существуют, missing=0; `git diff --check` PASS. Runtime не менялся; baseline 307 тестов и data manifest из FL00 без изменений.
- Решение DECISIONS/066 не изменялось: новые responsibilities остаются в том же tenant FIFO repository и canonical finance/TaxService pipeline.
- Следующий этап: FL02 — DTO, typed reason codes, clock providers и unit tests для null/zero/bool/Decimal/time/source-proof.

## Выполнение FL02 — 2026-11-07

- Добавлен `app/services/fifo_cost_transition_contracts.py`: scoped metadata, strict enums/reason codes, TransitionCase, SupplyDeclaration/Observation, BucketSnapshot, ReportEvidence, SourceProof и FinancialPreviewBinding; `Decimal`/`ROUND_HALF_UP`, UTC-aware timestamps, date-only precision и injected clock provider.
- Null quantity/cost/date требует reason code и source provenance; явный ноль остаётся допустимым. Полная стоимость `TOTAL_LANDED` не имеет компонентной разбивки; `COMPONENTS` требует явно введённые суммы с точным итогом. Доступность/полнота API чтения нельзя получить из owner-input DTO. Lookup reference contract требует Fernet-token shape либо `None`; криптографическое открытие токена относится к FL03. Секрет или обычный номер поставки не записывается в поле ciphertext.
- Добавлен `tests/test_fifo_cost_transition_contracts.py`: **13 passed**; объединённый профиль всех 320 уникальных FIFO/Telegram FIFO tests: **320 passed in 10.87s**. `python -m compileall -q app tests` и `git diff --check` PASS.
- Состояние `data/`: 5 файлов, 3,168 bytes; manifest SHA-256 `e9687fed6ce42852eb4398a7425b83b1c544613bf3f4d67d58753c8533d00730`, совпадает с FL00. Тесты запускаются в локальной venv проекта; файлы данных не изменились.
- Источники реального магазина не запрашивались. `SourceProof` подтверждает полноту чтения только по API-kind и complete scope/pagination, но не физическую семантику; cutoff gate ADR066 остаётся открытым.
- Следующий этап: FL03 — schema v13, миграция 12→13 и общий cipher provider без изменения credentials.

## Выполнение FL03 — 2026-11-07

- `FifoCostRepository.SCHEMA_VERSION` повышен до 13; добавлены seven scoped tables: transition cases/revisions, supply declarations/observations, report evidence, previews и commits. Append-only guards и indexes встроены в FIFO schema; Planning `user_version` не используется.
- Таблица `fifo_cost_rate_changes` переводится 12→13 контролируемым rebuild внутри текущей immediate transaction. Старые component amounts, IDs и row digest сохраняются; старые записи становятся `COMPONENTS`. Новый `TOTAL_LANDED` допускает только `NULL` для трёх не сообщённых владельцем компонентов. Индексы, triggers и существующие child FK схемы восстановлены; `PRAGMA foreign_key_check` проходит до commit.
- `app/services/tenant_cipher_provider.py` делегирует существующему `OZON_CREDENTIAL_MASTER_KEY`; `OzonAccountRepository._fernet()` использует тот же provider. Не добавлены новый ключ или ciphertext для credentials; invalid/missing key и invalid token fail closed.
- Добавлен `tests/test_fifo_cost_transition_schema_v13.py`. Проверены fresh schema/cost mode constraints, v12→v13 exact row digest/objects/FKs, injected partial-DDL rollback (schema остаётся 12, FK enforcement восстановлен), future schema refusal без mutation, разделение двух tenant scope для одинаковых store/SKU и шифрование с отсутствующим/неверным ключом. Обновлён v11 test для текущей schema version.
- Фактические проверки: focused schema/repository/backup/credential suite **41 passed in 2.30s**; окончательный related FIFO/profile suite **348 passed in 12.78s**; `compileall -q app tests` PASS; `git diff --check` PASS. Профиль использовал изолированные `tmp_path` БД; production/live DB и данные владельца не открывались. `git status --short -- data` пуст, `data/` manifest остаётся ожидаемым FL00 SHA-256 `e9687fed6ce42852eb4398a7425b83b1c544613bf3f4d67d58753c8533d00730`.
- Источник реального магазина не запрашивался. Новый кейс не записывался; `IMPLEMENTATION_VERIFIED: нет`, `OWNER_CASE_VERIFIED: нет`; cutoff и все owner case evidence gates остаются открытыми.
- Следующий этап: FL04 — repository commands с CAS/idempotency и квотами.

## Выполнение FL04 — 2026-11-07

- В `FifoCostRepository` добавлены `save_transition_case`, `read_transition_case`, `append_supply_declaration`, `append_supply_observation`, `append_report_evidence`, `read_transition_evidence`. Имена публичных команд приведены к зафиксированному контракту ТЗ. SQL helpers в `fifo_cost_transition_store.py` используют только переданный repository connection и не открывают/не завершают транзакцию.
- Запись case/evidence, revision snapshot, idempotency audit и CAS выполняются в `BEGIN IMMEDIATE`; на ошибке вызывающий repository откатывает всю команду. Case revision независима от FIFO stream, поэтому pending case сохраняется и читается после нового экземпляра repository, не создавая FIFO queue.
- Scope включает owner/store/product/offer/SKU. Owner id не помещается в case payload; encrypted supply lookup-reference отделён от payload и исключён из обычного read. Внешние номера поставок хранятся только в Fernet ciphertext, а payload содержит digest.
- Применены квоты: максимум20 активных cases на tenant/store,100 разных declarations на case,2000 observations на case. При превышении команда возвращает typed error и не продвигает case revision; предыдущие записи читаются полностью.
- `tests/test_fifo_cost_transition_store.py`: keyword-only public API, restart/no-queue, CAS/idempotency, concurrent CAS, declaration/observation/report persistence, replay с разным payload, stale revision, чужой tenant, ciphertext redaction, append-only и quotas. Focused профиль: **63 passed in 3.80s**. Related profile (31 modules): **357 passed in 13.95s**. `compileall -q app tests` и `git diff --check` PASS.
- Тесты использовали временные SQLite БД. `git status --short -- data` пусто; реальные data files, production DB, отчёты владельца и Ozon/Telegram API не использовались. `IMPLEMENTATION_VERIFIED: нет`, `OWNER_CASE_VERIFIED: нет`; это repository foundation, а не готовый flow применения.
- Commit FL04: `a9b1374eaf96b0262ee854cb68612d6d19241717` (`Add durable FIFO transition repository commands`).
- Следующий этап: FL05 — fault injection в каждой записи, restart/baseline proof и подтверждение неизменности legacy/history/фактической прибыли до создания FIFO.

## Выполнение FL05 — 2026-11-07

- Добавлена параметризованная fault-injection регрессия для case create, case update, append declaration, observation и report. SQLite ошибка внедряется после промежуточных изменений; repository возвращает storage-unavailable, а transaction rollback сохраняет количество evidence и прежнюю case revision. Конкурентный CAS и idempotency с конфликтующим payload дополнительно покрыты FL04 тестами.
- Новый synthetic integration test сравнивает canonical Period Profit до/после сохранения pending transition case на той же временной базе. Настоящие `FifoCostRepository` и `FifoCostPeriodProfitSourceService` остаются на `FIFO_COST_MODE_LEGACY`, `read_cost_history_snapshot` остаётся `FIFO_HISTORY_NOT_INITIALIZED`; себестоимость **21.00 ₽** и прибыль **53.00 ₽** идентичны. В базе есть case, но нет FIFO stream.
- Focused профиль transition store/schema/contracts/repository/backup/credentials: **69 passed in 4.00s**. Широкий профиль всех FIFO repository/services, Telegram FIFO, Period Profit integration, navigation и credentials (32 модуля): **370 passed in 14.40s**. `compileall -q app tests` и `git diff --check` PASS.
- Тесты используют `tmp_path`. `git diff --exit-code -- data` чистый; 5 файлов / 3,168 bytes совпадают с веткой. Владелец, production DB, реальные API и бот не использовались.
- FL05 подтверждает только безопасное сохранение незавершённого случая. Положительное доказательство принятия, cutoff, bridge и применение ещё не реализованы; `IMPLEMENTATION_VERIFIED: нет`, `OWNER_CASE_VERIFIED: нет`.
- Commit FL05: `a5e455f49fb81af7e67bbbd708edab9db8d8e642` (`Prove FIFO pending case isolation and rollback`). Следующий этап: FL06 — единая семантика полной landed cost без фиктивных компонент.

## Выполнение FL10 — 2026-11-08

- Добавлен pure `FifoCostSupplyAcceptanceReconciliationService`, который принимает только уже нормализованные и обезличенные `FifoSupplyActSnapshot` для одной поставки/магазина. Он не выполняет API-запросы, persistence, inventory movement, FIFO allocation или изменение режима прибыли.
- Кумулятивные снимки 40→70→100 выбирают последний подтверждённый total. Повтор evidence fingerprint не прибавляет количество; повтор одного act/page нормализатором дедуплицируется, а разные act refs остаются раздельными и суммируются один раз. Снимки разных stores/supplies, другой SKU, неоднозначные same-time versions и принятые единицы сверх декларации дают CONFLICT.
- Более поздний PARTIAL/UNAVAILABLE/EMPTY сохраняет последнее complete accepted quantity, но выставляет PARTIAL и не подтверждает финальную недостачу. Complete non-final 98/100 остаётся ожиданием (2 не приняты), а complete final 98/100 возвращает DISCREPANCY=2 и `CONFIRM_SHORTAGE_MOVEMENT`. Снижение 100→90 возвращает `CORRECTION_REVIEW_REQUIRED`, сохраняет 100 как прежний confirmed total, 90 — как candidate и требует документально подтверждённой коррекции.
- Отдельная repository regression подтверждает, что CANCELLED observation не удаляет declaration/cost link и не активирует FIFO. Механизма удаления/перепривязки supply cost links не добавлено.
- Изменены: новый `app/services/fifo_cost_supply_acceptance_reconciliation_service.py`, новый `tests/test_fifo_cost_supply_acceptance_reconciliation_service.py`, расширен `tests/test_fifo_cost_transition_observations.py`. Документация обновлена в CHANGELOG, CURRENT_STATE, ROADMAP, TEST_MAP и FL01_IMPLEMENTATION_MAP. Архитектура — minor extension: pure service поверх существующего нормализатора; storage schema, tax, Period Profit и production bot wiring не менялись.
- Код commit `9445d8cc` (`Reconcile FIFO supply acceptance snapshots`). Проверки на финальном коде: focused FL10 + normalizer/observation **46 passed in 1.01s**; полный FIFO/Telegram FIFO профиль **379 passed in 15.04s**; compileall, `git diff --check`, `git diff --exit-code -- data` PASS. Database fixtures используют `tmp_path`; owner database и live API не использовались.
- `IMPLEMENTATION_VERIFIED`: нет; source collection budget, persistent document versions, stock/cutoff bridge и production UI остаются впереди. `OWNER_CASE_VERIFIED`: нет; документы и факт по каждой реальной поставке ещё не представлены. Нет блокера для FL11.
- Следующий этап: FL11 — один общий budget, source checkpoints и проверяемый resume.

## Выполнение FL11 — 2026-11-08

- Добавлен `FifoCostTransitionSupplyRefreshService`: он связывает точный active status read и accepted act lookup для одного owner/store/SKU/case/declaration/revision. Финальная owner/reference проверка делает сравнение scoped digest внутри transition service; digest и ID не выводятся в safe manifest/result.
- На весь вызов наследуется единый parent budget не больше 20 секунд и 10 реальных HTTP-попыток, включая list/details, act summary/products и retry-capable client boundary. Для внешнего parent trace применяется более строгий из двух лимитов. `actual_http_attempts` показывает фактически зарезервированные вызовы без маскирующего clamp.
- Active supply, найденная до конца пагинации, теперь сохраняется внутри ограниченного process-local checkpoint и не становится complete observation. Resume продолжает scan, выявляет дубли ID на последующих страницах и записывает observation только после полного source scope. Неверная область не потребляет валидный checkpoint. Continuation привязан к владельцу, магазину, точному SKU/identity, делу, декларации, reference digest и revision; после рестарта старый токен fail closed, владелец может начать новый bounded read с сохранённого кейса/evidence.
- Добавлены `app/services/fifo_cost_transition_supply_refresh_service.py` и `tests/test_fifo_cost_transition_supply_refresh_service.py`; расширены `fifo_cost_source_collection_service.py`, `fifo_cost_transition_service.py` и source-collection tests. Покрыты 429, deadline timeout, malformed page, repeated cursor, duplicate ID across pages, process restart, store switch, case revision change, partial budget checkpoint/resume, полный shared budget по status+acts и invariant «нет FIFO mutation».
- Ошибка проверки показала, что публичный manifest должен продолжать скрывать scoped reference digest. Digest остался только внутренним; existing privacy contract regression проходит.
- Focused wrapper/source/declaration profile: **40 passed in 1.77s**. На кодовом SHA `66d05d381b3981c767fcd2fd4c4d057c7b1bd50a` полный FIFO+Telegram FIFO профиль: **388 passed in 16.26s**. `compileall -q app tests`, `git diff --check`, `git diff --exit-code -- data` PASS; все fixtures используют tmp_path и synthetic API, owner DB/данные/live API не тронуты.
- Commit FL11: `66d05d38` (`Bound FIFO supply refresh and resume`). Никакие source facts этого теста не трактуются как owner-case validation: `IMPLEMENTATION_VERIFIED: нет`, `OWNER_CASE_VERIFIED: нет`.
- Следующий этап: FL12 — read-only parser оборотной ведомости с cell provenance и точными control totals.

## PR delivery

| PR | Этапы | Ветка | Base | HEAD | CI |
|---|---|---|---|---|---|
| 1 | FL00–FL11 | codex/fifo-late-entry-foundation-20261107 | main | `66d05d381b3981c767fcd2fd4c4d057c7b1bd50a` + FL11 docs pending | NOT_RUN |
| 2 | FL12–FL23 | codex/fifo-late-entry-reconciliation-20261107 | branchPR1 | — | NOT_RUN |
| 3 | FL24–FL35 | codex/fifo-late-entry-integration-20261107 | branchPR2 | — | NOT_RUN |

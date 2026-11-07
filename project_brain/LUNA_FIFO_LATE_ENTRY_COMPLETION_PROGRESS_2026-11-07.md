# Luna FIFO late entry — журнал

Дата подготовки: 2026-11-07.
ТЗ: LUNA_FIFO_LATE_ENTRY_COMPLETION_TASK_2026-11-07.md.
Матрица: FIFO_LATE_ENTRY_CASE_AND_ACCEPTANCE_2026-11-07.md.
База спецификации: main d8d4ba00c85acf14ba9a960f56a755fbe30b555c.
Журнал исполнения; содержит фактические результаты ниже. Спецификация не заменяет доказательства владельца.

## Resume

Следующий этап: FL06.
Выполненных этапов:6/36 (FL00 baseline, FL01 implementation map, FL02 typed contracts, FL03 schema v13/cipher, FL04 repository commands и FL05 pre-FIFO/fault boundaries VERIFIED; runtime integration и owner case ещё не завершены).
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
| FL06 | Полная стоимость | NOT_STARTED | — |
| FL07 | Lifecycle случая | NOT_STARTED | — |
| FL08 | Конкретные поставки | NOT_STARTED | — |
| FL09 | Наблюдения и missing | NOT_STARTED | — |
| FL10 | Частичная приёмка | NOT_STARTED | — |
| FL11 | Бюджеты/checkpoints | NOT_STARTED | — |
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

## PR delivery

| PR | Этапы | Ветка | Base | HEAD | CI |
|---|---|---|---|---|---|
| 1 | FL00–FL11 | codex/fifo-late-entry-foundation-20261107 | main | — | NOT_RUN |
| 2 | FL12–FL23 | codex/fifo-late-entry-reconciliation-20261107 | branchPR1 | — | NOT_RUN |
| 3 | FL24–FL35 | codex/fifo-late-entry-integration-20261107 | branchPR2 | — | NOT_RUN |

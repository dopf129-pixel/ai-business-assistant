# Журнал Luna: ежедневная эксплуатация — 25.10.2026

Статус: **READY_FOR_INDEPENDENT_REVIEW; USER_VALIDATION_PENDING**. S00, A00–A05, B00–B05, C00–C05, D00–D06 и E00 закрыты в указанном offline/synthetic scope. E01 завершён на зелёных exact-head CI; owner evidence E03 остаётся открытым.
ТЗ: `LUNA_DAILY_USE_READINESS_TASK_2026-10-25.md`.
Основание: `DAILY_USE_READINESS_AUDIT_2026-10-25.md`.

## Точка продолжения

- Следующий шаг: независимый review текущей PR stack #713–#717, затем owner evidence E03 и эксплуатационное наблюдение. Не считать зелёный synthetic CI заменой реальным данным. E00 acceptance: `DAILY_USE_END_TO_END_LINKED_ACCEPTANCE_E00_2026-10-25.md`. D01–D06 acceptance: `DAILY_USE_BACKUP_ACCEPTANCE_D01_2026-10-25.md`, `DAILY_USE_RESTORE_ACCEPTANCE_D02_2026-10-25.md`, `DAILY_USE_UPDATE_PREFLIGHT_ACCEPTANCE_D03_2026-10-25.md`, `DAILY_USE_UPDATE_ACCEPTANCE_D04_2026-10-25.md`, `DAILY_USE_STATUS_DIAGNOSTICS_ACCEPTANCE_D05_2026-10-25.md`, `DAILY_USE_RESILIENCE_ACCEPTANCE_D06_2026-10-25.md`. A04 завершён только в доступном документальном scope; owner evidence pending в `DAILY_USE_A05_OWNER_EVIDENCE_REQUEST_2026-10-25.md`.
### E01 — исправления независимого review backup (R1–R3)

- R1: добавлены реальные list-based `actions.json`, `conversation_history.json`, `store_reports.json` в единый JSON root-type контракт creation/verify.
- R2: `BotStartupMaintenanceGuard` сериализует canonical `BotInstanceLease` startup и полный backup snapshot. Запуск во время snapshot и backup во время startup завершаются fail-closed без публикации смешанного архива.
- R3: mapping registry override внутри approved project/storage root записывается в manifest как `(root, relative path)`; выбор nested storage использует самый специфичный root, verify/dry-run/restore согласованы; внешний путь остаётся запрещённым.
- Адресный Windows профиль: **32 passed in 1.93s**; `compileall -q app tests` и `git diff --check` прошли. Один существующий `SyntaxWarning` остаётся в неизменённом test module.
- Commit #715 `509fedba`; forward merge #716 `5bd3699c`; forward merge #717 includes `8559832f`; soak assertion correction `37d6bb43`. Исходные ветки не переписывались, main не менялся. Exact-head Verify: #715 `40185833721` success; #716 `40185869091` success; #717 `40186507007` success on Windows/Linux, 3,728 tests per platform plus Linux Docker build/smoke.
- Verify #717 `40186094904` обнаружил на Windows и Linux одну одинаковую регрессию в bounded lifecycle soak: после восьми циклов остаётся ровно три ограниченных файла, поскольку startup/snapshot lock безопасно сохраняется вместе с instance metadata и instance lock. Проверка обновлена с подсчёта «2 файла» на точные префиксы `instance-*` (2) и `startup-*` (1); повторная проверка вынесена в новый exact-head CI.
- Локальный повтор именно subprocess soak пометил тест как ошибку и завис при очистке на Windows ACL; запуск остановлен и не учитывается как успешная проверка. Исправленный test прошёл как часть полного Windows/Linux CI (`3728 passed` на каждой платформе).

- Снимок подготовки: локальный main `7e6eabdeba34a822434e5ef417a135995628cc41`; PR #712 открыт, проверенный head `698c9f8bb9c4b8f5acc6b4fdcb475c1062e658ea`. Не считать эти refs неизменными на момент исполнения.
- Ветка реализации: `codex/daily-readiness-a-foundation`, база PR #712 head `698c9f8bb9c4b8f5acc6b4fdcb475c1062e658ea`; отдельный managed worktree.
- Создан зависимый PR stack: #713 A/foundation (`e014f278`), #714 B/C (`7ec47ef6`), #715 backup/restore (`509fedba0246b87bbc1d407fdadcf990b2daaee0`), #716 updater/status (`5bd3699cf70a3e459ca0bfd21776799a42c37da1`), #717 acceptance (`8559832f802054b564823798c05e0cbf1bccead8`). Исправления из review #715 перенесены в #716/#717 обычными merge commits; prior exact-head CI для #715–#717 superseded, свежие проверки ожидаются. #713/#714 checks остаются актуальны. Все PR остаются draft. A02 добавил локальный read-only service/CLI; production финансовые формулы не менялись.
- Содержимое отчётов частично проверено на этапе A01: только метаданные, схема, даты и агрегированные признаки; исходные строки не копируются.
- Документальные проверки подготовки: 30 уникальных stage IDs, 30 строк матрицы, 36 существующих путей, markdown/UTF-8/whitespace и diff-check успешны; это не выполнение S00.
- Исходники продавца, `.env`, SQLite/JSON данные, существующие lock/temp/review files сохранить. Документы подготовки можно выборочно перенести в новую ветку, не добавляя остальной dirty diff.

## Матрица этапов

| ID | Задача | Статус | Evidence / commit / PR |
|---|---|---|---|
| S00 | Исходная точка и безопасная среда | DONE | `698c9f8`; PR #712 открыт, exact-head CI зелёный; dirty main сохранён |
| A00 | Матрица показателей/источников | DONE | `DAILY_USE_RECONCILIATION_RESULTS_2026-10-25.md` |
| A01 | Инвентаризация отчётов и fixtures | DONE | `DAILY_USE_EVIDENCE_INVENTORY_2026-10-25.md`; A04 исправил подсчёт XLSX: 1 293 строк, 2 SKU |
| A02 | Offline comparator и canonical снимок | DONE | `daily_use_reconcile.py`; 10 targeted tests; реальный August XLSX read-only 38,864 строк |
| A03 | Известные расхождения и multi-SKU регрессии | DONE | 94 + 90 targeted tests passed; добавлен multi-SKU regression |
| A04 | Сверка текущего кода с реальными отчётами | DONE_WITH_EXTERNAL_EVIDENCE_PENDING | `DAILY_USE_A04_PRELIMINARY_SOURCE_RECHECK_2026-10-25.md`; XLSX повторно нормализован, current exact-head bot JSON отсутствует |
| A05 | Реестр приёмки и недостающего evidence | DONE_LOCAL | `DAILY_USE_A05_OWNER_EVIDENCE_REQUEST_2026-10-25.md`; один current anonymized export + optional 56-day cross-docking summary |
| B00 | Аудит существующей полноты | DONE | `DAILY_USE_COMPLETENESS_GAP_AUDIT_2026-10-25.md`; 40 targeted tests passed; подтверждённых defects нет |
| B01 | Источники/суммы/статусы подтверждения | DONE | `component_evidence` в существующей projection; 43 targeted tests passed |
| B02 | Заказы, отмены и возвраты | DONE | `DAILY_USE_EVENT_SOURCE_AUDIT_2026-10-25.md`; 73 targeted tests passed |
| B03 | Расходы и отсутствие двойного вычитания | DONE | `DAILY_USE_EXPENSE_CATEGORY_AUDIT_2026-10-25.md`; 94 core + 5 pure tests passed; storage-backed CI pending |
| B04 | Себестоимость и Return COGS | DONE | `DAILY_USE_COGS_EFFECTIVE_DATE_AUDIT_2026-10-25.md`; current-cost historical fallback removed; 154 targeted tests passed |
| B05 | Приёмка полноты и exports | DONE | `DAILY_USE_COMPLETENESS_ACCEPTANCE_B05_2026-10-25.md`; 41 passed, 1 ACL-bound test deselected |
| C00 | Инвентаризация экранов и схема | DONE | `DAILY_USE_SCREEN_INVENTORY_C00_2026-10-25.md`; formatter 470 chars / 472 UTF-16; emoji split ≤3 800 units |
| C01 | Компактный отчёт и детали | DONE_LOCAL | Acceptance C01; 74 passed, 1 deselected; exact-head CI pending |
| C02 | Следующие действия/навигация | DONE_LOCAL | Acceptance C02; 105 passed, 9 ACL-bound tests deselected |
| C03 | Ожидание, retry и отмена | DONE_LOCAL | Acceptance C03; 44 passed, 1 ACL-bound test deselected |
| C04 | Профиль запросов/производительности | DONE_LOCAL | `DAILY_USE_PERFORMANCE_ACCEPTANCE_C04_2026-10-25.md`; 44 passed, 1 ACL-deselected; exact-count batch profile |
| C05 | Сквозная пользовательская приёмка | DONE_LOCAL | `DAILY_USE_END_TO_END_ACCEPTANCE_C05_2026-10-25.md`; 81 passed, 3 ACL/temp tests deselected |
| D00 | Storage inventory и snapshot contract | DONE | `DAILY_USE_STORAGE_INVENTORY_D00_2026-10-25.md`; DECISION 056; actual DB/data untouched |
| D01 | Проверяемая резервная копия | VERIFIED_OFFLINE + REVIEW_FIXES | `DAILY_USE_BACKUP_ACCEPTANCE_D01_2026-10-25.md`; R1–R3 regressions: 32 focused tests passed |
| D02 | Восстановление в новый root | VERIFIED_OFFLINE | `DAILY_USE_RESTORE_ACCEPTANCE_D02_2026-10-25.md`; 13 focused tests passed |
| D03 | Update preflight | VERIFIED_OFFLINE | `DAILY_USE_UPDATE_PREFLIGHT_ACCEPTANCE_D03_2026-10-25.md`; 24 synthetic Git/lifecycle tests passed |
| D04 | Обновление и readiness одной командой | VERIFIED_OFFLINE | `DAILY_USE_UPDATE_ACCEPTANCE_D04_2026-10-25.md`; 54 updater/backup/lifecycle tests passed |
| D05 | Статус процесса/диагностика | VERIFIED_OFFLINE | `DAILY_USE_STATUS_DIAGNOSTICS_ACCEPTANCE_D05_2026-10-25.md`; 87 related tests passed |
| D06 | Fault/soak проверки и runbook | VERIFIED_OFFLINE | `DAILY_USE_RESILIENCE_ACCEPTANCE_D06_2026-10-25.md`; 11 passed, max lifecycle cycle 0.297 s |
| E00 | Общая регрессия | VERIFIED_LOCAL_ISOLATED | `DAILY_USE_END_TO_END_LINKED_ACCEPTANCE_E00_2026-10-25.md`; 350 passed in 22.70s |
| E01 | PR и полный актуальный CI | VERIFIED | #715 `40185833721`, #716 `40185869091`, #717 `40186507007` green on exact heads |
| E02 | Независимый review handoff | READY_FOR_INDEPENDENT_REVIEW | `DAILY_USE_READINESS_REVIEW_HANDOFF_2026-10-25.md`; exact #713–#717 heads and CI runs recorded |
| E03 | Пакет внешней приёмки владельца | PREPARED / USER_VALIDATION_PENDING | `DAILY_USE_A05_OWNER_EVIDENCE_REQUEST_2026-10-25.md`, `DAILY_USE_OWNER_OBSERVATION_LOG_2026-10-25.md` |

## Независимые состояния готовности

| Контур | Текущее состояние |
|---|---|
| Новая реализация и регрессии | A02 comparator реализован; B/C/D/E00 завершены в offline/synthetic scope; owner evidence остаётся pending в E03 |
| Новый Windows/Linux/Docker CI | VERIFIED on exact PR heads #715–#717; #717 run `40186507007`: Windows/Linux 3,728 tests each, Linux Docker build/runtime smoke |
| Сверка содержимого реальных отчётов | Предварительно: net accrual августовского XLSX `177282.17`, complete; current bot JSON export не предоставлен; финальная сверка A04 после C |
| Backup/restore drill на synthetic data | Offline verification done in D01/D02; D06 fault cases passed; no owner production restore performed |
| Текущее live-окружение и приёмка владельца | Не проверено; подготовить USER_VALIDATION_PENDING в E03 |

## Журнал исполнения (продолжение)

### D00 — карта durable storage и контракт v1 (25.10.2026)

- Только по коду/factory найдено две группы durable state: общая credential DB и tenant-scoped `data/tenants/<24hex>/` DB/JSON; дополнительно активны legacy root DB, global user/task/profile JSON, tax/mapping и app JSON. `AI_ASSISTANT_STORAGE_ROOT` не перенаправляет все legacy источники.
- Отдельно зафиксированы включаемые root-relative paths, excluded `.env`/ключи/Git/venv/cache/log/diagnostics/process state и внешний mapping override как unsupported, если он выходит за approved roots.
- Зафиксировано архитектурное решение 056: стоп-only backup boundary, manifest v1 с SHA-256/metadata, SQLite backup API + integrity, JSON parse, атомарная публикация и restore только в новую пустую папку; нет обещания cross-DB transaction consistency.
- Реальные каталоги, `.env`, SQLite/JSON и lifecycle не читались. Acceptance только на generated synthetic state; следующий D01.

### D01 — создание и проверка резервной копии (25.10.2026)

- Добавлены локальный `backup_bot.ps1`, Python CLI/helper, архив формата `ai-assistant-backup` v1, `.local-backups/` ignore rule и synthetic regressions. Backup требует токен-связанного lifecycle=`STOPPED`, ничего не останавливает и не читает реальные данные в рамках разработки.
- Первичная проверка выявила подтверждённую ошибку: валидатор source paths считал директорию tenant-хранилища файлом. Валидатор получил явный тип пути; успешный сценарий теперь включает legacy и tenant JSON/SQLite с кириллическими именами каталогов.
- Ужесточена проверка архива: отказ при лишних/дублирующих case-insensitive ZIP entries, превышении распакованного размера, небезопасных относительных путях, расхождении с manifest и неверном completion marker.
- Проверка на Python 3.12 Windows: `tests/test_bot_backup_service.py` — **7 passed in 0.46s**; `py_compile app/services/bot_backup_service.py app/bot_backup.py` прошёл. `.env`, ключи, исходные синтетические JSON/SQLite не попали в архив; источник остался неизменен. `git diff --check` очищен.
- Не проверено: disk-full физического носителя; вместо этого проверен отказ атомарной публикации и сохранение предыдущего архива. Полный exact-head CI ещё впереди.
- Acceptance: `DAILY_USE_BACKUP_ACCEPTANCE_D01_2026-10-25.md`. Следующий этап D02.

### D02 — проверка восстановления в новый root (25.10.2026)

- Добавлены `restore_bot.ps1`, `restore` CLI subcommand и `BotBackupService.restore_archive()`; `-CheckOnly` выполняет verify + destination preflight без записи. Реальное восстановление допускает только новый отсутствующий target, разворачивает `project/` и `storage/` через private staging, повторно проверяет checksums/контент, пишет `RESTORED.json` последним и публикует переименованием.
- Restore отвергает target внутри/над текущими storage roots, существующие каталоги, небезопасные/unsupported paths, archive traversal, symlink/reparse entries, case-insensitive дубли и превышение лимитов expanded size/files. Никакой `.env`/master key не восстанавливается; вывод указывает необходимость прежнего ключа только для сохранённых encrypted credentials.
- Регрессия создала два synthetic tenant ExpenseRepository с различными расходами, сделала backup/restore и повторно прочитала оба владельческих scope через существующий repository. Значения совпали с исходными; source DB и JSON остались без изменений.
- Windows Python 3.12: backup/restore профиль — **13 passed in 0.69s**; Python `py_compile`, PowerShell parser для обоих wrappers и `git diff --check` прошли. Exact-head CI предстоит; live restore/bot не запускались.
- Runbook и ограничения: `DAILY_USE_RESTORE_ACCEPTANCE_D02_2026-10-25.md`. Следующий этап D03.

### D03 — read-only update preflight (25.10.2026)

- Добавлены `update_bot.ps1 -CheckOnly`, local CLI и `BotUpdatePreflightService`. Разрешён только ожидаемый root, `main`, tracking `origin/main` и канонический remote. План фиксирует текущий/целевой SHA cached ref и предупреждает, что он может устареть; fetch не выполняется.
- Перед будущей остановкой процесса проверяются staged/unstaged/untracked changes, local ahead commits, входящие пути и target tree. Изменённые или игнорируемые `data/tasks.json`/`data/users.json` сохраняются только при отсутствии пересечения; прочие code/data dirty files и конфликтующие untracked paths блокируют план. Изменения requirements отображаются, подтверждённая lifecycle state включена в результат; `UNKNOWN` блокирует.
- Регрессия: **9 passed in 8.46s** на синтетических репозиториях. Проверено, что HEAD/status и fake running process остаются без изменений; список вызовов Git не содержит fetch/pull/reset/checkout/clean; CLI не печатает synthetic token или remote URL.
- Python `py_compile`, PowerShell parser и `git diff --check` прошли. Реальный checkout/.env/remote/бот не трогались; exact-head CI впереди.
- Acceptance: `DAILY_USE_UPDATE_PREFLIGHT_ACCEPTANCE_D03_2026-10-25.md`. Следующий этап D04.

### A04 final — августовская сверка после C05 (25.10.2026)

- Re-run `daily_use_reconcile.py reference` на фактическом августовском accrual XLSX с bundled OpenPyXL: `DAILY_USE_REFERENCE_READY`, complete, **38 864 строки**, **177 282.17 ₽ net accrual**, date basis `accrual_date`; команда и структурированный результат без SKU сохранены в A04 audit.
- Другой сопоставимый закрытый период, current exact-revision Period Profit JSON и полный cross-docking знаменатель за 56 завершённых дней отсутствуют. Ранее полученные суммы комиссии/размещения сопоставлены с историческими XLSX/API сообщениями, не с новым запуском текущего кода. Event metrics не сравниваются как одна когорта.
- Нового необъяснённого дефекта в доступном документальном scope не подтверждено. A04 закрыт с пометкой `DONE_WITH_EXTERNAL_EVIDENCE_PENDING`; дальнейшее текущегодо evidence не требуется для подготовки review-ready PR.

### A05 — пакет владельческой приёмки (25.10.2026)

- Подготовлена одна инструкция получения нового JSON export и точного revision после отдельного обновления владельцем; указаны анонимизация SKU и единственный explicit refresh перед новым снимком.
- Отдельно указан необязательный read-only cross-docking summary для полного 56-дневного знаменателя. Один acceptance act не объявляется полным окном.
- Статус внешней приёмки: `USER_VALIDATION_PENDING`; credentials/raw files не запрашиваются. Пакет: `DAILY_USE_A05_OWNER_EVIDENCE_REQUEST_2026-10-25.md`.

### C05 — сквозные пользовательские пути (25.10.2026)

- Добавлен public-handler regression: отчёт → детали → полнота → расходы того же периода → подтверждение → возврат → точный refresh → CSV; owner/store stale actions rejected. Detail/expense/return/export не добавляют запросы; исходный и явный refresh — 2 запроса.
- Исправлено принятие expired snapshot как успешного контекста для перехода к внешним расходам. Кнопка возврата показывается только для валидного callback с 12-значным report token; источник на проверке синтетический.
- Связанный C00–C05 профиль: **81 passed, 3 deselected in 3.33s**. В отдельном analytics runtime module: **10 passed, 1 deselected in 0.82s**. Temp-backed tests остаются обязательны на CI из-за локального Windows ACL, не считаются зелёными.
- Руководство обновлено: кнопка внешних расходов сохраняет период; после внесения данных требуется явное обновление; экспорт использует снимок.
- Acceptance: `DAILY_USE_END_TO_END_ACCEPTANCE_C05_2026-10-25.md`. Следующее: A04 final/A05.

## Журнал исполнения

### S00 — безопасная исходная точка (25.10.2026)

- Основной checkout: `main`, HEAD `7e6eabdeba34a822434e5ef417a135995628cc41`. В нём сохранены изменения `CHANGELOG.md`, `project_brain/CURRENT_STATE.md`, `project_brain/ROADMAP.md`, `data/tasks.json`, `data/users.json`, пользовательские lock/temp/review paths. Ни один из этих файлов не переключался и не очищался.
- PR #712 повторно проверен: открыт, base `main` на `7e6eabde...`, head `698c9f8bb9c4b8f5acc6b4fdcb475c1062e658ea`, mergeable. Exact-head CI 40168559070 и 40168556617: Linux и Windows jobs завершились `success`; полный suite по 3 647 tests на каждой ОС, compile обеих ОС, Linux Docker build/runtime smoke.
- Создан отдельный worktree и ветка `codex/daily-readiness-a-foundation` от проверенного head `698c9f8`; его исходный checkout чистый. Новый тестовый код будет использовать изолированные temporary/storage roots; production factory на пользовательской storage не запускается.
- SHA-256 `data/tasks.json` и `data/users.json` сохранены только в локальном системном `%TEMP%` (`daily-readiness-s00-protected-data-hashes.json`), не в Git/CI. `.env`, credentials, БД и содержимое этих JSON не читались.
- PR #712 не менялся/не сливался. Бот, Telegram, Ozon live API, backup/restore и deploy не запускались.
- Проверка: сравнение ветки/base/head, статус чистого worktree, фильтрованный status основного checkout, хэши защищённых JSON и API CI checks. Результат — S00 принят.

### A00 — границы сверки

- Подготовлена матрица источников, времени, зерна, периода, области и округления в `DAILY_USE_RECONCILIATION_RESULTS_2026-10-25.md`.
- В матрице различаются строка реализации, начисление, отправление и единица товара; отдельно описаны store P&L, SKU/unit economics, планы цены и Return COGS.
- Исторические цифры августа остаются ориентирами до A01/A04; тип строк не превращается в количество проданных товаров.
- Проверка: у каждого денежного и количественного показателя описаны авторитетный источник и date basis; несопоставимые источники явно отмечены.

### A01 — файлы и безопасные fixtures

- Перепроверены точные пути приложения 1. Семь файлов доступны, старый returns export 14:57 отсутствует. Размеры/хэши, sheet ranges, header aliases и date ranges записаны в локальный manifest `%TEMP%/daily-readiness-source-manifest.json`; manifest очищен от значений строк/идентификаторов.
- Две августовские выгрузки начислений содержат по 38 864 строки данных; все строки, ID-мультимножество и суммы совпали. Хэши различаются; файлы не суммируются. Период даты начисления 01–31 августа, дата услуги начинается 15 июня.
- Первичная проверка ошибочно включила строку 15 с номерами заголовков; A04 повторно проверил 01–31 августа с 16-й строки: 1 293 строки с SKU, 2 SKU, 5 356 реализованных единиц и 2 возврата. Коррекция документации записана в `DAILY_USE_A04_PRELIMINARY_SOURCE_RECHECK_2026-10-25.md`.
- Returns report имеет отдельные даты заказа, возврата, статуса, компенсации и возврата продавцу. Orders CSV содержит 6 119 строк и пересекает август–октябрь по разным датам. Оборотная ведомость относится к одному дню; акт — к одной поставке.
- Создан `tests/fixtures_daily_use_synthetic_multi_store_v1.json`: 2 тестовых магазина, 4 синтетических SKU, actual vs процентная комиссия, возврат комиссии, signed cross-dock adjustment, unknown vs zero и Return COGS gap.
- Проверка: две выгрузки начислений сравнивались по строкам/ID/суммам в памяти; исходники не менялись и не копировались. A01 принят. `.env`, ключи, идентификаторы и базы не читались. Инвентаризация реализации исправлена после прямого A04 повторного подсчёта.

### A02 — offline comparator и сохранённый snapshot (25.10.2026)

- Добавлены `DailyUseReconciliationService` и локальный `daily_use_reconcile.py`. Единственный профиль — `ozon_accruals_xlsx_v1`, с точным листом, строкой заголовков и колонками `Дата начисления` / `Сумма итого, руб.`. Читается один XLSX read-only; signed суммы считаются через `Decimal`, одинаковый ID начисления не дедуплицируется.
- Snapshot-команда проецирует только `net_accrual` из сохранённого allowlisted JSON export Period Profit и записывает период, date basis, coverage и известную ревизию. Для старого экспорта без ревизии остаётся `UNAVAILABLE`, текущий checkout не подставляется. Compare выдаёт `metric/expected/actual/difference/source_basis/coverage/status/reason`; неизвестное покрытие, период, source, dimension или значение не становится нулём/MATCH.
- Добавлены 10 регрессий: profile/schema, дубликат заголовка, signed adjustment, повторяющийся ID, пустая выборка, observed zero, corrupt amount, чужие date/store/SKU scopes, incomplete coverage, safe export projection и CLI boundary.
- Реальный августовский accrual XLSX прочитан локально через bundled OpenPyXL в read-only: **38 864 строки**, все даты валидны в периоде. Даты и полнота были подтверждены владельцем по видимому периоду отчёта; alias магазина вводится вручную. Сырые значения и итог суммы остались вне Git.
- Проверка: `tests/test_daily_use_reconciliation_service.py tests/test_daily_use_reconcile_cli.py` — **10 passed in 0.94s** на локальном Windows venv. Полный pytest не запускался из-за документированного ACL/shared-storage ограничения. Ozon API, Telegram, бот, DB и backup не запускались.
- Следующий этап: A03 — регрессии известных расхождений и multi-SKU сценариев; A02 сам не меняет production economics.

### A03 — сверка тестового покрытия известных экономических рисков (25.10.2026)

- Проведён audit существующих тестов и добавлена одна regression для трёх SKU с разными ставками комиссии, рекламы и себестоимости. Zero-sales SKU даёт observed zero; SKU с положительным количеством без COGS оставляет group profit/tax unavailable.
- Изолированный finance/store/cross-docking profile: **94 passed in 2.58s**. Изолированный product/unit-economics/sales-mix/plan-fact profile: **90 passed in 3.93s**.
- В этих профилях покрыты actual commission + refund, явное placement, signed crossdock adjustments и reverse logistics, остаток без повторного вычитания, cancellations/returns, API duplicate/pagination/unknown state, multiple SKU, tenant/store isolation и saved-plan compatibility adapters.
- Один первый запуск без `AI_ASSISTANT_STORAGE_ROOT` завершился ошибками открытия account DB; тесты повторены с отдельным Temp storage и прошли. Отдельные тесты с Python/pytest `TemporaryDirectory/tmp_path` получили Windows ACL setup/cleanup ошибки: 64 прошло, 6 failed, 3 errors в дополнительном mixed run; эти результаты не засчитываются, тестовые фикстуры не менялись. Полный local pytest не запускался.
- Не воспроизведено подтверждённого дефекта основного расчёта; production finance/COGS logic не менялась. Далее B00; temp-dependent regressions должны выполняться в CI с чистым runner.

### B00 — аудит полноты и текущих действий (25.10.2026)

- `DAILY_USE_COMPLETENESS_GAP_AUDIT_2026-10-25.md` фиксирует проверенные view/runtime/keyboard/export/resolver contracts и отделяет подтверждённый defect от source limitation и product gap.
- Повторно подтверждены exact-period gating, row/unit reconciliation, tax/cost validation, external expense coverage, отдельная сверка рекламы, Return COGS blocker chain, scoped snapshot и allowlisted support export.
- Обнаруженные направления для B01–B05: покомпонентную provenance/coverage-строку можно сделать яснее; источник отмен/возвратов остаётся ограниченным; расходная декомпозиция требует явного no-double-count; actions не должны обещать исправление недоступного источника. Новый registry не нужен.
- Targeted profile: 4 модуля полноты/диагностики/export/blocker — **40 passed in 1.64s** с отдельным storage root. Полный local pytest и temp-heavy ACL-профили не запускались.
- Production-дефект не подтверждён, code changes не потребовались. Далее B01; C00 и D00 независимы по dependency graph.

### B01 — покомпонентное evidence полноты (25.10.2026)

- В `PeriodProfitCompletenessViewService` добавлен совместимый `component_evidence` projection для выручки, скидочных баллов, налоговой базы/налога, net accrual, финансовых комиссий/логистики/эквайринга/остатка, продаж, себестоимости, внешних расходов, рекламы, возвратов и исторического Return COGS.
- Каждая строка содержит safe key/label, amount либо `None`, unit, source, date basis, exact period, normalized status/coverage и reason. Новая проекция не копирует SKU/posting/return IDs и не меняет enum публичной диагностики.
- Observed zero отделён от unknown; partial external expense показывает только наблюдаемую сумму. При неподтверждённой налоговой политике точная налоговая база и прибыль не публикуются в проекции. Рекламная сумма помечена как уже включённая в net accrual.
- Текст экрана использует компоненты; C01/C03 должны проверить длину на длинных возвратных списках и при необходимости вынести подробности в существующий details/export с транспортным разделением.
- Проверка: полнота, diagnostic view, support export и Return COGS blocker — **43 passed in 1.58s** с отдельным storage root. Полный pytest не запускался.
- Код: `app/period_profit_completeness_view.py`; regressions: `tests/test_period_profit_completeness_view.py`. Новая layer/registry и изменение центральной формулы не добавлялись.
- Далее B02; C00/D00 остаются независимыми от B02.

### B02 — заказанные, отменённые и возвращённые единицы (25.10.2026)

- Фактическая Analytics diagnostic за 01–31.08.2026: 31 дневная строка; `ordered_units` total и сумма строк **6 117**; `cancellations`/`returns` отсутствуют в totals и каждой строке. Unknown не перекодирован в zero.
- По ранее запущенному владельцем API diagnostic: FBO 272/272 уникальных строк на полной странице; 270 `Cancellation` / quantity 270 и 2 `ClientReturn` / quantity 2. FBS пустой, полный. `visual.change_moment` попадает в августовское окно. Идентификаторы/товары не сохранены.
- Прочитано официальное описание, переданное владельцем: `/v1/returns/list` допускает один date filter, max 500, пагинацию `last_id`/`has_next`. Код и timestamp tests подтверждают фильтр `visual_status_change_moment`; официальный документ указан в `DAILY_USE_EVENT_SOURCE_AUDIT_2026-10-25.md`.
- Existing fallback считает cancellation units в posting source по его фильтру и текущему status cancelled; возвраты суммируются только по `ClientReturn.product.quantity` и дате смены статуса. `Cancellation` не прибавляется к возвратам. Разные когорты не получают процент от ordered units.
- Проверка 4 модулей Analytics/returns/timestamp/evidence: **73 passed in 2.48s** с отдельным storage root. Новой production ошибки не подтверждено, код не менялся.
- Далее B03; ограничения даты cancellation и сравнения с realization зафиксированы как источник/зерно, не как ноль или искусственный defect.

### B03 — категории расходов и точное включение в прибыль (25.10.2026)

- Проверены месячный `/v2/finance/realization` commission source, provisional fallback для partial month, shared Ozon label classifier, категоризация последней мили/обратной логистики/рекламы/cross-docking/размещения и вывод баланса остатка.
- Подтверждено: monthly source суммирует actual commission sale/refund amounts, а количество строк реализации нигде не используется как количество продаж/единиц. Последняя миля имеет `included_in=logistics`, `additive=false`; Performance CPC — только сверка; alternative storage source отображается как reference без повторного сложения. Signed categories plus unallocated balance preserve net accrual; profit formula не меняется.
- Exact monthly commission regression: sale **−69 193,10 ₽** + return **+25,20 ₽** = **−69 167,90 ₽**; placement recognizer включает явный type `Размещение на складе` / `Услуги FBO → Размещение`. Owner's previously posted August report contains expected commission **−69 167,90 ₽** and remainder **−105 966,58 ₽**; direct XLSX rerun is reserved for A04.
- Проверка: 4 core modules — **94 passed in 2.54s**. Pure external expense evidence/adjustment cases — **5 passed**. Storage-backed coverage/Telegram flows encountered pytest `tmp_path` ACL setup errors; no assertion failures. Exact-head CI must run these before release. Full local pytest not executed.
- Confirmed production defect: none. Implementation/contracts: unchanged. Detailed findings and test limitations: `DAILY_USE_EXPENSE_CATEGORY_AUDIT_2026-10-25.md`.
- Далее B04; A04 остаётся зависимым от завершения соответствующих B/C сверок.

### B04 — даты действия себестоимости и Return COGS (25.10.2026)

- Найдена подтверждённая ошибка: при отсутствии date-scoped historical cost service использовал текущую строку `get_all_costs()` для прошлой даты. Два regressions показывали применение стоимости, внесённой 1 и 5 сентября, к периоду до неё. Это нарушало предыдущий выбор владельца «предлагать дату; всю историю применять только после отдельного подтверждения».
- Удалён этот fallback в `PeriodProfitFinanceSkuScopeService`. Исторический SKU теперь восстанавливается только через `get_historical_cost_evidence` на дату расчёта; без подтверждения COGS режим остаётся `PERIOD_PROFIT_FINANCE_SKU_COST_COVERAGE_INCOMPLETE`. Точные SKU каталога, pre-COGS режим, и отдельное whole-history подтверждение не менялись.
- Проверены fail-closed стадии Return COGS: inventory recovery → accounting attribution → recognition → application authorization → explicit commit → final application. Одного `SALEABLE_RESTORED` недостаточно, учётный write consumer не добавлялся.
- 18-модульный B04 profile — **154 passed in 5.28s**. Полный pytest не запускался; часть SQLite/commit файловых tests остаётся exact-head CI из-за Windows ACL на pytest `tmp_path`.
- Изменены service и две регрессии; audit: `DAILY_USE_COGS_EFFECTIVE_DATE_AUDIT_2026-10-25.md`. DECISIONS.md не менялся: выполнено ранее принятое решение, новый architectural contract не вводился.
- B04 закрыт; следующий этап B05.

### B05 — приёмка полноты и экспортов (25.10.2026)

- Подтверждённый дефект: основной CSV/JSON analytics export терял полноту компонентов и canonical причины, доступные в report completeness/diagnostics.
- Existing report view теперь сохраняет allowlisted completeness status/reason projection в analytics snapshot. Короткий ответ, полнота и диагностика используют одинаковые человекочитаемые причины; JSON metadata и CSV `metadata_json` содержат те же status/reason codes. Support JSON остаётся safe, no-money allowlist.
- Интеграционная regression сравнивает причины в коротком ответе, полноте, диагностике, support JSON, CSV и JSON; проверяет один query service call при открытии деталей/export. Матрица confirmed/partial/unavailable остаётся fail-closed.
- Пять связанных модулей: **41 passed, 1 deselected in 2.39s**. Исключён только production-factory тест с `tmp_path`, заблокированным ACL локальной Windows среды; exact-head CI должен выполнить его. Полный локальный pytest не запускался.
- Отчёт: `DAILY_USE_COMPLETENESS_ACCEPTANCE_B05_2026-10-25.md`. Далее C00; согласно ТЗ окончательную A04 сверку выполнить после C05.

### C00 — инвентаризация экранов ежедневной работы (25.10.2026)

- Пройдены контракты публичных путей прибыли, экспериментальной экономики магазина, юнит-экономики, калькулятора/сохранённых планов, внешних расходов, полноты/диагностики и Telegram transport. Текущие кнопки/снимки и связанные public handler tests записаны в `DAILY_USE_SCREEN_INVENTORY_C00_2026-10-25.md`.
- Репрезентативный financial formatter: **470 chars / 472 UTF-16 units / 17 строк**; тестовый профиль с предупреждениями: **1 065 / 1 067**. Emoji transport stress разделился на два сообщения максимум по **3 800 UTF-16 units**.
- Подтверждённый UX-gap: `details_text` результата прибыли не входит в scoped cache и не имеет отдельной кнопки, хотя аналитика и export доступны из того же снимка. Подробный текст должен стать явным scoped view в C01. Проверка реальных live-периодов не выполнялась.
- Связанный экранный профиль `test_period_profit_compact_report_v1431_v1440.py`, `test_period_profit_analytics_runtime.py`, `test_product_unit_economics_telegram_ui.py`, `test_telegram_loading_feedback_v1451_v1460.py`: **31 passed, 1 deselected in 2.23s**. Один storage-backed test исключён из-за Windows ACL на `tmp_path`; полный suite — exact-head CI.
- C00 — аудит/схема без изменения production-кода или расчётов. Следующий этап C01; A04 закрывается только после C05.

### C01 — компактный финансовый отчёт и scoped детали (25.10.2026)

- Основные суммы теперь показываются с копейками и пробелами тысяч, денежные доли — от общей выручки. Для нулевой/отрицательной выручки доля остаётся неопределённой; отрицательные деньги сохраняют знак. Подпись результата сообщает, учтены ли себестоимость и полные внешние расходы.
- `📋 Подробности` открывает исходный detail text из того же owner/store/period snapshot (TTL 10 минут), без нового запроса к Ozon. Старый callback другого владельца/магазина остаётся отклонённым; возврат ведёт к той же сводке. Детали используют существующий splitter, keyboard остаётся на последней части.
- Короткий экран показывает приоритетную причину полноты плюс количество остальных; экран полноты и diagnostics сохраняют весь canonical список причин. Экспериментальный экран экономики проверяет ≤2 500 UTF-16 units для summary и ≤3 800 units на отправляемую деталь.
- C01 profile: пять модулей (`test_period_profit_compact_report_v1431_v1440.py`, `test_period_profit_analytics_runtime.py`, `test_experimental_store_economics.py`, `test_telegram_loading_feedback_v1451_v1460.py`, `test_period_profit_response.py`) — **74 passed, 1 deselected in 3.24s**. Исключён только production-factory `tmp_path` test из-за Windows ACL. Полный pytest локально не запускался.
- Измерения fixtures: approved compact 695 chars / 697 UTF-16 units; runtime partial report 557 / 558; synthetic details 7,350 chars / 7,700 units → 3 chunks, max 3,799 units. Это offline formatter/transport evidence, не реальный Telegram вызов.
- In-memory compile 7 changed Python files и `git diff --check` прошли. `compileall -q app tests` попытался писать в существующие `__pycache__` и завершился ACL `WinError 5`; этот результат не засчитан. Exact-head CI пока ожидает финальной интеграции.
- Изменения и тесты внесены в C01 acceptance `DAILY_USE_SCREEN_ACCEPTANCE_C01_2026-10-25.md`, пользовательскую инструкцию и проектную документацию. CI ещё не запущен; merge/deploy/live bot не выполнялись.
- C01 закрыт локально; следующий этап C02. A04 остаётся открыт до C05.

### C02 — действия из полноты и сохранение контекста (25.10.2026)

- Проверены completeness actions и прежние store/owner guards. Тесты подтверждают отказ stale cost-confirmation после смены магазина, отказ чужого/старого custom-period prompt, отсутствие переноса SKU в новую tenant scope, подтверждение external-expense write и отсутствие лишней кнопки выбора периода в завершении экспериментального сценария.
- Подтверждённый UX-gap: диагностика показывала «Обновить расчёт», но вела к общему меню, требуя повторно выбирать даты. Добавлен `period_profit_refresh:<view_id>` для explicit recalculation по точным датам исходного кешированного снимка. Callback проходит существующую owner/store/TTL проверку до чтения периода; неверный/устаревший снимок не вызывает источник; успешный refresh создаёт новую ревизию.
- Regression подтверждает сохранение периода 2026-08-01—2026-08-31, `compare_previous=True`, выдачу нового view ID и отсутствие запросов от чужого owner/другого store.
- Связанный профиль из 6 модулей: **105 passed, 9 deselected in 3.45s**. Исключены один production-factory и восемь external-expense `tmp_path` tests, блокируемых ACL на Windows; предыдущий непропущенный запуск упал на `PermissionError: WinError 5` setup/teardown, поэтому эти кейсы требуют CI.
- In-memory compile 4 изменённых Python файлов и `git diff --check` прошли. Точный refresh и анализ scope записаны в `DAILY_USE_NAVIGATION_ACCEPTANCE_C02_2026-10-25.md`; exact-head CI не запущен. Merge/deploy/live bot не выполнялись.
- C02 закрыт локально; следующий этап C03. A04 остаётся открыт до C05.

### C03 — ожидание, retry и late-result scope (25.10.2026)

- Проверены существующие Telegram callback dedup, runtime custom-period inflight, Ozon Retry 503, bounded request/time trace, safe HTTP 429/timeout diagnostics и progress/split transport. Бюджет и retry правила не расширялись.
- Подтверждён дефект: расчёт мог вернуть результат первоначального магазина после переключения на другой. `TelegramBotService` теперь проверяет resolved tenant scope после долгого read-only callback или текстового ответа; несовпадение показывает `TELEGRAM_CALCULATION_STORE_CHANGED`, а старые данные не доходят до пользователя. Новая точная кнопка `period_profit_refresh` добавлена в типы расчётных callback для общей дедупликации.
- C03 linked profile — **44 passed, 1 deselected in 3.04s**; исключён один `tmp_path` trace-export test из-за Windows ACL. Новые regressions покрывают callback и текстовый поздний ответ при смене магазина; существующие проверяют 429, timeout, retry limit, duplicate, exceptions и Telegram delivery.
- In-memory compile 3 изменённых Python файла и `git diff --check` прошли. Подробная приёмка: `DAILY_USE_RELIABILITY_ACCEPTANCE_C03_2026-10-25.md`. Exact-head CI ещё не запущен; merge/deploy/live bot не выполнялись.
- C03 закрыт локально; следующий этап C04. A04 остаётся открыт до C05.

### C04 — измерение источниковой работы (25.10.2026)

- Существующий runtime уже сохраняет периодный результат в owner/store-scoped snapshot: analytics, details, completeness, diagnostics, CSV/JSON и support export после первого query не запускают новый query-service вызов. Explicit refresh выполняет один новый запрос по сохранённым точным ISO-датам и создаёт новую ревизию.
- Добавлен воспроизводимый fake-source profile для batch 3 SKU. Результат: **1 catalog load, 3 SKU snapshots, 3 fake finance pages, 6 HTTP reservations, 0.06 fake seconds** (10 ms на каждую fake попытку). Все три строки готовы. Ранее существующие tests подтверждают один catalog load на build, shared root request budget и нулевые source reads для batch edits/exports.
- Связанный profile: **44 passed, 1 deselected in 1.93s**; исключён один production-factory test с `tmp_path` из-за Windows ACL. Три ключевые проверки отдельно: **3 passed in 1.01s**. `git diff --check` и in-memory compile будут повторены перед завершением C05.
- На UI fake seam невозможно вывести физическое число API attempts/finance pages для store report, поэтому они не выдаются за измеренные. Batch counts — искусственно заданная и явно маркированная fixture, не live latency Ozon. Абсолютный wall-clock CI threshold не вводился.
- Подтверждённой избыточной production работы нет, расчётные сервисы не менялись; baseline/ограничения записаны в `DAILY_USE_PERFORMANCE_ACCEPTANCE_C04_2026-10-25.md`. Следом C05.

### A04 preliminary — августовские источники (25.10.2026)

- Через bundled Python/OpenPyXL и локальный `daily_use_reconcile.py reference` read-only проверен `Отчет по начислениям_01.08.2026-31.08.2026 (2).xlsx`: период 01–31.08.2026, 38 864 строки, полный coverage, `net_accrual=177282.17`. Это совпадает с историческим сообщением бота; текущая ревизия сообщения не подтверждена без JSON export.
- Прямой read-only подсчёт реализации с детализации с 16-й строки дал 1 293 строки / 2 SKU / 5 356 реализованных / 2 возвращённых единицы. Строка 15 содержит индексы заголовков, отчего прежняя инвентаризация завысила строку и число SKU на единицу.
- 6 117 Analytics `ordered_units`, 5 356 реализованных единиц и число финансовых операций имеют разное зерно; они не сравниваются напрямую. Один акт cross-docking не подтверждает полное 56-дневное количество. Комиссия совпадает в историческом API diagnostic, но XLSX товарной реализации не имеет явного поля комиссии.
- Второго сопоставимого закрытого финансового периода и актуального bot JSON export нет. Исходники не изменялись; snapshot не изготовлялся из сообщения вручную. Предварительная матрица и точные ограничения: `DAILY_USE_A04_PRELIMINARY_SOURCE_RECHECK_2026-10-25.md`.
- A04 остаётся открыт до окончания C00–C05; C00 закрыт, следующий этап C01.

### D03 — checkout-bound update preflight (25.10.2026)

- Расширена lifecycle metadata one-way SHA-256 fingerprint нормализованного пути проекта; исходный путь не сохраняется. `start_bot.ps1` передаёт `APP_BUILD_PROJECT_ROOT`, status projection возвращает только fingerprint. Старые активные записи без поля и активный экземпляр из другого checkout блокируют автоматическую остановку.
- `request_graceful_stop` принимает ожидаемый checkout fingerprint и сверяет его перед loopback stop. PID остаётся неавторитетным; чужой и устаревший экземпляр не завершается.
- Проверка `tests/test_bot_update_preflight_service.py tests/test_bot_instance_lifecycle_service.py`: **24 passed in 10.54s** на Windows/Python 3.12. `py_compile`, PowerShell parser API и `git diff --check` прошли.
- Acceptance: `DAILY_USE_UPDATE_PREFLIGHT_ACCEPTANCE_D03_2026-10-25.md`. Ни один настоящий процесс не проверялся и не останавливался.

### D04 — сериализованное обновление до проверенной готовности (25.10.2026)

- Реализован `BotUpdateRuntimeService`; `update_bot.ps1` поддерживает read-only `-CheckOnly`, штатное обновление и `-NoStart`. Обновление разрешено только в проверенном `main` от canonical `origin/main`.
- Поток: безопасный identity check → явный fetch → preflight точного SHA → checkout-bound graceful stop → verified backup + повторная verify → трижды перепроверенный SHA/status → `git merge --ff-only <sha>` → зависимости → `compileall` → локальный `runtime_healthcheck` → запуск → polling readiness с точными revision и checkout. Повторные updater сериализованы OS kernel lock в private Git worktree directory.
- Ошибки после stop показывают остановленное состояние, проверенный backup path (если он есть) и `.\update_bot.ps1 -CheckOnly`; автооткат/restore не производится. Уже актуальная версия не останавливается и не перезапускается. Ни один subprocess stderr и секрет не выводятся.
- Изолированный Windows/Python 3.12 профиль: `tests/test_bot_update_runtime_service.py tests/test_bot_update_preflight_service.py tests/test_bot_backup_service.py tests/test_bot_instance_lifecycle_service.py` — **54 passed in 11.84s**. Проверены happy paths, update failure boundaries, requirements install, revision races, lock contention, no-start, exact readiness и redaction.
- Python compilation прошла; PowerShell parser API — 0 ошибок для update/start scripts; `git diff --check` прошёл. Реальные fetch, backup, stop, install и bot start не вызывались.
- Acceptance: `DAILY_USE_UPDATE_ACCEPTANCE_D04_2026-10-25.md`. Последующий D05 закрыт ниже.

### D05 — статус экземпляра и безопасные причины ошибок (25.10.2026)

- `telegram_bot_control status` / `status_bot.ps1` раздельно показывают lifecycle polling и offline-проверку локальных настроек; отображаются ревизия, время, режим, совпадение checkout и известный safe failure code. Полный путь и fingerprint не печатаются.
- `stop_bot.ps1` передаёт expected checkout fingerprint; остановка чужой или старой записи без fingerprint отклоняется. Канонический runner сохраняет только enum startup/polling failure code и не печатает текст исключения; старые lifecycle metadata остаются совместимыми.
- `AppBuildMetadataService` и allowlisted Period Profit support JSON включают проверенный foreground/background mode. Размер support JSON остаётся ограниченным, схема восстанавливается из allowlist.
- Связанный Windows/Python 3.12 профиль: **87 passed in 13.27s**. Включает missing/invalid env/key/storage, чужой checkout, safe failure persistence/redaction, startup/polling exceptions, support export, lifecycle, updater и backup tests. Python compile прошёл; PowerShell parser — 0 ошибок для четырёх scripts.
- Настоящий бот, remote, `.env` и продавецкие данные не использовались. Healthcheck не подтверждает доступность Ozon/финансовый результат; эта информация остаётся в соответствующих расчётных диагностических статусах.
- Acceptance: `DAILY_USE_STATUS_DIAGNOSTICS_ACCEPTANCE_D05_2026-10-25.md`. Следующий этап D06.

### D06 — ограниченная устойчивость и recovery runbook (25.10.2026)

- Bounded synthetic run выполнил 64 расчёта и 64 экспорта, 12 ревизий сохранённого плана, чтение cost/expense в двух tenant scopes и 8 fake start/status/stop циклов. Максимум цикла 0.297 s; thread delta 0; handle delta +2; plan DB 61,440 bytes; tenant storage 2 files / 114,688 bytes; lifecycle state 2 files / 364 bytes.
- Сбои TTL/cache eviction, invalid clock, stop timeout, interrupted backup, failed restore staging и checkpoint resume покрыты; D06 профиль — **11 passed in 3.74s**.
- Runbook и журнал 24–72h переданы владельцу, статус наблюдения `USER_VALIDATION_PENDING`. Настоящий бот, user backup и Ozon/Telegram не запускались.
- Acceptance: `DAILY_USE_RESILIENCE_ACCEPTANCE_D06_2026-10-25.md`.

### E00 — связанная регрессия (25.10.2026)

- Сквозной isolated profile связал reconciliation, completeness, report/details/expense/refresh/export, планы, стоимость, внешний расход, verified backup, dry-run restore, чтение после восстановления и tenant isolation.
- Первый запуск: 349 passed / 1 failed из-за ожидаемого metadata object без нового allowlisted `mode`; после обновления fixture весь профиль прошёл: **350 passed in 22.70s**. Это local isolated evidence, не exact-head CI и не production acceptance.
- Текущий exact-revision bot JSON и полный 56-day cross-docking snapshot отсутствуют; внешний evidence остаётся pending.
- Acceptance: `DAILY_USE_END_TO_END_LINKED_ACCEPTANCE_E00_2026-10-25.md`.

### E01 — reviewable PR stack и exact-head CI (25.10.2026)

- Опубликованы draft PR: #713 (`e014f278`, base #712 head `698c9f8`), #714 corrected (`7ec47ef6`, base #713), #715 rebased (`40c99b69`, base #714), #716 rebased (`e578779c`, base #715), #717 E acceptance (base #716; head обновляется с handoff). Run #713 **40181639324** завершён `success`.
- Первые runs #714 **40181793806**, #715 **40181869351**, #716 **40181908157** завершились `failure`: 3 теста, остальные прошли. Исправлено: B04 удалил helper, который downstream использовал только для SKU identity; добавлен identity-only projection без возврата cost. Compact-money assertions обновлены до двух знаков. Подробности `DAILY_USE_CI_REGRESSION_FIX_2026-10-25.md`.
- Свежие corrected-head runs #714 **40182473893**, #715 **40182505098**, #716 **40182519871** завершились `success`: Windows/Linux full tests and compile, Linux Docker build/runtime smoke. Позже R1–R3 были внесены в #715 и forwarded; новые exact runs #715 `40185833721`, #716 `40185869091`, #717 `40186507007` также прошли. На #717 проверено 3,728 tests per platform и Linux Docker build/runtime smoke. Старые failures superseded. Слияние, развёртывание и настоящий запуск запрещены рамками task.

### E02 — пакет независимого review (25.10.2026)

- Подготовлен `DAILY_USE_READINESS_REVIEW_HANDOFF_2026-10-25.md`: порядок зависимостей PR, base/head, architecture map, compatibility boundaries, риски и тестовые evidence.
- Классификация: **Architecture Review Required** из-за новых backup/restore и updater/lifecycle границ. Handoff содержит exact #713–#716 heads and CI. E PR SHA and run will be available in current PR metadata after publication; final Verify must pass.

### E03 — пакет внешней приёмки владельца (25.10.2026)

- В `DAILY_USE_A05_OWNER_EVIDENCE_REQUEST_2026-10-25.md` запрошены только точный build revision и обезличенный current bot JSON за проверенный августовский период, плюс агрегированный read-only 56-day cross-docking summary, если доступен.
- Подготовлен 24–72h owner observation log. Результаты не получены, поэтому `USER_VALIDATION_PENDING`; synthetic CI не объявляется эксплуатационной приёмкой.

## Шаблон записи каждого этапа

```text
Stage / дата:
Status:
Branch / base / head / PR:
Что реализовано или что уже существовало:
Подтверждённый дефект / продуктовый gap / ограничение источника:
Файлы и изменение контрактов:
Проверка: команда, passed/failed/errors, окружение:
Реальные отчёты: что доказано и какой date/source basis:
CI: head/run URL/Windows/Linux/Docker:
Защищённые данные/секреты сохранены:
Непроверенное / внешнее evidence:
Следующий доступный этап:
```

После compaction продолжать по последней записи и фактическому diff. Не считать отсутствующее evidence нулём, stage implemented — verified, а синтетическую проверку — успешной реальной эксплуатацией. Не выполнять merge/deploy/live restart.

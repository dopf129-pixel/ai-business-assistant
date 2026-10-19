# Журнал исполнения GPT Luna — planning workspace H–O

Статус: **IMPLEMENTED — O01 code verification зелёный; O02 handoff опубликован, независимый review ожидается**. Реализация поручения начата 19.10.2026.
ТЗ: `LUNA_PLANNING_WORKSPACE_TASK_2026-10-19.md`.
Основание: `PLANNING_WORKSPACE_AUDIT_2026-10-19.md`.

## Точка продолжения

- Текущий этап: **O02 — handoff опубликован в PR #708; проверить latest Verify для текущего PR head и передать пакет независимому reviewer**.
- Проверенная база: `main` на `722f368526c278b701cbfd69f3dbb9a474d52386`, подтверждена актуальной `origin/main` и успешным GitHub Verify `39165543772`.
- Рабочая ветка: `codex/planning-workspace-20261019`.
- Подготовительный commit ТЗ и аудита на feature branch: `79fc0a72 Document planning workspace program and baseline`.
- H00 завершён: исходная точка сохранена; пользовательские данные и временные каталоги pytest не включены в commit.
- Последнее широкое локальное окно H–O: **249 passed** на Windows/Python 3.12 с отключённым pytest tmpdir/cache и workspace-local temp plugin; compileall / PowerShell AST / diff-check фиксируются после окончательного docs patch.
- Commits: H `050563b6 Add safe local bot lifecycle controls`; I `4e6b1bc1 Add tenant-scoped saved planning repository`; J–K `b66ebc45 Add bounded ad caps and sales mix planning`; L–N/O integration `a5041e5d Integrate planning comparisons and exports`.
- PR stack: #705 → #706 → #707 → #708; exact base/head, run IDs and tested merge-ref SHAs in `PLANNING_WORKSPACE_REVIEW_HANDOFF_2026-10-19.md`.
- Initial Verify runs on all four PR merge refs are green: #705 **3,443 passed**, #706 **3,454 passed**, #707 **3,466 passed**, #708 **3,497 passed** on both Windows and Linux; Docker build/runtime smoke passed on each full-verification job.
- Review handoff is included in PR #708. The code head `a5041e5d7355d593bae6dacbc20c1590930eed21` passed full Windows/Linux and Docker verification; the current documentation-only head must be checked through the latest PR #708 Verify. Independent architecture review follows; no merge/deploy.
- Решения владельца: дополнительных вопросов на момент подготовки нет; product defaults закреплены в разделе 5 ТЗ.

## Что сохранить

- Существующие modified `data/tasks.json`, `data/users.json`, `data/tasks.json.lock` и локальные temporary directories не включать в PR.
- Hash `data/tasks.json` при подготовке: `AC6E856BD17E17029151C25C0D29DE414E553CE7C3607CB8DED9EC22E052110F`.
- Hash `data/users.json` при подготовке: `900FFAE4759D8CCE6A8E462C8F6B9C3CF64DC88F3388EDB7CDBEB157736AF63A`.
- Hashes — свидетельство исходной точки, не команда откатить позднейшие легитимные изменения пользователя. В H00 снять новую исходную точку.
- Изменения документации этого поручения — отдельная подготовительная работа; не считать их implementation H00.

## Матрица исполнения

| Модуль | Этапы | Статус | PR / code SHA / проверки |
|---|---|---|---|
| H — база и lifecycle | H00, H01, H02, H03, H04 | H00–H04 VERIFIED; independent architecture review pending | local H profile 40; PR #705 Verify 3,443 passed Windows/Linux + Docker smoke |
| I — сохранённые планы | I00, I01, I02, I03, I04, I05 | I00–I05 VERIFIED; independent architecture review pending | local H/I profile 99; PR #706 Verify 3,454 passed Windows/Linux + Docker smoke |
| J — рекламный предел | J00, J01, J02, J03 | J00–J03 VERIFIED; independent architecture review pending | local J profile 63; PR #707 Verify 3,466 passed Windows/Linux + Docker smoke |
| K — объём продаж | K00, K01, K02, K03, K04 | K00–K04 VERIFIED; independent architecture review pending | local K profile 27; PR #707 Verify 3,466 passed Windows/Linux + Docker smoke |
| L — план и факт | L00, L01, L02, L03, L04 | L00–L04 VERIFIED; independent architecture review pending | combined L/M/N 68; PR #708 Verify 3,497 passed Windows/Linux + Docker smoke |
| M — готовность | M00, M01, M02, M03 | M00–M03 VERIFIED; independent architecture review pending | direct edit CAS and conflict regression; PR #708 full CI green |
| N — сравнение/экспорт | N00, N01, N02, N03 | N00–N03 VERIFIED; independent architecture review pending | comparison and four user-report exports; PR #708 full CI green |
| O — приёмка | O00, O01, O02 | O00/O01 VERIFIED for code head; O02 packet published; independent review pending | PR #708 latest exact-head Verify is the gate for the docs-only handoff; previous code-head Verify: 3,497 passed on both platforms + Docker |

## Шаблон записи этапа

Каждый stage записывать отдельно; групповой статус модуля не заменяет evidence этапов.

```tex
Stage:
Status: IN_PROGRESS / IMPLEMENTED / VERIFIED / BLOCKED / NEEDS_REVIEW
Дата:
Branch / base / code SHA:
Что изменено и почему:
Контракты и границы:
Tests: точная команда, количество passed/failed/errors/deselected, причина ограничений:
CI: run URL, head_sha, итог Windows/Linux/Docker:
Документация:
Пользовательские данные сохранены:
Оставшиеся риски/блокеры:
Следующий конкретный шаг:


## Проверки подготовки ТЗ

- Прочитаны production code и документация перечисленных в audit границ.
- Повторно проверены GitHub metadata merged PR #702 и successful jobs main Verify 39165543772.
- Пять синтетических вариантов рекламной ставки и второй SKU проверены прямыми вызовами действующих UnitPriceScenarioService/TaxService; aggregate tax примеров также проверен. Это не тесты будущей реализации.
- Новый pytest не запускался: поручение изменяет только документацию. Итоги реализации H–O пока отсутствуют.
- Структурная проверка ТЗ: все 36 этапов H00–O02 присутствуют ровно один раз и идут в нужном порядке; явные `app/...py` references существуют, fences парные, trailing whitespace отсутствует. `git diff --check` successful.
- Числа 15.2/15.3 дополнительно сверены агрегированными вызовами TaxService; bridge 15.4 — точной арифметикой. Hashes обоих пользовательских JSON после подготовки совпали с исходными.

## Блокеры и вопросы

Нет открытого обязательного бизнес-решения при подготовке. Известное ограничение local Windows pytest temp ACL требует честного учёта и чистого CI при реализации, а не обращения к данным продавца.

## Исполнение

### H00 — фактическая база

Status: **VERIFIED**
Дата: 2026-10-19
Branch / base / code SHA: `codex/planning-workspace-20261019` / `722f368526c278b701cbfd69f3dbb9a474d52386` / `79fc0a72` (docs-only checkpoint).
Что проверено: рабочая ветка создана от проверенного `main`; после подготовки новых коммитов `origin/main` остался на том же SHA. Осмотрены production entrypoint, PTB lifecycle, PowerShell bootstrap, test contracts, `.gitignore`, архитектурные решения. Уже существующий `build_application()` остаётся сетево-инертным; production `main()` вызывает `run_polling()`. В проекте уже есть кроссплатформенная kernel file lock реализация, которую можно использовать как проверенный образец.
Сохранность данных: `data/tasks.json` SHA-256 `AC6E856BD17E17029151C25C0D29DE414E553CE7C3607CB8DED9EC22E052110F`; `data/users.json` SHA-256 `900FFAE4759D8CCE6A8E462C8F6B9C3CF64DC88F3388EDB7CDBEB157736AF63A`. Изменения `data/*`, `data/tasks.json.lock` и локальные pytest directories оставлены вне index/commit. Временные каталоги не читались и не удалялись.
CI baseline: GitHub Verify `39165543772` successful для того же base SHA: Windows/Python 3.12, Linux/Python 3.11, полный pytest (3 425 passed на каждой платформе), compileall, Docker build/runtime smoke. Это baseline, не результат нового lifecycle-кода.
Локальные проверки H00: код и документация прочитаны; полный pytest не запускался, так как на H00 не было implementation changes и рабочая копия содержит ACL-ограниченные scratch-папки.
Блокеры: нет.
Следующий шаг: добавить кроссплатформенный singleton guard и authenticated loopback stop control, не затрагивая `build_application()`.

### H01 — контракт одного локального экземпляра

Status: **IN_PROGRESS**
Подтверждённая граница PTB: `Application.stop_running()` доступен в установленной версии и предназначен для graceful exit из `run_polling()`; `build_application()` не будет захватывать lifecycle lock. Предварительный контракт: OS lock удерживается открытым весь срок жизни процесса; control channel loopback принимает только запрос с совпавшими generation и случайным секретом из пользовательского приватного состояния; PID не используется для завершения процесса. Разные token fingerprint получают отдельные lock namespace, сами токены нигде не записываются.
Следующий шаг: зафиксировать схему service/runtime states, затем реализовать менеджер с injected token/clock/path и тестами на contention, token isolation, corrupt metadata и отказ lock backend.

### H01 — контракт одного локального экземпляра

Status: **VERIFIED**
Branch / base: `codex/planning-workspace-20261019` / `722f368526c278b701cbfd69f3dbb9a474d52386`.
Контракт зафиксирован в `project_brain/DECISIONS.md` Decision 046: lock namespace = SHA-256 token fingerprint, held OS lock = owner; generation+random secret authenticate only loopback control. `build_application()` по-прежнему не захватывает lock и не открывает сеть. Plaintext token нигде в state file/log/status не записывается; PID не вызывает сигналов/kill.

### H02 — управляемый запуск, статус и остановка

Status: **VERIFIED**
Изменения: `start_bot.ps1` сохраняет видимый режим по умолчанию и принимает `-Background`; `status_bot.ps1` и `stop_bot.ps1` используют локальный Python CLI. Состояние RUNNING публикуется только когда одновременно `Updater.running` и `Application.running`; PTB `post_stop/post_shutdown` закрывают сервер, а команда stop ожидает освобождения lock не более 15 секунд. Тайм-аут и повреждённые metadata не завершают процесс.

### H03 — lifecycle regression coverage

Status: **VERIFIED**
Локальная команда: `python -m pytest -p no:tmpdir -p no:cacheprovider -p h03_temp_fixture_plugin -q tests/test_bot_instance_lifecycle_service.py tests/test_telegram_runtime_health_shutdown_contract.py tests/test_telegram_runtime_dependencies.py tests/test_windows_local_handoff_readiness.py tests/test_telegram_bot_control_cli.py --tb=short`. Результат: **40 passed**, Windows, 2.51 s. Временный `h03_temp_fixture_plugin.py` переопределяет только `tmp_path` в доступном user workspace после того, как стандартные pytest tmp/cache каталоги стабильно получали WinError 5; он не является production/test-suite code и не должен попасть в PR. Профиль включает два отдельных токена, реальный subprocess lock contention, аварийный startup release, simulated stale PID reuse, RUNNING readiness, STARTING stop, repeated stop, timeout/no-force, corrupt metadata, wrong/non-ASCII secret, token non-disclosure и CLI output.
Дополнительные проверки: `python -m compileall -q app tests` — PASS; PowerShell `Parser.ParseFile` для `start_bot.ps1`, `status_bot.ps1`, `stop_bot.ps1` — PASS; scoped `git diff --check` — PASS. Реальный Telegram bot, Ozon API и токен не запускались/не использовались тестами.

### H04 — architecture review и приёмка

Status: **VERIFIED for PR #705 head**.
README, guide, ARCHITECTURE, CHANGELOG, CURRENT_STATE, ROADMAP, TEST_MAP и Decision 046 обновлены. Review checkpoint обнаружил раннюю публикацию RUNNING в PTB `post_init`; исправлено на readiness watcher, который проверяет polling и Application.start. Stop допускается в STARTING после bind IPC. Verify #705 (`39175656753`) прошёл: Windows/Linux **3,443 passed**, compile и production Docker smoke successful. Независимый architecture review остаётся кросс-модульным O02 этапом; локальный full-suite ACL инцидент описан ниже и не влияет на чистый CI.

### I00 — durable planning contract

Status: **VERIFIED** · 2026-10-19 · branch `codex/planning-workspace-20261019`.
Decision 047 добавлен: recipe, historical projection и transient runtime state разделены; persisted payload — строгая allowlist, owner/store scope обязателен; внешние данные, credentials, callback/runtime secrets не принимаются.

### I01 — tenant SQLite repository

Status: **VERIFIED**. Добавлены таблицы `planning_schema`, `planning_documents`, `planning_revisions`, `planning_idempotency` в существующую tenant DB, schema version 1. `BEGIN IMMEDIATE`, expected revision CAS, idempotency key, ограничения 200 документов / 20 ревизий / 64 KiB; write успех возвращается только после commit. Тесты: legacy table preservation, owner/store isolation, CAS concurrent winner, repeated idempotency, archive/restore/confirmed delete, invalid payload/time, storage failure, corrupted record and unsupported future schema.

### I02 — explicit save from current editors

Status: **VERIFIED**. Добавлены публичные callbacks сохранения single/batch редактора и именование плана. Перед записью capture повторно читается по точному `scenario_id|batch_id`, version и tenant scope; прежняя кнопка после изменения сценария не может сохранить новое состояние. Локальное сохранение не затрагивает seller-cost/settings/finance repositories.

### I03 — «Мои планы», просмотр и продолжение

Status: **VERIFIED**. Публичный handler поддерживает страницы активных/архивных планов, detail, revisions, copy, rename, archive, restore, confirmed delete, historical continue and explicit refresh. Просмотр после создания новых repository/service/runtime objects читает SQLite и не вызывает Ozon. Продолжение строит transient scenario с нулевым source TTL и исторической пометкой.

### I04 — история, пределы, деградация

Status: **VERIFIED locally**. Новая regression проверяет stale title ticket, invalid clock (не создаёт пустой success), синтаксически повреждённый документ и payload будущей schema (controlled status; список остаётся доступен). После explicit exact-identity refresh manual price сохраняется, а callback добавления ревизии bound к expected revision; параллельная новая версия приводит к конфликту без перезаписи.

### I05 — module acceptance

Status: **VERIFIED for PR #706 head**. Public-handler acceptance охватывает single save → runtime restart → historical reopen/continue без повторного source call, batch save/continue с пометкой stale, CRUD и refresh → CAS update с ручным override; добавлен explicit copy path. Combined H/I targeted profile на Windows/Python 3.12: **99 passed**. Verify #706 (`39175669828`) прошёл: Windows/Linux **3,454 passed**, compile and Docker smoke successful.

Точная команда:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'app'
$env:CODEX_LOCAL_TEST_TMP_ROOT = Join-Path $PWD '.pytest-h03-manual-data'
.\.venv\Scripts\python.exe -m pytest -p no:tmpdir -p no:cacheprovider -p h03_temp_fixture_plugin -q tests/test_planning_workspace_repository.py tests/test_saved_planning_plan_telegram_flow.py tests/test_unit_price_scenario_telegram_runtime.py tests/test_telegram_unit_price_batch_plan_runtime_service.py tests/test_product_workbench_acceptance.py tests/test_telegram_runtime_dependencies.py tests/test_telegram_runtime_health_shutdown_contract.py tests/test_telegram_bot_control_cli.py tests/test_bot_instance_lifecycle_service.py --tb=short
```

Полный локальный suite с `AI_ASSISTANT_STORAGE_ROOT` в `.pytest-h03-manual-data/isolated-storage` завершился **3431 passed, 28 failed**. Семь multi-tenant тестов столкнулись с общей persisted storage между тестами; остальные 21 сбой связаны с системными `%TEMP%` ACL (`WinError 5` / SQLite unable to open). Тесты также изменили корневые `data/tasks.json` и `data/users.json` несмотря на указанное хранилище. Предшествующие этому прогону контрольные суммы из H00 были `AC6E856BD17E17029151C25C0D29DE414E553CE7C3607CB8DED9EC22E052110F` и `900FFAE4759D8CCE6A8E462C8F6B9C3CF64DC88F3388EDB7CDBEB157736AF63A`; текущие наблюдаемые суммы — `8F7FFF206A4748DE6EFB3E5DCABABD07E3341188A7326383A21D966B73710698` и `0B12986702D5C62B8A410EE4B3B3228923FF72BA897F18FF62FEF556CDA88409`. В workspace не найдено точной копии обеих исходных версий, автоматическое восстановление не предпринималось. Файлы оставлены нетронутыми после прогона, не staged/committed. Не запускать локальный полный suite повторно.

Успешные проверки: H/I focused profile **99 passed**, compileall/diff-check PASS; затем PR #706 exact stacked-head Verify `39175669828` прошёл полные Windows/Linux suite (**3,454 passed** обе платформы) и production Docker smoke. PR I содержит только SQLite repository/service и прямые tests; production wiring приходит в зависимом интеграционном PR #708. Локальный full-suite инцидент и актуальные hashes сохранены как есть; existing scratch directories не включены в Git.

### J00 — рекламный предел: контракт

Status: **VERIFIED LOCALLY** · 2026-10-19.
`UnitPriceAdvertisingCapService` использует существующий `UnitPriceScenarioService` и не загружает источники/не пишет факты. Rate grid — целые 0–10 000 ticks (0,01 п.п.); solver проверяет монотонность прибыли и маржи при 0/25/50/75/100%, дважды проверяет крайние точки поисков и подтверждает найденный tick и соседний следующий. Все сравнения идут по каноническим Decimal из рассчитанных компонентов, не по форматированным строкам. При недоказанной границе, missing/invalid input или non-monotonic расчет закрывается без cap.

### J01 — bounded solver

Status: **VERIFIED LOCALLY**.
Лимит 128 прямых вычислений включает расчёт текущей рекламы, проверки монотонности, два двоичных поиска и принудительное повторное подтверждение обоих результатов. Числовые regression tests покрывают пример ТЗ (13,20% для цели 25%; 38,20% безубыточность), следующий шаг, все налоговые режимы, минимум налога, отсутствующее значение против явного 0, недостижимую цель и отказ на искусственно немонотонном калькуляторе.

### J02 — Telegram single/batch/saved plan

Status: **VERIFIED LOCALLY**.
Single требует явную целевую маржу, показывает цену продавца, текущую долю/сумму, пределы, запас в п.п./₽/шт. и freshness. Apply привязан к user/store/SKU/snapshot/scenario version и перед локальной правкой повторно вызывает канонический calculator; старый повторный callback после apply становится stale. Batch cap привязан к row+batch version+source version; историческая saved-plan карточка только отображает предел и не предлагает напрямую перенести старое значение. Campaign writes и новые source calls в тестах отсутствуют.
Документация: README, Telegram guide, ARCHITECTURE, CHANGELOG, CURRENT_STATE, ROADMAP и TEST_MAP обновлены.

### J03 — acceptance checkpoint

Status: **VERIFIED for PR #707 head**. Связанный профиль Windows/Python 3.12:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'app'
$env:PYTHON_DOTENV_DISABLED = '1'
$env:CODEX_LOCAL_TEST_TMP_ROOT = Join-Path $PWD '.pytest-h03-manual-data\j-tests'
New-Item -ItemType Directory -Force -Path $env:CODEX_LOCAL_TEST_TMP_ROOT | Out-Null
.\.venv\Scripts\python.exe -m pytest -p no:tmpdir -p no:cacheprovider -p h03_temp_fixture_plugin -q tests/test_unit_price_advertising_cap_service.py tests/test_unit_price_scenario_telegram_runtime.py tests/test_telegram_unit_price_batch_plan_runtime_service.py tests/test_saved_planning_plan_telegram_flow.py --tb=short
```

Result: **63 passed**. The public-flow regressions prove no extra Ozon reads, fresh-version-only local apply, stale replay rejection and read-only historical view. `compileall -q app tests` passed before current J runtime integration was completed; rerun it and scoped diff-check at the next J acceptance checkpoint. No full local pytest rerun: the previous full attempt was **3431 passed / 28 failed** (seven shared-storage cross-test failures and 21 Windows temp ACL failures) and modified local `data/tasks.json`/`data/users.json`. Initial and post-run SHA-256 values are recorded above and in CURRENT_STATE; original exact file copies were unavailable, so no restoration was attempted. Both local files plus `data/tasks.json.lock` remain outside Git. Do not stage/restore them or re-run the full suite locally.

Verify #707 (`39175679778`) passed the full Windows/Linux suites with **3,466 passed** on both platforms and successful production Docker smoke. The commit isolates solver/economics cores; public workflow wiring is in dependent PR #708. Proceeded to K00 after completing J targeted acceptance.

### K00 — контракт sales mix

Status: **VERIFIED LOCALLY** · 2026-10-19.
Вводится период, точная сохранённая identity каждого SKU и вручную подтверждённое количество именно успешных продаж; `None` остаётся неизвестным, `0` допустим только при явном вводе/кнопке. До 10 SKU и до 50 дополнительных расходов за период. Дополнительные расходы хранятся только в planning revision и не попадают в таблицу внешних расходов. История документа остаётся отдельной от финансового факта.

### K01 — агрегирование компонентов и один налог

Status: **VERIFIED LOCALLY**.
Добавлен `UnitPriceScenarioService.calculate_components_only`: canonical one-sale calculator отдаёт округлённые компоненты без повторного налога; aggregate service умножает components на целое Q в Decimal и вызывает действующий `TaxService` ровно один раз при полной и единой налоговой политике. Minimum tax применяется к суммарной группе, а не суммируется из построчных налогов. Partial inputs показывают confirmed subtotal, но tax/profit/margin всей группы остаются `null`. В `calculate_components_only` отдельно возвращается округлённая себестоимость для построчного вклада; обычный сценарий одной продажи не меняет DTO.

### K02 — Telegram ввод и revision CAS

Status: **VERIFIED LOCALLY**.
В `TelegramSavedPlanningPlanRuntimeService` добавлен flow period → quantity per exact row → explicit fixed-expense count/list (включая подтверждённый пустой список) → preview → user confirmation. Input tickets bound к owner/store/document/revision/ticket. После независимой проверки preview ticket повторно сверяется под lock непосредственно перед CAS write; конкурентная замена draft не сохраняет старый состав. Изменение документа — отдельная revision. Источники не вызываются.

### K03 — подробное представление и рекламные пределы

Status: **VERIFIED LOCALLY**.
Preview показывает Q, price per unit, total revenue/COGS/commission/ad/fees и pre-tax SKU contribution, общие points/expenses/tax/profit/margin и наименования фиксированных расходов. Сумма individual per-SKU advertising caps показывается только если target задан, состав и налог полны, все cap outcomes подтверждены; UI прямо говорит, что сумма не является group optimization и не гарантирует group margin. Неизвестные строки не преобразуются в нулевые.

### K04 — локальная связанная проверка

Status: **VERIFIED for PR #707 head**. K targeted profile: **27 passed**; Verify #707 (`39175679778`) passed Windows/Linux **3,466 tests each** plus production Docker smoke. The connected Telegram/UI and cross-module acceptance is covered by the dependent top PR #708.
Точная Windows/Python 3.12 команда:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'app'
$env:PYTHON_DOTENV_DISABLED = '1'
$env:CODEX_LOCAL_TEST_TMP_ROOT = Join-Path $PWD '.pytest-h03-manual-data\k-tests'
New-Item -ItemType Directory -Force -Path $env:CODEX_LOCAL_TEST_TMP_ROOT | Out-Null
.\.venv\Scripts\python.exe -m pytest -p no:tmpdir -p no:cacheprovider -p h03_temp_fixture_plugin -q tests/test_sales_mix_planning_service.py tests/test_planning_workspace_repository.py::test_sales_mix_persists_explicit_unknown_quantity_and_rejects_bad_scope tests/test_saved_planning_plan_telegram_flow.py::test_sales_mix_public_flow_confirms_zero_expenses_and_saves_revision_without_source_reads tests/test_saved_planning_plan_telegram_flow.py::test_sales_mix_result_shows_per_sku_components_and_price_times_quantity tests/test_unit_price_scenario_service.py tests/test_unit_price_advertising_cap_service.py --tb=short
```

Result: **27 passed, 0 failed**. Проверены обязательные 15.2/15.3, округление money component × Q, общий minimum tax, explicit zero/unknown, partial result, mixed tax, fixed expense once, public preview, exact saved-plan revision, no source read, stale confirm race, detailed component display and individually solved cap sum caveat. `compileall`, PowerShell parse and diff-check passed at final acceptance. Clean Windows/Linux full suite and Docker smoke evidence is Verify #707 as listed above. Full local pytest remains suspended after the recorded workspace incident.

Implementation SHA for the J–K calculation core: `b66ebc45686e276c76bfcb4173c92cade6100c9c`; PR #707. User data policy сохранена: `data/tasks.json`, `data/users.json`, lock и все local ACL scratch directories не staged, не восстановлены и не удалены.

Следующий шаг: исполнить K04 technical checks; затем продолжить L00 и строить фактическую projection поверх существующего канонического period/SKU report.

### L00–L03 — plan/fact projection

Status: **VERIFIED LOCALLY**.
`PeriodProfitPlanFactComparisonService` остаётся pure projection: сравнивает только точный owner/store, период и набор SKU, берёт завершённые факты через существующий SKU runtime/query один раз и строит revenue bridge в Decimal. При неполной/несопоставимой базе прибыльная дельта имеет явный `NOT_COMPARABLE` status. Результат сохраняется в scoped transient snapshot; экран, детали и выгрузки используют один snapshot и не читают Ozon повторно.

### L04 — приёмка plan/fact

Status: **VERIFIED LOCALLY**.
Проверены exact identity/period, explicit unknown и zero quantity, mismatched expense scope, canonical finalized query, bridge, snapshot expiry и отсутствие повторных источников. В итоговом связном H–O профиле затронутые модули входят в **249 passed**.

### M00–M02 — готовность и редактирование

Status: **VERIFIED LOCALLY**.
`PlanningPlanReadinessService` отдельно показывает готовность расчёта, исторические допущения и состояние сравнения с фактом. Ссылки открывают только нужную строку/поле или конкретное неизвестное количество. Изменение проходит preview и expected-revision CAS; navigation/store switch/reset очищают временные edit tickets. Регрессии покрывают явное сохранение новой single revision и конфликт, если конкурент уже опубликовал более новую версию.

### M03 — приёмка готовности

Status: **VERIFIED LOCALLY**.
Целевые readiness/edit tests, batch selected-row edit и сохранённый flow включены в итоговый H–O профиль (**249 passed**); отдельная L/M/N связанная проверка ранее дала **68 passed**. При неполном вводе экран не объявляет план готовым и не переписывает пользовательские факты.

### N00–N02 — сравнение и выгрузка

Status: **VERIFIED LOCALLY**.
`PlanningPlanComparisonService` сравнивает две сохранённые ревизии в одном owner/store scope и только по сопоставимым историческим расчетам. Несовпадающая версия расчёта/период/состав/policy сохраняет видимость изменений inputs, но скрывает итоговую дельту прибыли/маржи. Экспорт `saved_plan`, `advertising_cap`, `sales_mix`, `plan_comparison` добавлен в существующие serializer/service/sender. Пользовательский экспорт — отдельная авторизованная projection; diagnostic allowlist не получает деньги, названия и идентификаторы. Снимки не инициируют повторный Ozon-запрос.

### N03 — руководство и приёмка N

Status: **VERIFIED LOCALLY**.
Public Telegram comparison, CSV/JSON kinds, saved snapshot delivery, Unicode and formula-safe serializer paths покрыты targeted regressions; `tests/test_planning_plan_comparison_service.py` и saved-plan flow проверяют incompatibility и historical semantics. Полная новая CI приёмка ожидается на PR head.

### O00 — сквозные пользовательские сценарии

Status: **IMPLEMENTED; targeted acceptance passed locally**.
Текущие regression flows связывают single/batch edits, historical save/continue, advertising caps, quantity/expenses preview, plan/fact, readiness navigation, comparison and exports. В итоговом targeted профиле перечисленные в O01 модульные границы дали **249 passed**. Живой Telegram/Ozon и реальные учётные записи не запускались.

### O01 — итоговая техническая приёмка

Status: **VERIFIED for code head `a5041e5d`; latest docs-only PR head is tracked by GitHub Verify**.
Финальная Windows/Python 3.12 связанная команда, выполненная с изоляцией локального тестового temp root, завершилась **249 passed in 9.98s**. Команда включила lifecycle, planning repository/runtime, ad caps, sales mix, plan/fact, readiness, comparison/export, Telegram transport/document, legacy overview/sensitivity and return diagnostic regression modules. Два предварительных вызова pytest без сбора тестов из-за неверно указанного test path завершились до выполнения каких-либо тестов; окончательная команда использовала проверенные пути.

Также после реализации: `python -m compileall -q app tests` — **PASS**; PowerShell AST parse `start_bot.ps1`, `status_bot.ps1`, `stop_bot.ps1` — **PASS**; `git diff --check` — **PASS**. PR Verify runs завершены: #705 run `39175656753` — **3443 passed** Windows/Linux; #706 `39175669828` — **3454 passed** обе платформы; #707 `39175679778` — **3466 passed** обе платформы; #708 `39175690904` — **3497 passed** обе платформы; на каждом Linux full-verification также успешно выполнил production Docker build и runtime smoke. Handoff merge-ref SHA / artifact reference указан в отдельном review handoff. Последующий docs-only commit handoff обновит PR #708 head и требует повторного CI. Текущие SHA пользовательских data — tasks `8F7FFF206A4748DE6EFB3E5DCABABD07E3341188A7326383A21D966B73710698`, users `0B12986702D5C62B8A410EE4B3B3228923FF72BA897F18FF62FEF556CDA88409`. Data, lock и ACL-limited scratch paths остаются вне Git. Full local pytest повторно не запускать.

Команда итогового targeted прогона:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'app'
$env:PYTHON_DOTENV_DISABLED = '1'
$env:CODEX_LOCAL_TEST_TMP_ROOT = Join-Path $PWD '.pytest-h03-manual-data\h-o-final'
New-Item -ItemType Directory -Force -Path $env:CODEX_LOCAL_TEST_TMP_ROOT | Out-Null
.\.venv\Scripts\python.exe -m pytest -p no:tmpdir -p no:cacheprovider -p h03_temp_fixture_plugin -q tests/test_bot_instance_lifecycle_service.py tests/test_telegram_bot_control_cli.py tests/test_telegram_runtime_dependencies.py tests/test_telegram_runtime_health_shutdown_contract.py tests/test_windows_local_handoff_readiness.py tests/test_planning_workspace_repository.py tests/test_saved_planning_plan_telegram_flow.py tests/test_product_workbench_acceptance.py tests/test_unit_price_advertising_cap_service.py tests/test_sales_mix_planning_service.py tests/test_period_profit_plan_fact_comparison.py tests/test_period_profit_sku_end_to_end_scope.py tests/test_period_profit_summary_service.py tests/test_planning_plan_readiness_service.py tests/test_planning_plan_comparison_service.py tests/test_analytics_export_service.py tests/test_analytics_export_serializer.py tests/test_telegram_document_contract.py tests/test_telegram_cost_table_transport.py tests/test_product_overview_service.py tests/test_product_overview_telegram_flow.py tests/test_telegram_unit_price_sensitivity_runtime_service.py tests/test_unit_price_sensitivity_service.py app/tests/test_period_profit_sku_scope_transport.py tests/test_unit_price_scenario_telegram_runtime.py tests/test_telegram_unit_price_batch_plan_runtime_service.py tests/test_telegram_external_expenses_flow.py tests/test_telegram_calculation_inflight_dedup.py app/tests/test_ozon_returns_diagnostic_request_attempt_count.py --tb=short
```

### O02 — пакет независимого review

Status: **R1–R10 FIXED; CODE-HEAD CI GREEN; INDEPENDENT SECOND REVIEW PENDING**. First review and findings: `PLANNING_WORKSPACE_ARCHITECTURE_REVIEW_2026-10-19.md`. Handoff: `PLANNING_WORKSPACE_REVIEW_HANDOFF_2026-10-19.md`. The review identified ten confirmed issues across the #705–#708 stack; all are addressed with targeted regression coverage. The connected H–O profile reports **259 passed**, documentation drift/manager tests **3 passed**, and `compileall -q app tests` plus `git diff --check` pass. Exact code head `d057031364e6d934f258fec2efa385a045f6e3bf` passed Verify `39221770481` and repeat `39221764654`: Windows/Linux tests, compile, and full-verification Docker build/runtime smoke are successful. This record is followed by a docs-only commit, which requires its own exact-head Verify. Independent second review remains required. Classification: **Architecture Review Required**. No merge/deploy.

### Review fix record — R1–R10

- **R1**: preserve period, quantities, and confirmed expenses on update only for the exact same SKU identity scope; reject silent scope changes.
- **R2**: add monotonic `state_revision` CAS to payload and metadata mutations, and bind stale callbacks to it.
- **R3–R5**: keep the source batch alive through its bound save action, preserve saved-editor context across allowed field navigation, and provide one READY/INCOMPLETE status contract.
- **R6**: make database schema initialization/migration atomic and singleton-versioned while preserving existing documents/revisions.
- **R7**: begin transient plan/fact generation before the external query so reset invalidates any late response.
- **R8**: retain document/revision binding for permitted successive edits; stale or cross-scope callbacks fail closed.
- **R9**: align service/persistence limits and reject aggregate overflow before calling float-based TaxService; unchanged legacy sales-mix records remain readable and preservable.
- **R10**: keep added, removed, and unchanged common SKU identities visible in the comparison screen and CSV/JSON export.
- Regression files: `tests/test_planning_workspace_repository.py`, `tests/test_saved_planning_plan_telegram_flow.py`, `tests/test_sales_mix_planning_service.py`, `tests/test_planning_plan_comparison_service.py`.
- Data check after isolated tests: tasks `8F7FFF206A4748DE6EFB3E5DCABABD07E3341188A7326383A21D966B73710698`; users `0B12986702D5C62B8A410EE4B3B3228923FF72BA897F18FF62FEF556CDA88409`. Local data and ACL scratch folders remain untouched/uncommitted.

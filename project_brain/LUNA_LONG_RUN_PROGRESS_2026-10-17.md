# Журнал выполнения Luna A–G — 17.10.2026

Журнал продолжения для `LUNA_LONG_RUN_PRODUCT_TASK_2026-10-17.md`. После каждого этапа сверять состояние с деревом, обновлять этот журнал и документацию, затем двигаться к следующему доступному этапу. Слияние и развёртывание не входят в поручение.

## A00 — снимок исходной точки

- Статус: **VERIFIED**.
- Начало: 17.10.2026.
- Исходная ветка подготовки: `codex/luna-long-run-product-task-20261017`; рабочая ветка: `codex/product-workbench-20261017`.
- Исходный HEAD: `91aac988aa067082434704095cc61a2400b06159`, родитель `3f7923ced48ba9434fdf5930d1f55431e0eacedd`.
- База `main`: `c55434327f50134324a5ca58e2f084854b809832`.
- PR #697 перепроверен через GitHub 17.10.2026: открыт, не слит, mergeable; head `3f7923ced48ba9434fdf5930d1f55431e0eacedd`, base `main` на `c55434327f50134324a5ca58e2f084854b809832`.
- Рабочее дерево до продуктовых изменений: пользовательские `data/tasks.json`, `data/users.json` изменены; сохранены без редактирования и staging. SHA256 на старте: tasks `8F7FFF206A4748DE6EFB3E5DCABABD07E3341188A7326383A21D966B73710698`; users `0E8D6AE4BF9E2842F5055502B5B94C0E9244F0A5F002B3ED76092E9A73488BE2`.
- Обнаружены существующие тестовые временные каталоги с ограничением Windows ACL и `data/tasks.json.lock`. Сохранить; не менять ACL и не удалять каталоги. Эти пути не входят в git diff по tracked файлам.
- Перед изменениями прочитаны `AGENTS.md`, `CURRENT_STATE.md`, `DECISIONS.md`, `TEST_MAP.md`, `ROADMAP.md`, полное ТЗ и аудит основания. Архитектура PR #697 и числовые примеры сверены ранее и повторно проверены как актуальные по SHA.
- Изменения A00: переименование текущей ветки; создание этого журнала; фиксация исполняемого поручения. Production code и тесты не менялись.
- Проверки: GitHub PR metadata — успешно; локальные SHA/base/head сверены; хэши user JSON записаны; ACL каталоги определены; полный pytest на A00 не нужен, код не менялся.
- Следующий шаг: A01 — пройти текущие call paths и подтвердить публичные точки расширения/budget/snapshot, затем записать только конкретные риски и совместимость.

## A01 — повторный review архитектурных точек расширения

- Статус: **VERIFIED**.
- Проверена production-реализация на базе PR #697 head `3f7923ced48ba9434fdf5930d1f55431e0eacedd`.
- `ProductBusinessDecisionQueryService.query_all()` загружает весь каталог, оборачивает вычисление в history/proposal/task lifecycle и прекращает весь результат на первой ошибке. Внешнего публичного read-only selected-row API нет. Для обзора нужен публичный projection contract; существующие callers оставить на старом пути.
- `_query_product()` валидирует и собирает decision по существующим метрикам/economics/input provider/decision service; сама запись истории находится отдельно в `_with_decision_history()`. Это позволяет добавить узкий public method, переиспользующий вычислительное ядро, но исключающий history/proposal/draft decoration.
- `UnitPriceScenarioSource._load_snapshot()` всегда активирует новый `PeriodProfitOperationTrace` с 60 секундами/64 запросами и затем сбрасывает ContextVar. Унаследованный лимит может быть потерян. `load_snapshot()` follower ждёт `Event` фиксированно 61 секунду. При новом grouped вызове эти два пути должны принимать явный parent operation context; одиночный публичный flow сохранить.
- Ozon clients уже резервируют physical attempts через текущий trace: обычный Ozon client — каждую retry attempt, Performance client — запрос. Существующий trace ограничивает один trace, но не умеет делить time/request cap parent/child. Новое расширение должно сохранить standalone поведение.
- `UnitPriceScenarioService.calculate()` — pure forward calculation, `UnitPriceTargetPlanningService.solve()` перепроверяет цену через forward result и ограничен 128 вычислениями. Новые builders делегируют им.
- `telegram_api_bot._send_result()` фиксирует caption всех файлов как инструкцию для CSV себестоимости; `SellerCostTableService.import_csv()` требует точные четыре заголовка. Ввести отдельный outgoing document kind, сохранив существующий caption и import schema.
- Существующий operation trace содержит сырые SKU/posting identity, события и stack dump; его нельзя отдавать пользователю как безопасный diagnostic без отдельной whitelist projection.
- Решения 036–045 и текущие finance/TaxService/Return COGS contracts повторно просмотрены по ТЗ. Новый A–G контур остаётся read-only и transient; новый архитектурный decision сейчас не требуется.
- Findings: всё выше — `VERIFIED_BEHAVIOR` и prerequisites, новых подтверждённых production defects не заявлено.
- Проверки: чтение actual code paths, factory/Telegram routes, trace/API reservation, cost import и test modules — пройдено; code не менялся, отдельный pytest не запускался.
- Следующий шаг: A02 — добавить parent-aware bounded operation trace и cooperative cancel с regressions, сохранив standalone defaults.

## A02 — общий budget, deadline и отмена

- Статус: **VERIFIED**.
- Изменён `PeriodProfitOperationTrace`: дочерний trace наследует минимальный deadline и общий attempt cap по полной цепочке parent-ов; reservation для всех уровней атомарна под общим lock. Локальный cap дочернего source дополнительно действует. Отмена child изолирована от sibling/parent, отмена parent распространяется на потомков.
- `UnitPriceScenarioSource.load_snapshot(..., operation_trace=...)` принимает только trace contract. Для новых групповых вызовов source создаёт дочерний trace; старые standalone вызовы сохраняют собственные 60 секунд/64 запроса. `Event.wait` ограничен source ceiling и оставшимся parent time; checks стоят до строки источника, перед циклом discount days и после возврата источника. Поздний результат после отмены возвращает controlled error и не попадает в source cache.
- Ozon `base_ozon_client` получает активный дочерний trace через существующий ContextVar и продолжает резервировать каждую физическую retry attempt. Перенос родительского trace восстанавливается `finally`; endpoint/API структуры не менялись.
- Добавлены регрессии parent deadline, общего cap, конкурентной гонки двух child traces, локальной/root cancellation, физического запроса через `OzonClient`, in-flight wait clamp, explicit parent trace propagation/restoration и запрета кэшировать результат после отмены.
- Проверка: **21 passed, 1 deselected** (`test_long_running_trace_writes_secret_free_worker_snapshot`, существующий тест зависит от `tmp_path`; Windows ACL блокирует чтение/cleanup basetemp). `compileall` изменённых app/test файлов — успешно; `git diff --check` — успешно. Полный pytest ещё не запускался; он обязателен на A04 и CI.
- Первые две попытки pytest для baseline не использовали `PYTHONPATH=app`; они остановились при collection и не считаются кодовым дефектом. Повтор с корректным import path показал отдельную WinError 5 на pytest temp tree. Успешный focused запуск отключил только tmpdir fixture и выбрал все остальные тесты этого набора. Не меняли ACL и не удаляли temp data.
- Изменения A02: `app/services/period_profit_operation_diagnostics.py`, `app/services/unit_price_scenario_source.py`, соответствующие два test modules. CHANGELOG/CURRENT_STATE/TEST_MAP/ROADMAP обновлены. Никаких data/** файлов не изменяли намеренно.
- A02 code commit: `f42274a` (`Bound grouped Ozon reads under parent operation budget`). Он содержит production trace/source изменения и regressions; пользовательские файлы данных не включены.
- Следующий шаг: A03 — scoped in-memory snapshots для новых обзорного и batch consumers.

## A03 — scoped снимки новых экранов

- Статус: **VERIFIED**.
- Добавлен `ScopedTransientSnapshotStore`, предназначенный только для новых обзорного и batch consumers. Снимки привязаны к активному tenant, владельцу, магазину и виду отчёта; новый generation инвалидирует предыдущий и не позволяет позднему worker опубликовать старые строки.
- Снимок содержит случайный ID, generation/version, времена создания/истечения, source freshness, coverage и валидированные строки со стабильным `row_id`. Данные JSON-safe, не более 256 строк и 1 MiB; хранение ограничено 64 snapshot и 64 generation, TTL 600 секунд. Чтение делает изолированную копию под lock; обращения обновляют LRU, но не срок жизни.
- Добавлены regressions для отсутствующего/чужого tenant, точного owner/store, старого generation, fixed TTL, copy isolation, stable row identity, payload shape/size, 64-entry eviction и конкурентного чтения во время eviction.
- Совместный A02/A03 профиль: **34 passed, 1 deselected**. Исключён только существующий `test_long_running_trace_writes_secret_free_worker_snapshot`, использующий заблокированный ACL `tmp_path`; его обязан включить чистый CI. Compileall изменённого A03 кода/тестов и `git diff --check` — успешно.
- A03 не переносит старые кэши и не добавляет persistent storage. Следующие модули B и C обязаны использовать этот helper; иначе A03 не считается востребованным двумя consumers.
- A04 теперь VERIFIED по exact-head CI; следующий шаг: B00 — начать обзор выбранных товаров.

## A04 — фиксация основания

- Статус: **VERIFIED**.
- Полный Windows pytest стартовал на чистом изолированном storage и свежем basetemp: собрал **3 288** тестов. В ходе старых `tempfile` тестов системная temp-папка не дала SQLite открыть файл; cleanup завершился `PermissionError (WinError 5)`, поэтому pytest не выдал итоговую сводку. Повтор одного такого теста с отдельным temp внутри workspace воспроизвёл запрет создания/открытия и очистки временной базы. ACL не менялись; user JSON SHA до/после совпадает с A00.
- Новые A02/A03 проверки прошли: **34 passed, 1 deselected**. A03 test-модуль отдельно проходит все 13 тестов. Compileall и `git diff --check` успешны. Полный локальный результат не принят; полная приёмка выполнена exact-head GitHub CI ниже.
- Exact-head GitHub CI по PR #698, code SHA `be76a4f8e4c7d78160e0d1047515651993062d54`, Verify run `39059951770`: **windows-verification** и **full-verification** — success. Обе jobs скомпилировали приложение и выполнили полный pytest; full verification также успешно собрала production Docker image и прошла runtime smoke. SHA-bound test report опубликован как artifact `12111345571`. Это clean CI приемка основания A несмотря на локальную Windows ACL.
- A foundation оформлена commit `f42274a` (A02) и `be76a4f` (A03), push на branch `codex/product-workbench-20261017`, draft PR #698 stacked поверх PR #697. B00 начат после точного зеленого CI.
- Следующий шаг: продолжить B01.

## B00 — публичный read-only row query

- Статус: **VERIFIED**.
- Добавлен `query_selected_products(selectors)` в decision query service. Он требует активный tenant, принимает до 20 точных строковых selector, дедуплицирует их, загружает каталог один раз, отклоняет неоднозначные offer/catalog SKU, продолжает обработку остальных строк при частичной ошибке и возвращает coverage со статусами каждой строки.
- Новый путь напрямую использует существующую pure decision calculation; он не использует decorated cache и не вызывает history record, action proposal или task-draft reconciliation. Старый `query()`/`query_all()` lifecycle сохранён.
- Источники получили совместимые методы `sales_for_product`, `stock_for_product`, `query_for_product`, чтобы использовать уже разрешённую строку каталога вместо повторной загрузки каталога на каждый товар. Unit-economics cache стал owner/store tenant-scoped. Trace предоставляет безопасную проверку, можно ли начинать следующую строку.
- Regressions: 53 passed, 1 deselected (только ACL-bound tmp_path test); compileall и diff-check прошли. Набор включает selection 0/21, точный tenant, duplicate selector, ambiguous identity, missing product, один catalog load, no lifecycle writes, partial source failure, parent budget exhaustion и cache tenant isolation.
- Следующий шаг: B01 — pure row projection, stable row ID, source provenance/freshness, счётчики полного scope и страницы без источниковых вызовов.

## B01 — подготовка группы и coverage

- Статус: **VERIFIED**.
- Добавлен `ProductOverviewService`: ограниченный запрос до 20 селекторов преобразуется в короткие строки для нового экрана и публикуется в A03 transient snapshot store, привязанном к активному owner/store. Factory создаёт один общий store и overview service; будущий пакетный план должен подключить тот же экземпляр.
- Каждая строка содержит stable opaque `row_id`, проверенную identity, только whitelist decision priority/reasons, показатели с единицами, `missing_data`, статус/error и provenance источников. В evidence протаскиваются даты периода продаж, наблюдения и записи источника. Raw внутренний payload не переносится.
- Coverage считается по уникальным отображаемым строкам; READY, INCOMPLETE, SOURCE_UNAVAILABLE, NOT_FOUND, IDENTITY_AMBIGUOUS, BUDGET_EXHAUSTED и CANCELLED взаимоисключающие. Повторная identity схлопывается и отражается отдельным счётчиком. Некорректная identity не остаётся READY.
- Snapshot чтение выдаёт ограниченные страницы только из памяти; переход страницы не вызывает decision query/Ozon. Snapshot API повторно проверяет owner/store/generation/version; чужой scope получает stale, истёкший/старый токен не переоткрывает строку.
- Для свежести сохраняются observed/recorded timestamps, период и возраст на момент создания. Источник не объявляется stale по придуманному business порогу: `freshness_policy` явно говорит, что порог не настроен.
- Проверка B01: **69 passed** в шести связанных наборах (overview, input provider, selected query, snapshot store, business decision query, factory-backed seller attention); `compileall` изменённых app/tests и `git diff --check` успешны. Использованы `-p no:tmpdir -p no:cacheprovider`, исключён только ранее ACL-заблокированный worker `tmp_path` regression; новые B01 проверки все прошли.
- Следующий шаг: B02 — фильтры существующих сигналов, sort по текущему приоритету/метрикам и страницы без источниковых вызовов; stale filter реализовать только по подтверждённым source age metadata.

## B02 — snapshot filters и sorting

- Статус: **VERIFIED**.
- `ProductOverviewService.get_page` теперь фильтрует и сортирует уже прочитанный snapshot: все выбранные, существующий приоритет, подтверждённая отрицательная прибыль, существующее решение LOW_MARGIN, положительный остаток без продаж по `NO_SALES`, неполные/устаревшие данные. Правила расчёта решений не дублируются.
- Низкая маржа определяется только существующим reason `LOW_MARGIN`/решением `WATCH_LOW_MARGIN`; отрицательная прибыль требует одновременно `NEGATIVE_UNIT_PROFIT` и отрицательного числового показателя. Запасы без продаж требуют `stock_priority=NO_SALES`, скорости 0 и остатка >0.
- Порог возраста не придуман. `ProductBusinessDecisionQueryService` передаёт проверенную метаинформацию unit-economics cache, а обзор маркирует stale только при явном `cache.status=stale`. Невалидная/неполная freshness остаётся в отдельном фильтре без превращения неизвестного в ноль.
- Priority sort сохраняет стабильный порядок identity; числовая сортировка выводит unknown после числовых значений и стабилизирует ties по identity. Ответ показывает размер scope и отфильтрованной группы, параметры сортировки и номер страницы.
- Проверка B02 вместе с B01/B00/provider/cache/factory regressions: **75 passed**; `compileall` и `git diff --check` успешны. Pagination/filter/sort не повторяют query; тесты сверяют вызов источников ровно один раз.
- B03 завершён: Telegram entry/card navigation, stale callbacks, price-plan basket и подтверждение замены активного price scenario. Проверка B03 — 88 passed; следующий шаг B04 — расширить edge/factory acceptance.

## Матрица этапов

Статусы: `NOT_STARTED`, `IN_PROGRESS`, `IMPLEMENTED`, `VERIFIED`, `BLOCKED`. `IMPLEMENTED` означает код есть, `VERIFIED` — проверки этапа успешны.

| Этап | Статус | Ветка/base/head | Результат и проверки | Документы | Следующий шаг / блокер |
|---|---|---|---|---|---|
| A00 | VERIFIED | `codex/product-workbench-20261017` / PR #697 head / `91aac98` | PR открыт; refs и data SHA сохранены | этот журнал; CURRENT_STATE; ROADMAP | A01 |
| A01 | VERIFIED | `codex/product-workbench-20261017` / production base `3f7923c` | подтверждены public-path, budget, snapshot и file boundaries | этот журнал; audit | A02 |
| A02 | VERIFIED | `codex/product-workbench-20261017` / base `91aac98` / `f42274a` | parent/child deadline, shared atomic cap, cancel and source wait; 21 passed, 1 ACL-bound deselected | code + two test modules; CHANGELOG; CURRENT_STATE; TEST_MAP; ROADMAP | A03 |
| A03 | VERIFIED | `codex/product-workbench-20261017` / base `f42274a` | scoped store; **34 passed, 1 ACL-bound deselected** with A02; compileall/diff-check passed | helper + tests; this journal; CHANGELOG; CURRENT_STATE; TEST_MAP; ROADMAP | A04 |
| A04 | VERIFIED | PR #698 exact head `be76a4f8e4c7d78160e0d1047515651993062d54` | Verify `39059951770`: Windows/full verification, full pytest, compileall, Docker build/runtime smoke — success | CI artifact `12111345571`; this journal | B00 |
| B00 | VERIFIED | `codex/product-workbench-20261017` / stacked on #698 | public bounded selected-row query; **53 passed, 1 ACL-bound deselected** | code + regression; CHANGELOG; CURRENT_STATE; TEST_MAP; ROADMAP; this journal | B01 |
| B01 | VERIFIED | `codex/product-workbench-20261017` / stacked on #698 | bounded snapshot builder/pages; **69 passed**, compileall/diff-check passed | code + tests; CHANGELOG; CURRENT_STATE; TEST_MAP; ROADMAP; this journal | B02 |
| B02 | VERIFIED | `codex/product-workbench-20261017` / stacked on #698 | snapshot-only filters/sorts, exact source freshness; **75 passed**, compileall/diff-check passed | code + tests; CHANGELOG; CURRENT_STATE; TEST_MAP; ROADMAP; this journal | B03 |
| B03 | VERIFIED | `codex/product-workbench-20261017` / stacked on #698 | Main-menu entry, group navigation, snapshot-only controls, row/completeness screens, basket for up to 10 exact catalog identities, and version-bound confirmation before replacing an active price scenario; **88 passed**, compileall passed | selected query, overview, Telegram handler/keyboard, price runtime, factory; regressions; CHANGELOG; CURRENT_STATE; TEST_MAP; ROADMAP; this journal | B04 boundary + public factory acceptance |
| B04 | VERIFIED | `codex/product-workbench-20261017` / stacked on #698 | Boundary/public-route acceptance: 0/1/20/21, partial/failure rows, budget exhaustion, concurrent generations, owner/store tokens, 10-item basket, message/callback bounds, factory/menu; **93 target passed**; related product suite **1,018 passed, 12 ACL-bound `tmp_path` tests deselected**; `compileall app`, diff-check passed | this journal; CHANGELOG; CURRENT_STATE; TEST_MAP; ROADMAP; tests | B00–B04 locally verified. Clean exact-head CI must run all tests. Next C00 |
| C00 | VERIFIED | `codex/product-workbench-20261017` / PR #698 stack / `127914d` base | Batch contract 2–10 exact unique catalog identities, stable row IDs, source/as-of/provenance per row, explicit statuses, read-only; covered by batch service regressions | `unit_price_batch_plan_service.py`; tests; CHANGELOG; CURRENT_STATE; TEST_MAP; ROADMAP; this journal | C01 |
| C01 | VERIFIED | `codex/product-workbench-20261017` / PR #698 stack / working tree | One catalog snapshot; exact identity; shared parent deadline/128 HTTP attempts; cached age retention; partial failure isolation and unsupported FBS explicit | batch plan + source implementation/tests; docs | C02 |
| C02 | VERIFIED | `codex/product-workbench-20261017` / PR #698 stack / working tree | Row and target edits, explicit bulk advertising preview/cancel/confirm, refresh retains manual values/provenance; 0-valued inputs remain known; no source calls for local operations | batch service + Telegram runtime/tests; docs | C03 |
| C03 | VERIFIED | `codex/product-workbench-20261017` / PR #698 stack / working tree | Per-row current/break-even/target results, solver target candidate forward-proof, original order/local sorts, bounded 3,500 UTF-16 output and 64-byte callbacks | batch service/runtime/tests; docs | C04 |
| C04 | VERIFIED | `codex/product-workbench-20261017` / PR #698 stack / working tree | Public handoff revalidates batch version, owner/store, exact identity, source freshness, FBO and target; recalculates candidate without HTTP; no Ozon write; stale callbacks and cancelled ad confirmation fail closed | single/batch runtimes, factory, handler, tests; docs | C05 acceptance |
| C05 | VERIFIED | `codex/product-workbench-module-c` / PR #699 stacked on #698 / code SHA `07b9d595df32b11b736aaa2dc13c822df7f52ec4`; acceptance docs head `292c4cb83d4499045ae200862c2b3132905e409e` | Focused profile **116 passed**; wider B/C product profile **193 passed**; `compileall -q app tests`, `git diff --check` passed. Exact-head Verify runs `39063730904` and `39063717597` passed Windows/full-verification; docs-only acceptance head also passed runs `39064061444` and `39064066060`. PR #699 open, no merge/deploy. | code/tests; CHANGELOG; CURRENT_STATE; TEST_MAP; task matrix; this journal | D00 |
| D00 | VERIFIED | `codex/product-workbench-module-d` stacked on C acceptance head `292c4cb` | Pure sensitivity sweep builder, bounded parsing/axes, exact scenario calculations, target markers, staleness and immutable inputs. **117 focused tests passed** across D and related single/batch calculation profiles; compileall and diff-check passed. | sensitivity service/tests; TEST_MAP; docs | D01 |
| D01 | VERIFIED | `codex/product-workbench-module-d` / working tree | Telegram sensitivity flow from single calculator and eligible batch rows; paged results for up to 49 cells; strict text/callback ownership and stale-scope checks; no Ozon network calls. Covered by the **117 passed** focused profile. | sensitivity runtime, keyboard, handler, factory, batch/single adapters; tests; docs | D02 |
| D02 | VERIFIED | `codex/product-workbench-module-d` / working tree | Explicit candidate transfer rechecks exact store/catalog identity, source version/freshness and scenario lifecycle, then recalculates forward through the existing calculator; no automatic apply or writes. Covered by the **117 passed** focused profile. | single/batch runtimes; sensitivity runtime tests; docs | D03 |
| D03 | VERIFIED | `codex/product-workbench-module-d` / PR #700 stacked on PR #699 / head `d7c33dfa9d4d1e3ffde626d375dd17d2f0d38824` | Local acceptance: **117 passed**, `compileall -q app tests` and `git diff --check` passed. Full local Windows pytest: **2,978 passed, 21 failed, 369 errors**, blocked by `WinError 5` temp-directory ACL and SQLite temp-file access. Exact-head Windows and full-verification CI passed in runs `39065039552` and `39065028764`. Project-data JSON SHA256 values unchanged. PR open; no merge/deploy. | D code/tests/docs; PR #700; CI runs | E00 |
| E00 | VERIFIED | `codex/product-workbench-module-e` / stacked on PR #700 | Added explicit document-kind/MIME/filename contract; sender reports success only after Telegram document send and does not retry failures. Existing seller-cost CSV and caption preserved. **12 passed**, compileall/diff-check pass. | Telegram document contract/sender; seller-cost export; transport tests; docs | E01 |
| E01 | VERIFIED | `codex/product-workbench-module-e` / working branch | Pure schema-v1 CSV/JSON serializers; CSV formula protection for text fields, numeric negatives remain numbers, JSON money strings use dot, null≠0, typed schema/units/semantic metadata, no NaN/Infinity, 2 MiB no-truncation gate. **17 passed**; compileall/diff-check pass. | serializer service/tests; document contract; docs | E02 |
| E02 | VERIFIED | `codex/product-workbench-module-e` / stacked on PR #700 | Period CSV/JSON comes from finalized report snapshot, includes B/E bridge, rounding/reconciliation and saved TOP_K/coverage; no source rerun. Covered in combined **73 passed** profile. | export service/tests; CHANGELOG; CURRENT_STATE; TEST_MAP; ROADMAP; this journal | E03 |
| E03 | VERIFIED | `codex/product-workbench-module-e` / working branch | Separate export buttons for overview, batch, sensitivity. All selected/filtered snapshot rows/cells included; current page does not truncate; filter/sort metadata retained; planning scope/provenance/FBO disclaimers present. | runtime, keyboards, handler, factory, tests; docs | E04 |
| E04 | VERIFIED | PR #701 `codex/product-workbench-module-e` / base #700 / accepted code SHA `47cfa2527b2f963d2604511c76d1a41b6e6201f0`; docs head `f598d300164916434de27a5180bb033d8a9f4293` | Public period/product callback → export → Telegram document path covered; legacy cost import/export and failed send preserved. Focused profile **73 passed**. Final exact-head Verify `39066587245`: Windows/Linux **3 389 passed** and Docker smoke; documentation head Verify `39066774774` also green. PR remains open; no merge/deploy. | code/tests; CHANGELOG; CURRENT_STATE; TEST_MAP; ROADMAP; guide; this journal | F00 |
| F00 | VERIFIED | `codex/product-workbench-module-f` / base PR #701 docs head `f598d30` / commit `057d439` | Bounded 256-event ring, durable counters across trimming, parent-child HTTP/row aggregation and sanitized operation summary; cached completeness-linked diagnostic view with source/reason codes and actionable buttons; reading screen does no Ozon call or write. Profile **27 passed, 1 deselected** (only existing `tmp_path` stack-dump fixture blocked by local Windows ACL with tmpdir disabled); compileall and diff-check passed. Exact acceptance remains pending module F CI. | trace, finance posting probes, completeness/runtime/keyboard/handler; diagnostic view service; regressions; guide, CHANGELOG, CURRENT_STATE, TEST_MAP, ROADMAP, task and journal | F01 allowlisted support JSON |
| F01 | VERIFIED | `codex/product-workbench-module-f` / stacked on #701 docs head / commit `59432ef` | Strict support-diagnostic JSON schema, stable within-file masked SKU aliases, exact cached owner/store/report route; no source rerun, no money or private API/request identifiers. Combined F00/F01 profile **34 passed, 1 deselected** (the existing ACL-bound `tmp_path` stack-dump test); compileall and diff-check passed. Exact acceptance awaits F PR CI. | exporter, runtime cache accessor, handler/keyboard, adversarial tests, user guide, CHANGELOG, TEST_MAP, ROADMAP, CURRENT_STATE, task and journal | F02 process metadata |
| F02 | VERIFIED | `codex/product-workbench-module-f` / stacked on #701 docs head / commit `3e4af5a0` | Read-only main-menu version view; validated revision and UTC process start are captured once, included in cached support JSON, and never resolved from disk per request. Windows start script captures Git revision and a fresh start timestamp once per launch; Docker/Verify pass the build SHA. Profile **58 passed, 1 deselected** (existing ACL-bound `tmp_path` stack-dump test); compileall and diff-check passed. | metadata service, handler/keyboard/factory wiring, Docker/Verify/startup config, regression and integration tests, user guide and project docs | F03 adversarial diagnostics acceptance |
| F03 | VERIFIED | `codex/product-workbench-module-f` / commit `fba94596` | F00–F03 profile **77 passed, 1 deselected**. New fake-transport cases cover 429/timeout counters and secret-free public trace, expired export with zero new source calls, and support JSON send failure. Existing coverage includes cancellation, partial source coverage, alias masking, invalid revision, process-start snapshot, foreign owner/store and no-query cached view/export. Compileall/diff-check passed. Exact-head CI remains pending G01. | diagnostic regressions, changelog, test map, current state, roadmap, task and journal | G00 cross-feature flows |
| G00 | VERIFIED locally | `codex/product-workbench-module-g` / dependency stack A–F | Public-handler acceptance connects overview → incomplete filter → exact item selection → batch target → local cost edit → sensitivity → batch/sensitivity CSV/JSON; period comparison → CSV/JSON → safe support JSON; legacy main-menu destinations remain discoverable. **54 passed, 1 existing `tmp_path` factory test deselected** due local ACL with pytest tmpdir disabled. | `tests/test_product_workbench_acceptance.py`; period/overview regressions; CHANGELOG; CURRENT_STATE; TEST_MAP; ROADMAP; user guide; task matrix; this journal | G01 |
| G01 | VERIFIED | G code acceptance head `12447d4cb48823fea938513fbb16dc4f41a080c2`, branch `codex/product-workbench-module-g` | Local full Windows pytest: **3 018 passed, 22 failed, 369 errors** за 78,73 с. 21/22 failures are under five test modules using inaccessible temp directories/SQLite; one stale menu assertion fixed in F. Exact-head Verify `39069249065` completed successfully: Windows suite and full-verification/Docker build-runtime smoke. Exact F head `55db3e60fda3c3080051da2fbea1902091a4bfff` passed Verify `39069168434` on Windows and full-verification/Docker. | G00 acceptance, allowlist and data review, Verify artifacts; this journal | G02 final review packet and current-head recheck |
| G02 | VERIFIED | `codex/product-workbench-module-g` / PR #702 → #703 | Dependency-ordered handoff and architecture checklist in `LONG_RUN_REVIEW_HANDOFF_2026-10-17.md`. G code acceptance head `12447d4cb48823fea938513fbb16dc4f41a080c2` passed Verify `39069249065`; handoff head `1a6664429533e092b239a6240e0b1173358f0cfa` passed Verify `39069517726` (Windows/full-verification and Docker). Independent reviewer approval remains pending. | handoff, PR descriptions, this journal | reviewer checks latest PR head before merge |

## Архитектурные выводы

- A02 реализует trace hierarchy без нового job framework: один root owns deadline/request reservation; child сохраняет меньший локальный cap и локальный counter. Отмена cooperative и scope-safe.
- Новые bounded snapshots (A03) будут самостоятельным helper только для overview/batch consumers с одинаковыми owner/store/generation/TTL invariants.
- Для B отдельный read-only projection method должен повторно использовать decision core и не проходить через history/proposal/draft side effects.

## Коммиты и PR

| Артефакт | Статус |
|---|---|
| PR #697 | Открыт, не слит; внешний dependency и base новых веток |
| PR #701 (E) | Открыт: https://github.com/dopf129-pixel/ai-business-assistant/pull/701; code SHA `47cfa2527b2f963d2604511c76d1a41b6e6201f0`, Verify `39066587245` green: Windows/Linux 3 389 passed, Docker smoke; docs SHA `f598d300164916434de27a5180bb033d8a9f4293`, Verify `39066774774` green; не слит/не развёрнут |
| PR #702 (F) | Открыт: https://github.com/dopf129-pixel/ai-business-assistant/pull/702; base #701 / `f598d300164916434de27a5180bb033d8a9f4293`; head `55db3e60fda3c3080051da2fbea1902091a4bfff`; Verify `39069168434` green; не слит/не развёрнут |
| PR #703 (G) | Открыт: https://github.com/dopf129-pixel/ai-business-assistant/pull/703; base #702 / `55db3e60fda3c3080051da2fbea1902091a4bfff`; acceptance head `12447d4cb48823fea938513fbb16dc4f41a080c2` Verify `39069249065` green; handoff head `1a6664429533e092b239a6240e0b1173358f0cfa` Verify `39069517726` green; не слит/не развёрнут |

# 2026-10-17 — модуль F02, версия работающего процесса

- Коммит F01 `59432ef` закрепил allowlisted JSON-экспорт диагностики. F02 завершён commit `3e4af5a0`: новая кнопка главного меню показывает валидированный revision и UTC-время старта именно запущенного процесса; при отсутствии SHA используется безопасная отметка локальной сборки.
- Метаданные считываются единожды при инициализации фабрики и добавляются к cached support JSON. Пересмотр файлов или HEAD во время работы не обновляет экран уже запущенного процесса. `start_bot.ps1` заново снимает Git SHA и время для каждого запуска; Docker/Verify передают build SHA как build arg. Рестарт/завершение процесса не добавлялись.
- Связанный профиль F00–F02: **58 passed, 1 deselected**; исключён только известный `tmp_path` stack-dump тест при отключённом pytest tmpdir из-за локальной Windows ACL. `compileall -q app tests` и `git diff --check` прошли. В export integration проверено, что метаданные версии попадают в JSON, а источник читается ровно один раз.
- Следующий шаг: F03 — проверка полного набора adversarial/error/scope/send-failure сценариев диагностики, затем G00.

# 2026-10-17 — модуль F03, приёмка диагностики

- Commit `fba94596` добавил три acceptance направления: настоящий `OzonClient` поверх fake HTTP transport для 429/timeout (ровно 1 зарезервированная попытка; публичная трасса не содержит endpoint, Client ID, API key, token или exception detail); support export после TTL возвращает expired без повтора запроса; сбой отправки именно `support_diagnostic` заканчивается явной ошибкой без ложного успеха.
- В проверяемом профиле также оставлены существующие регрессии cancellation, partial coverage, точных ring-buffer totals, повторного alias для одинакового SKU, invalid revision, immutable старого process metadata, foreign user/store, read-only flags и source-call count=1 для диагностики/экспорта.
- F00–F03 итоговый локальный профиль: **77 passed, 1 deselected**; deselected — только существующий ACL-bound `tmp_path` stack dump при отключённом pytest tmpdir. `compileall -q app tests` и `git diff --check` успешны. Exact-head CI пройдёт в G01.
- F03 закрыт локально. Следующий шаг — G00, сквозные сценарии продукта через публичные runtime/Telegram пути.

# 2026-10-17 — модуль G00, сквозная приёмка

- Добавлен `tests/test_product_workbench_acceptance.py`: через публичный `AssistantButtonHandlerService` проходят обзор → фильтр «Пробелы данных» → точное добавление двух товаров → пакетная цель → исправление отсутствующей себестоимости как локального допущения → анализ чувствительности → JSON пакетного плана и CSV/JSON чувствительности. Используются настоящие `ProductOverviewService`, `UnitPriceBatchPlanService`, `UnitPriceScenarioService`, target solver, Telegram batch/sensitivity runtimes и export serializers с fake источниками.
- Счётчики подтверждают неизменность источников после загрузки: один query обзора, один catalog read и ровно по одному snapshot на выбранный SKU. Экспортированные документы помечены read-only, `executed=False`; локальная себестоимость зафиксирована в ручной provenance строке плана.
- Периодная сквозная проверка соединяет finalized comparison, CSV/JSON и support diagnostic JSON; один и тот же query остаётся ровно один. Main-menu regression проверяет доступность прежних разделов рядом с новым обзором.
- Локальный G00 профиль по семи связанным test modules: **54 passed, 1 deselected**. Единственный deselected — ранее известный factory test с `tmp_path`; он исключён при `-p no:tmpdir` из-за ACL Windows temp root. Все новые G00 acceptance cases прошли. Compileall и `git diff --check` — успешно.
- `data/tasks.json`, `data/users.json` и существующие ACL-limited temp/lock пути не добавлялись к тестовым изменениям и не менялись намеренно.
- G00 закрыт локально. Следующий шаг: G01 — сверить allowlist текущего diff и данные, выполнить полный pytest и compileall, подготовить точный финальный SHA, push branches и получить зелёный Windows/Linux full CI и Docker smoke.

# 2026-10-18 — модуль G01, полный локальный прогон и PR F

- Полный локальный Windows pytest завершился результатом **3 018 passed, 22 failed, 369 errors**. Из 22 падений 21 относятся к ранее недоступному system `%TEMP%`: пять затронутых групп используют `TemporaryDirectory`, SQLite отвечает `unable to open database file`, а cleanup завершается `WinError 5`. Оставшаяся ошибка была устаревшей проверкой списка главного меню после добавления F02 кнопки версии; исправлена только assertion, коммит `55db3e60`.
- После исправления целевой regression-профиль нового G00 и меню: **21 passed, 1 deselected**; deselected — только прежний factory test, требующий ACL-bound `tmp_path`. `compileall -q app tests` и `git diff --check` прошли.
- F branch опубликована и оформлена как PR #702, stacked на PR #701. Точный head `55db3e60fda3c3080051da2fbea1902091a4bfff`; Verify run `39069168434` queued на момент записи. PR #702 открыт и не слит.
- Для разделения review создана ветка G поверх F head. `data/tasks.json`, `data/users.json`, ACL-bound temp и lock файлы остаются вне индекса.
- Следующее: закоммитить только G allowlist, открыть PR #703 stacked на #702, получить exact-head Windows/Linux/Docker CI для обоих PR, затем выполнить G02 review handoff без merge/deploy.

# 2026-10-18 — модуль G02, пакет независимого review

- PR #702 (F) и PR #703 (G) созданы отдельными stacked branches; #702 exact-head Verify `39069168434` зелёный, #703 acceptance head Verify `39069249065` зелёный. Также перепроверены зависимые heads #698–#701: Verify runs `39062235998`, `39064066060`, `39065255165`, `39066774774` имеют conclusion `success`.
- Подготовлен `LONG_RUN_REVIEW_HANDOFF_2026-10-17.md`: таблица PR/base/head/CI и порядок зависимости, checklist по budgets/cancellation, tenant+identity, snapshot/TTL, финансовой семантике, приватности/экспортам, совместимости и данным.
- G00 acceptance head содержит только проверки и документацию поверх F; производственная логика на этапе G не менялась. Новая проверка проходит публичный Telegram handler и реальными builders/runtimes с fake source; source counts подтверждают отсутствие повторного запроса при локальной правке/просмотре/экспорте.
- Полный локальный Windows suite затруднён локальным доступом к временным каталогам: **3 018 passed, 22 failed, 369 errors**. CI успешен для Windows/full-verification и Linux/Docker. Единственная ошибка тестового контракта главного меню исправлена коммитом F `55db3e60`.
- Для G02 создан documentation-only review-handoff commit. Его точный head `1a6664429533e092b239a6240e0b1173358f0cfa` прошёл Verify `39069517726`, оба job зелёные. Независимый архитектурный review ожидает reviewer; этот handoff — не approval. Merge и deploy не выполнялись.

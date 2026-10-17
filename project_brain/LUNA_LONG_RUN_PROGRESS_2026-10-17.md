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
| C05 | VERIFIED | `codex/product-workbench-module-c` / PR #699 stacked on #698 / code SHA `07b9d595df32b11b736aaa2dc13c822df7f52ec4` | Focused profile **116 passed**; wider B/C product profile **193 passed**; `compileall -q app tests`, `git diff --check` passed. Exact-head Verify runs `39063730904` and `39063717597`: Windows + full-verification success, including full pytest and production Docker smoke. PR #699 open, no merge/deploy. | code/tests; CHANGELOG; CURRENT_STATE; TEST_MAP; task matrix; this journal | D00 |
| D00 | IN_PROGRESS | `codex/product-workbench-module-d` stacked on C SHA `07b9d595` | Pure sensitivity calculator and 18 regressions present as untracked files; focused suite **18 passed**, compileall/diff-check passed. Next: inspect/finalize service boundary, add Telegram workflow and candidate handoff. | D service/tests, then runtime/handler/factory and docs | D01/D02 |
| D01 | NOT_STARTED | — | — | — | зависит от D00 |
| D02 | NOT_STARTED | — | — | — | зависит от D01 |
| D03 | NOT_STARTED | — | — | — | приёмка чувствительности |
| E00 | NOT_STARTED | — | — | — | зависит от A04 |
| E01 | NOT_STARTED | — | — | — | зависит от E00 |
| E02 | NOT_STARTED | — | — | — | зависит от E01 |
| E03 | NOT_STARTED | — | — | — | зависит от B04/C05/D03 |
| E04 | NOT_STARTED | — | — | — | приёмка выгрузок |
| F00 | NOT_STARTED | — | — | — | зависит от A02/E00 |
| F01 | NOT_STARTED | — | — | — | зависит от F00 |
| F02 | NOT_STARTED | — | — | — | зависит от F01 |
| F03 | NOT_STARTED | — | — | — | приёмка диагностики |
| G00 | NOT_STARTED | — | — | — | зависит от B04/C05/D03/E04/F03 |
| G01 | NOT_STARTED | — | — | — | полный pytest/CI/Docker |
| G02 | NOT_STARTED | — | — | — | review handoff и итог |

## Архитектурные выводы

- A02 реализует trace hierarchy без нового job framework: один root owns deadline/request reservation; child сохраняет меньший локальный cap и локальный counter. Отмена cooperative и scope-safe.
- Новые bounded snapshots (A03) будут самостоятельным helper только для overview/batch consumers с одинаковыми owner/store/generation/TTL invariants.
- Для B отдельный read-only projection method должен повторно использовать decision core и не проходить через history/proposal/draft side effects.

## Коммиты и PR

| Артефакт | Статус |
|---|---|
| PR #697 | Открыт, не слит; внешний dependency и base новых веток |
| PR модулей A–G | Ещё нет |

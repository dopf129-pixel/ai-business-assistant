# План проверок большого пакета A–G (17.10.2026; IN_PROGRESS)

## Исправления архитектурного review R1–R8 (2026-10-18)

- `tests/test_telegram_unit_price_sensitivity_runtime_service.py`: production adapter single→sensitivity callback, owner reset, 64-entry LRU/TTL и cleanup action tokens.
- `tests/test_telegram_unit_price_batch_plan_runtime_service.py`: поздний refresh после cancel/edit, parent trace propagation, stale projection parity для экрана/экспорта и сброс при `/start`/переключении магазина.
- `tests/test_product_overview_service.py`: child time/request budget и инвалидирование in-flight snapshot при owner reset.
- `tests/test_unit_price_batch_plan_service.py`: удаление устаревших missing/invalid labels после пересчёта.
- Связанный профиль вместе с acceptance, architecture regression, Telegram integrity и export tests: **86 passed**. `compileall -q app tests` и `git diff --check` прошли.
- Полный локальный Windows pytest: **3 030 passed, 21 failed, 369 errors**; трассировки указывают на `PermissionError [WinError 5]` при создании/чтении/очистке pytest temp paths. Повтор с отдельным `--basetemp` дошёл до конца тестов, но teardown тоже заблокирован ACL. Для code SHA `664a370a117251a88297e57668a8ba721a80555c` exact-head Windows и full-verification CI прошли: runs `39161924581`, `39161920417`.

## Фактическое выполнение

- F00: tests/test_period_profit_operation_diagnostics.py проверяет 256-entry ring buffer, сохраняемые total/dropped counters, родительско-дочернюю агрегацию попыток и row outcomes без публикации raw identifiers. tests/test_period_profit_diagnostic_view_service.py покрывает whitelist статусов/причин, bounded counters, budget actions и fail-closed поля. tests/test_period_profit_completeness_view.py проверяет точный cached-view маршрут, tenant isolation и отсутствие повторного query.
- F00 локальный профиль: 27 passed, 1 deselected; исключён единственный existing tmp_path stack-dump тест, поскольку изолированный запуск отключил pytest tmpdir из-за известной ACL. Compileall и diff-check пройдены; полный F acceptance ожидает CI.
- F01: `tests/test_period_profit_support_diagnostic_export_service.py` проверяет strict JSON allowlist, secret-looking hostile nested fields, отсутствие сумм/raw IDs, стабильные aliases, invalid periods/revisions и default-deny неизвестных полей. `tests/test_period_profit_completeness_view.py` проходит реальный handler → cached owner/store snapshot → `support_diagnostic` document contract; source query выполняется ровно один раз, чужие user/store callbacks истекают.
- F00/F01 local profile: **34 passed, 1 deselected**; единственное исключение — существующий ACL-bound `tmp_path` stack dump. `compileall -q app tests` и `git diff --check` успешны; полный acceptance ждёт exact-head CI PR F.
- F02: `tests/test_app_build_metadata_service.py` verifies allowlisted environment reads, validation, UTC normalization, captured-once semantics and secret non-disclosure. `tests/test_telegram_help_discovery.py` checks the public version button/handler; container, Verify workflow and Windows startup contracts assert revision injection and launch metadata. `tests/test_period_profit_completeness_view.py` checks that the cached support JSON includes process metadata without another source query.
- Combined F00–F02 profile: **58 passed, 1 deselected**; the single deselection is the existing ACL-bound `tmp_path` stack-dump test. `compileall -q app tests` and `git diff --check` passed. Full exact-head acceptance remains in G01.
- F03 extends `tests/test_period_profit_operation_diagnostics.py` with fake Ozon HTTP 429 and timeout responses; public summaries retain exact reservation totals while excluding URL, Client ID, API key, token and exception details. `tests/test_period_profit_completeness_view.py` verifies an expired support export does not call its source again; `tests/test_telegram_cost_table_transport.py` verifies failed delivery of the support-diagnostic document reports failure and never claims success.
- Combined F00–F03 local profile: **77 passed, 1 deselected**; only the existing ACL-bound `tmp_path` stack-dump test is deselected. Compileall and diff check passed; clean exact-head CI remains required.

- Исполняемое ТЗ: `LUNA_LONG_RUN_PRODUCT_TASK_2026-10-17.md`; stage journal: `LUNA_LONG_RUN_PROGRESS_2026-10-17.md`.
- A00–A01: снимок исходной точки и architecture review; код не менялся, pytest не запускался.
- A02: `tests/test_period_profit_operation_diagnostics.py` проверяет parent/child deadline и общий concurrent attempt cap, child/root cancellation и лимит через реальный `OzonClient` request wrapper. `tests/test_unit_price_scenario_source.py` проверяет parent trace propagation/context restoration и clamp in-flight wait.
- Локальный A02 subset: **21 passed, 1 deselected**; исключён существующий stack-dump `tmp_path` regression из-за недоступного Windows temp ACL. Чистый CI должен включить его.
- A03: `tests/test_scoped_transient_snapshot_store.py` покрывает точную tenant/owner/store изоляцию, version/generation, атомарные копии при LRU eviction, TTL без продления на read, стабильные row IDs и границы размера. Совместный профиль A02/A03: **34 passed, 1 deselected**; тот же ACL-bound `tmp_path` regression. Compileall и `git diff --check` успешны.
- B00: `tests/test_product_business_decision_selected_query.py` покрывает public selected cohort: один load каталога, dedupe, ambiguous/not-found, tenant/cap, failure isolation, общий trace budget и отсутствие history/proposal/task-draft writes. Вместе с существующими decision, metrics-source, unit-economics-cache и trace regressions: **53 passed, 1 deselected** (тот же ACL-bound test). Compileall и diff-check прошли.
- B01: `tests/test_product_overview_service.py` покрывает whitelist projections, units, source periods/age, stable row IDs, duplicate identity, reconciled coverage, budget/cancel visibility, page reads без повторного query, tenant isolation, out-of-range pages и invalid identity fail-closed. Связанный набор вместе с provider, selected-query, scoped-store, decision-query и factory wiring: **69 passed**; compileall/diff-check прошли.
- B02: тот же overview regression suite проверяет все шесть фильтров существующих сигналов, explicit stale cache propagation, tie-break по identity, unknown numeric values в конце, page counts и отсутствие повторных source calls: совокупно **75 passed**; compileall/diff-check прошли.
- B03: `tests/test_product_overview_telegram_flow.py` проверяет main-menu entry, карточку и callback ≤64 bytes, stale row callback после refresh, явную замену и version-bound confirmation активного price scenario. `tests/test_product_overview_service.py` проверяет short view tokens, cross-store/generation rejection, next-group refresh и tenant-scoped deduplicated plan basket. Selected-query test проверяет одну загрузку каталога, стабильную сортировку группы и отсутствие lifecycle writes. Связанный набор: **88 passed**; compileall прошёл.
- B04: границы 0/1/20/21 и budget проверены в `tests/test_product_business_decision_selected_query.py`; concurrent latest-generation publication, cross-owner/store token rejection, cap/dedupe для 10 SKU проверены в `tests/test_product_overview_service.py`; production factory/handler, filter/page source-free reads, Telegram UTF-16 message и 64-byte callbacks — в overview/attention tests. Итог B: **93 профильных passed**; расширенный товарный набор **1 018 passed, 12 ACL-bound `tmp_path` tests deselected**. `compileall -q app` и `git diff --check` успешны. CI обязан включить все 12.

- ТЗ `LUNA_LONG_RUN_PRODUCT_TASK_2026-10-17.md` задаёт meaningful regressions: общий parent/child HTTP budget; read-only cohort без history/proposal writes; selected-group partial coverage; точные идентификаторы; stale/cross-store/concurrent callbacks; batch targets; sensitivity cells; CSV/JSON и formula injection; обезличивание diagnostics; public handler/factory/file sender.
- После каждого этапа — целевые проверки, после модуля — полный pytest и CI актуального SHA Windows/Linux/Docker. Результаты записываются в `LUNA_LONG_RUN_PROGRESS_2026-10-17.md` и итоговый review handoff.
- E00–E04: `tests/test_telegram_document_contract.py`, `tests/test_analytics_export_serializer.py`, `tests/test_analytics_export_service.py`, `tests/test_analytics_export_runtime.py`, `tests/test_telegram_cost_table_transport.py`, `tests/test_period_profit_analytics_runtime.py`, `tests/test_product_overview_telegram_flow.py`, `tests/test_telegram_unit_price_batch_plan_runtime_service.py`, `tests/test_telegram_unit_price_sensitivity_runtime_service.py`. Проверяются документные контракты, formula-safe CSV/JSON, snapshot-only exports, stale/foreign scopes и доставка через public Telegram handler.
- E exact-head PR #701 SHA `47cfa2527b2f963d2604511c76d1a41b6e6201f0`: Windows/Linux full suites **3 389 passed** на каждой платформе; Docker build/runtime smoke passed, Verify run `39066587245`.
- При подготовке выполнены 6 прямых fake-only вызовов настоящих `UnitPriceScenarioService`/`TaxService`; все контрольные числовые примеры ТЗ совпали.
- A02 добавлены parent deadline/request cap, одновременное резервирование, cancellation и HTTP wrapper/source regressions. A04 закрыт точным CI PR #698, приведённым выше.
- A04 exact-head CI PR #698 / SHA `be76a4f8e4c7d78160e0d1047515651993062d54`: Verify run `39059951770` прошёл на Windows и full-verification; полный pytest, compileall, production Docker build/runtime smoke успешны. SHA-bound artifact: `12111345571`.

# N06 — Telegram-экраны и scoped report snapshots (15.10.2026)

- `tests/test_period_profit_analytics_runtime.py` проверяет public handler route, прежний и текущий период, прибыль до внешних расходов, п.п. маржи, bridge, SKU residual, существующий выбор товара, owner/store isolation, fixed TTL, отсутствие tenant fallback, компактный snapshot и очистку длинной SKU-метки. В тесте присутствует production-factory wiring regression.
- N06 code commits `e9372b1` and `9a6523c`. Последний N06+N07 focused набор: **76 passed, 1 deselected**; deselected только production-factory regression, потому что локальный Windows runner не позволяет Python зайти в изолированный временный каталог (WinError 5). Отдельно `compileall -q app tests` и `git diff --check` прошли. Production-factory regression included and passed in the final N08 full CI.
- N07 `test_cached_read_and_eviction_are_atomic_and_cache_stays_bounded` делает interleaving через `Event`: cached entry копируется под lock, параллельный расчёт заполняет LRU, читатель получает READY, а после 65 отчётов старый callback expired и новый остаётся доступным; cache не превышает 64.
- N07 аналитический/query suite: **76 passed, 1 deselected** (production-factory test ждёт clean CI). Отдельно budget/dedup/Performance suite: **13 passed, 68 deselected**, включая Ozon/Performance retries в общем лимите и конкурентные callbacks с owner/store isolation. `compileall -q app tests` и `git diff --check` прошли.
- N08: локальный full-suite diagnostic на старом SHA `bbdebf4`: **2,876 passed, 22 failed, 369 errors**; обычный pytest также встретил basetemp `WinError 5`; этот локальный результат не использован как приёмка. Exact PR SHA `c36efb6...` выявил одну устаревшую подпись в legacy assertion; исправленный связанный модуль прошёл локально (**10 passed**). Final exact code SHA `05bac9b5be203970f0d40b930fe8cc1b6036415d`: Windows **3,268 passed**, Linux **3,268 passed**, compileall и production Docker build/runtime smoke — success (Verify runs `38755542971` and `38755551644`).

# N00–N05 — аналитика прибыли, contract, bridge и SKU contribution (15.10.2026)

- `tests/test_period_profit_sku_contribution.py` covers reference store-vs-SKU reconciliation (+4,100 ₽ = +3,000 ₽ matched SKU +1,100 ₽ residual), exact historical SKU change under the same confirmed product+offer, no-zero inference for a missing counterpart, conflicts, ambiguous offer variants, deterministic top five, incomplete coverage, malformed money, and mismatch with the canonical store contract.
- `tests/test_period_profit_finalized_comparison_contract.py::test_production_wrapper_exposes_sku_contribution_from_finalized_rows` verifies the production final wrapper exposes the contribution from the same finalized summaries and does not run an extra SKU query.
- N05 with contract/bridge/metrics and existing finance/legacy-SKU identity regressions: **67 passed in 1.32s**; `compileall -q app tests` and `git diff --check` passed. The store result remains authoritative; unmatched rows are not converted to zero.

- N04 commit `710ea8994881fc10a4a09a3f6ef11d7c7426f2c0`: `tests/test_period_profit_comparison_bridge.py` verifies reference ΔN/ΔC/ΔK/ΔT sums, nested revenue/net-accrual split, complete and partial E, one-cent rounding, >1-cent mismatch, per-period formula mismatch despite equal delta, applied K/tax, unsupported scope and unknown K. `tests/test_period_profit_finalized_comparison_contract.py` ensures production wrapper exposes the bridge and refuses its inconsistent fake canonical result.
- N04 focused suite with N01–N03 integration: **100 passed in 2.54s**; compileall and diff check passed. Bridge failure is controlled and does not rewrite the financial report.

- N03 commit `a02a42c29e11bbef93f824579dd9a15fbe5e796c`: `tests/test_period_profit_comparison_metrics.py` covers numeric deltas/revenue shares, zero/negative bases, percentage-point margin changes, independent metrics under tax-policy mismatch, different period lengths, partial external estimates, exact >2^53 unit counts, overflow and malformed contracts. The production-wrapper integration verifies metrics derive from the same finalized comparison contract.
- N03 related N01–N03 query/contract/presentation suite: **89 passed in 2.30s**; `compileall -q app tests` and `git diff --check` passed. `comparison_metrics` is analysis-only and does not rewrite canonical summaries.

- N02 commit `07c6c99eaea471f5b002e18b5554034af8d5180e`: `tests/test_period_profit_comparison_contract.py` проверяет периоды/исходные request, tenant, tax policy, profit scope, strict final Return COGS marker, independent metrics при несовместимости и B/E complete/partial/unknown coverage. `tests/test_period_profit_finalized_comparison_contract.py` проверяет production wrapper с fake источниками: обе финализации, внешние расходы после финализации, complete E и отказ previous external evidence без потери B. `tests/test_period_profit_request.py` покрывает равные периоды через год/високосный день и controlled underflow.
- N02 связанный набор из 14 модулей: **80 passed in 2.11s**. `compileall -q app tests` и `git diff --check` прошли. Попытка запустить существующий expense repository/evidence набор `tests/test_external_operating_expense_coverage_v1261_v1270.py` отдельно показала 7 tmp_path setup errors; pytest завершился дополнительным `PermissionError (WinError 5)` при перечислении basetemp и не дал summary. Pure/integration regressions N02 проходят; этот модуль должен быть перепроверен в N08 CI.
- Контракт N02 намеренно копирует finalized amounts, а не пересчитывает прибыль/налог. Сравнение B требует совместимости canonical scope, tax policy, component flags, периода и tenant; E дополнительно требует complete evidence/adjustment обоих периодов.

- N00 baseline перед кодом N01: `tests/test_period_profit_comparison.py`, `tests/test_period_profit_query_service.py`, `app/tests/test_period_profit_runtime_comparison_fallback.py` — **9 passed in 0.48s** на task SHA `12619f947fd00d5fce056836000abb36ecb5300f`.
- N01 code `66d79d6a87c6f3509e187f2a2e5b2441e270086f`: production final-wrapper/runtime tests verify previous return-loader and final-application failures preserve one finalized current result, while current errors remain fail-closed with one query. Base-only query regression covers optional previous-summary failure.
- Pure comparison tests reject absent/bool/string/NaN/infinite/overflow monetary values and non-boolean scope flags; finite Decimal, zero and negative profit remain valid. Compact-report test distinguishes displayed E from B↔B comparison text.
- **128 passed in 2.14s** across comparison, query, final wrapper, runtime, Return COGS, compact response and related mappings. `compileall -q app` passed. Full suite deferred to N08. No Ozon calls or persistent data writes.
- Fake-only probes подготовки подтверждали повтор current при отказе прошлых возвратов, принятие `None`/`bool`/`NaN` builder-ом и неподписанное сравнение B рядом с E. Это audit evidence, не успешные исправляющие тесты.
- Матрица N00–N08 и exact-head CI: `LUNA_STORE_ANALYTICS_DEVELOPMENT_TASK_2026-10-15.md`, разделы 16–19.
- PR #696 уже слит в main `c554343`; результаты ниже относятся к его историческим проверкам и не принимают будущий код аналитики.

# PR #696 — нормализация цены до сетки копеек

- `tests/test_unit_price_target_planning_service.py`: числовые строки/Decimal `11.110` нормализуются к 1 111 копейкам; `1.0000` принимается как 100 копеек, а `11.111` отклоняется. Два эквивалентных исходных формата обязаны дать одну цену при подборе цели.
- `tests/test_unit_price_scenario_telegram_runtime.py`: реальный runtime принимает `11.110` в редакторе и выдаёт ту же подтверждённую цену `11.08 ₽`, что и `11.11`; source читается один раз.
- Четыре связанных planner/runtime/architecture/repeat-review модуля — **87 passed in 1.19s**; `compileall -q app tests` и `git diff --check` прошли. Verify runs `38728949431` и `38728942708` на code SHA `4b7839caf54650e672b4410ee21bc1b64c627eff` успешны: Windows/Linux — по **3 204 passed**, compileall и Docker build/runtime health-check прошли. Локальный full pytest не сформировал сводку из-за `PermissionError (WinError 5)` при cleanup basetemp и не считается приёмкой.

# Карта тестов — актуальный статус 2026-10-15

## PR #696 — повторное исправление поиска целевой цены (проверки продолжаются)

- `tests/test_unit_price_target_planning_service.py`: если максимум проходит цель, solver всё равно проверяет меньшие точки и предпочитает минимальную среди ограниченных подтверждённых проб. Регрессия с ценой 500 ₽, комиссией 50% и целью 50% требует результат 0,02 ₽.
- `tests/test_unit_price_scenario_telegram_runtime.py`: тот же сценарий проходит через выбор SKU и ввод цели; результат остаётся точным, доступен только после прямой проверки и использует один source read.
- Четыре связанных planner/runtime/architecture/repeat-review модуля — **80 passed in 1.15s**; `compileall -q app tests` прошёл. Code SHA `007bd5a01a53d8451f8fe291810c76c55467b5c6` прошёл Verify runs `38726919355`/`38726911253`: полный suite **3 197 passed** на Windows и Linux, production Docker build/runtime smoke успешен. Локальный full pytest дал **2 808 passed, 21 failed, 368 errors** и traceback с `PermissionError (WinError 5)` на общем Windows pytest temp root; локальный результат не используется как приёмка.

## PR #696 — повторная правка R1/R2 (проверки продолжаются)

- `tests/test_unit_price_target_planning_service.py` покрывает цель 49,99% при неизвестной исходной цене и достижимой цене внутри диапазона, а также запятую/пробелы в исходной цене.
- `tests/test_unit_price_scenario_telegram_runtime.py` проходит публичный сценарий выбора SKU → ввод целевой маржи без исходной цены → проверенная цена.
- Четыре связанных модуля: **78 passed in 1.19s**. `compileall -q app tests` и `git diff --check` прошли.
- Полный pytest Windows в локальной среде: **2 806 passed, 21 failed, 368 errors**; pytest завершился `WinError 5` во время работы с временными каталогами. Локальный full suite не используется как приёмка.
- Verify run **38722009779** на SHA `ac43cb70069ac1e4586b13c7b8e70c9db04e2944`: Windows/Python 3.12 — **3 195 passed in 43.58s**, Linux/Python 3.11 — **3 195 passed in 11.59s**, compileall и production Docker build/runtime smoke успешны.

## PR #696 — первое исправление review R1/R2 (историческая запись)

- `tests/test_unit_price_target_planning_service.py` добавляет: достижимая 50% маржа и безубыточность находятся при неуспешной максимальной копейке; provenance рассчитанной и введённой цены отделяется от источника исходной цены. Максимальный счётчик в проверке — ≤113 при hard cap 128.
- Helper + Telegram runtime + architecture/repeat-review regressions: **75 passed in 1.12s**; `compileall` изменённых Python files и `git diff --check` прошли.
- Полный локальный `pytest -q` не дал достоверного итога: были ошибки и сбои, затем pytest завершился `WinError 5` при перечислении временного каталога. PR Verify run **38716365784** на точном SHA `475f2dbccc069c58a8ac859c9334705472718e0c` прошёл: Windows **3 192 passed in 20.16s**, Linux **3 192 passed in 11.08s**, compileall и production Docker build/runtime smoke успешны.

## M00 baseline целевой маржи

- Основа: актуальный merged main `de21561a8b440570ac34bcfd9b3dc48abee1ffac`, ветка `codex/price-planning-target-margin-20261015`.
- Пять существующих модулей `test_unit_price_scenario_service.py`, `test_unit_price_scenario_source.py`, `test_unit_price_scenario_telegram_runtime.py`, `test_unit_price_scenario_repeat_review_regressions.py`, `test_unit_price_scenario_architecture_review_regressions.py`: **57 passed in 1.20s**. Только warning — локальный ACL блокирует `.pytest_cache`; assertions passed.
- Восемь синтетических контрольных цен повторены через реальный `UnitPriceScenarioService` + `TaxService`. На 414,70 ₽ и 414,71 ₽ UI показывает 30,00%, но Decimal acceptance target 30% false; на 414,72 ₽ true. Это audit baseline, не тест solver.
- M01 добавит standalone helper/parser tests; текущий кодовый baseline не заменяет обязательный новый CI Windows/Linux/Docker.

## M01 target search и список цен

- Новый `tests/test_unit_price_target_planning_service.py` покрывает target parser, price list 2–5 с comma/dot/пробелами тысяч/CRLF, atomic rejection duplicates/invalid tokens, точный предел цели, контрольные цены, отдельный результат безубыточности, три налоговых режима действующего `TaxService`, not-found/missing distinctions, сравнение одинаковых допущений, округлённые верхние границы и счётчик максимум 113 (конфигурационный cap 128).
- Unit-price service/source/runtime + architecture/repeat-review regressions и новый helper module: **81 passed in 1.37s**. `compileall -q app/services/unit_price_target_planning_service.py` passed; кэш pytest отключён, тесты использовали пустой `AI_ASSISTANT_STORAGE_ROOT`.
- M02 добавил к этому набору target/list/retry/cancel/missing-input/price-preservation/production-factory/UTF-16 проверки в `tests/test_unit_price_scenario_telegram_runtime.py`. С `test_unit_price_scenario_architecture_review_regressions.py`, `test_unit_price_scenario_repeat_review_regressions.py` и helper module: **63 passed in 1.06s**.
- В Telegram tests подтверждены отсутствие дополнительного source/API call при поиске и таблице, сохранение цены основного сценария, удержание ранее введённой цели для отметок сравнения, исправление невалидного списка целиком и пределы сообщения/callback. Сквозная регрессия вызывает публичный `AssistantButtonHandlerService` от выбора карточки до явного применения цены. Четыре целевых модуля — **72 passed in 1.13s**.
- PR Verify run **38713193546** завершился success: `compileall` и полный `pytest` — **3 189 passed** на Windows/Python 3.12 и Linux/Python 3.11; Linux production Docker build/runtime smoke — success. PR head при проверке: `46e91cffe66beac1c5f8289ba5cac7984975fd6c`.
- Локальный изолированный Windows full-suite не смог выдать итог: pytest не получил доступ перечислить свой временный каталог (`WinError 5`). Успешный CI прошёл на чистых GitHub runners; пользовательские `data/*.json` не переносились в тестовую копию.

## M03 выбор цены и lifecycle

- `tests/test_unit_price_scenario_telegram_runtime.py` проверяет выбор target и конкретной строки, повторный прямой расчёт, неизменность Ozon/business state, отсутствие произвольной цены в callback, старые кнопки после редактирования/refresh/new SKU/store change/source TTL/session expiry и controlled late apply после возврата к редактору.
- Helper, Telegram runtime, architecture/repeat-review regressions и новые application cases: **71 passed in 1.11s**. Используются injected fake clock/events, настоящий `UnitPriceScenarioService`/`TaxService`, реальная клавиатура, не live API. `compileall` изменённых Python files и `git diff --check` прошли.
- M04 прошёл public-handler regression, `compileall`, Windows/Linux полный suite и Linux Docker smoke на PR. Открытый следующий контроль — независимый Architecture Review PR #696; merge/deploy не выполнялись.

## Планирование цены — baseline и новое ТЗ M00–M04

- PR #695 уже слит в main `de21561a8b440570ac34bcfd9b3dc48abee1ffac`; merged-main Verify `38707150836` success. PR integration Verify `38704768075` проверял 3 150 tests на Windows и 3 150 на Linux, compile и Docker build/runtime smoke.
- Подготовлено `LUNA_PRICE_PLANNING_TASK_2026-10-15.md`: будущие проверки target/rounding, сравнений, bounded search, отсутствия HTTP/writes и tenant/version/lifecycle guards перечислены в разделе 10. Новые тесты и функционал пока не добавлены.
- Синтетические контрольные цены 242,38/242,39; 335,25; 414,70/414,71/414,72; 500/600 сверены прямыми вызовами текущих `UnitPriceScenarioService`/`TaxService`. 414,70 и 414,71 показывают 30,00%, но точная цель 30% не достигнута. Это audit арифметических примеров ТЗ, не приёмка будущего solver.
- Для документационной подготовки pytest повторно не запускался: production code не менялся. Проверки новой реализации обязательны в M00–M04 на её собственном SHA.

## PR #695 — R11 исправление неизвестного SKU в auto-b

- `tests/test_unit_price_scenario_source.py`: отсутствие поля SKU, `None`, пустая и пробельная строка помечаются malformed/incomplete; известный другой SKU исключается как раньше даже без bonus.
- `tests/test_unit_price_scenario_repeat_review_regressions.py`: сквозная проверка raw Ozon accrual → настоящий `FinanceService` → source/math/runtime/public handler; unknown identity запрещает автоматический процент и прибыль, ручной fallback восстанавливает результат.
- Целевые шесть модулей (source, repeat-review, service, Telegram runtime, architecture regressions, finance accrual breakdown): **63 passed in 1.32s** (Python 3.12, `PYTHONPATH=app`). `compileall -q app tests` и `git diff --check` прошли.
- Полный CI на code SHA `27dbb2f65166ac63b07fac250eea87a2d9dca939` прошёл: Verify runs **38704396583** и **38704389615** завершились success для Linux full verification, Windows full verification и production Docker build/runtime smoke. GitHub PR review threads пусты.

## R11 — исходное подтверждение до исправления (историческая запись)

- На head `9185f65` пять модулей дали **51 passed in 1.53s**; три изолированных probes для отсутствующей identity подтвердили дефект.

## PR #695 — review 15.10.2026: R11, неразрешённая identity в auto-b

- Пять существующих модулей `test_unit_price_scenario_service.py`, `test_unit_price_scenario_source.py`, `test_unit_price_scenario_telegram_runtime.py`, `test_unit_price_scenario_architecture_review_regressions.py`, `test_unit_price_scenario_repeat_review_regressions.py`: **51 passed in 1.53s** на head `9185f65`.
- Три изолированных expected-red проверки настоящих FinanceService evidence → UnitPriceScenarioSource для SKU None/пустого/пробельного значения: **3 failed in 0.28s**. Подтверждают автоматические 20%/complete=true при пропущенной строке с неразрешённой identity; правильное поведение — unknown/incomplete и ручной fallback. Probe вне репозитория, fake-only, не входит в стандартный suite и не изменяет business data.
- Reviewed-head Verify runs `38635120280`/`38635112065` Windows/Linux/Docker success — существующий baseline, не приёмка R11. После исправления нужны штатные parser/source/runtime regressions, новый full pytest и CI. ТЗ: `LUNA_PR695_DISCOUNT_IDENTITY_FIX_TASK_2026-10-15.md`.

## PR #695 — повторный review R10: source/presentation граница

- `tests/test_unit_price_scenario_repeat_review_regressions.py` добавляет source → math → runtime → public `AssistantButtonHandlerService` regressions для сохранённой себестоимости `1e100` и seller price `1e100`. Они проверяют unknown provenance/incomplete source, отсутствие прибыли и `cost_as_of` для unsupported cost, рабочую keyboard, ручное исправление, прибыль 280 ₽, неизменность fake persisted cost, а также безопасные result/edit formatters.
- Red evidence до исправления: оба интеграционных сценария завершались `UNIT_PRICE_SCENARIO_CALLBACK_FAILED` без keyboard. После исправления calculator/source/math/runtime/architecture/UI/request-bound-tax-policy selection: **59 passed in 1.51s**. Изолированный Windows pytest без seller data/.env: **3 144 passed in 16.17s**; двум production-policy tests задана синтетическая конфигурация USN_INCOME 6%/minimum 1%. `compileall -q app tests` завершился с одной прежней SyntaxWarning в returns-impact test. GitHub Verify exact head `2207ec86` — runs **38634572358**, **38634565693**, обе Windows/Linux/Docker проверки successful.

## PR #695 — regressions повторного review R8/R9

- `tests/test_unit_price_scenario_repeat_review_regressions.py` использует реальные source, math и Telegram runtime с fake facts и injected monotonic clock. Проверяет weighted rate 50/300 с расчётом налога 25 ₽/прибыли 280 ₽/маржи 56%; источник кэшируется один раз; сценарий, открытый при age=590, ровно на TTL=600 и при t=610 становится STALE, отключает price comparison и показывает предупреждение в assumptions. Успешное обновление получает цену 550, начинает свежий TTL и сохраняет ручное advertising=0.
- `tests/test_unit_price_scenario_service.py` проверяет, что 28-digit bounded recurring rate допустим, а превышение precision guard недопустимо; existing tests сохраняют checks extreme money, не finite, bounds, explicit zero и tax errors.
- Новый calculator/source/math/runtime/regression set: **48 passed**. Полный изолированный Windows pytest — **3 141 passed in 24.54s**; `compileall -q app tests` прошёл с одной прежней `SyntaxWarning` в `tests/test_unit_economics_returns_impact_integrity_v971_v980.py:177`. Verify run **38621277605** на code SHA `9ed3e2d9bee334b54b874f63493f69dc4197d15f` — success: Windows/Linux full verification, Docker build/runtime smoke. Повторная проверка R8/R9 не выявила блокеров.

## PR #695 — regressions архитектурного review R1–R7

- Добавлен `tests/test_unit_price_scenario_architecture_review_regressions.py`: store/generation-scoped picker, atomic picker-consume/source-ticket interleave, controlled late source loads и refresh, eviction/pending isolation, READY text ownership, реальные Seller Cost/Return Inventory adapters, store switch/disconnect clearing и independent source freshness на result и assumptions screens. Interleavings используют `Event`, не timing sleeps.
- `tests/test_unit_price_scenario_service.py`: крайние Decimal magnitude/precision отклоняются, невалидный tax output делает итог недоступным, локализованная цена остаётся допустимой.
- Обновлены `tests/test_unit_price_scenario_telegram_runtime.py` на opaque calculator picker callback.
- Целевой calculator/runtime/UI/routing набор: **62 passed**. Полный `pytest -q`: **3 138 passed** на изолированной копии текущего кода; пользовательские данные исключены. Compileall прошёл. GitHub Verify run **38616115735** success на code SHA `3f4942b6c2e01238cabfd9fda7c274ab479bcba7`: Windows full suite, Linux full suite, Docker build и smoke.

## Архитектурный review PR #695 — непокрытые регрессии

- Review SHA `6d472145fe4586a5fe2a4da0e7b0b796900b8fac`: три existing modules `tests/test_unit_price_scenario_service.py`, `tests/test_unit_price_scenario_source.py`, `tests/test_unit_price_scenario_telegram_runtime.py` — **26 passed in 1.38s**.
- GitHub Verify run `38604649833` success на этом SHA подтверждает existing full-suite/Windows/Linux/Docker baseline (3 119 тестов), а не закрытие новых находок.
- Восемь дополнительных изолированных probes подтверждают R1–R7: stale store catalog callback; late initial load после clear и после более нового выбора; eviction inactive record при pending active record; unhandled text READY; finite input `1e100`; early-return seller-cost navigation; snapshot age >TTL при продлении session activity. Ни Ozon calls, ни business writes не выполнялись. R2 — concurrent runtime contract; текущая polling application имеет max concurrent updates=1.
- Probes не включались в pytest как тесты неправильного поведения. Требуемые red→green regressions, integration boundaries и порядок приёмки описаны в `LUNA_PR695_ARCHITECTURE_FIX_TASK_2026-10-14.md`; evidence — `ARCHITECTURE_REVIEW_PR695_2026-10-14.md`.
- Full pytest повторно не запускался: production code не менялся, exact-SHA CI уже прочитан. Новые регрессии и current-head full CI обязательны при исправлениях.

## Историческая приёмка PR #694

- Финальная проверка перед merge выявила и закрыла пропущенные whole-history text refresh (single/CSV confirm/cancel) и локальный auth timeout Performance / budget reason после 401. Новые регрессии: `app/tests/test_seller_cost_confirmation_flow.py::test_text_during_whole_history_confirmation_keeps_valid_draft_buttons`, `tests/test_ozon_performance_historical_reports.py::test_performance_auth_timeout_uses_remaining_local_and_shared_budgets` и `::test_performance_auth_refresh_preserves_exhausted_shared_budget_reason`.
- После дополнительного patch: cost-flow suite — **16 passed**; Performance/SKU-advertising suite — **99 passed / 3 deselected**. Полный CI code SHA `f7a0f945bc26cadd5d190982a68c2dae6191d632` включает эти три локально исключённых файловых теста: Linux Python 3.11 и Windows Python 3.12 по **3 093 passed**, compileall и production Docker build/smoke прошли. Финальный review одобрил слияние.

## Историческая проверка R1–R5 на fb1b0db

- Исправления R1–R5 для PR #694 проверены целевым набором регрессий: **74 passed**; прямой повтор ключевых сценариев: **13 passed**. На code SHA `d3cfddeda006cdb164393ba7a8ae182a24a3c1ea` GitHub CI прошёл: Linux **3 090 passed**, Windows **3 090 passed**, production Docker build/smoke прошли; `compileall` изменённых production модулей прошёл.
- В регрессии вошли stale cost preview (товар/сумма/CSV/history/cancel), store A → store B для обычного/SKU/pre-COGS/experimental custom period, текстовое описание внешнего расхода с retry после слишком длинного ввода, Performance auth/JSON/401/429/download с общим request/time budget, и контролируемый interleaving read/eviction decision LRU.
- Повторный Architecture Review этого SHA закрыл R1–R5 без оставшихся замечаний. Исходный review и проверенный follow-up: `ARCHITECTURE_REVIEW_PR694_2026-10-14.md`. PR #694 не сливался.

## Исторический снимок 2026-10-13 до remote CI и Architecture Review

- Текущий полный isolated pytest после P07/P08: **3,077 passed in 12.06s**, exit code 0; `compileall app tests` также прошёл. Копия исключала `.git`, `.venv`, секретный `.env`, базы и пользовательские runtime data.
- P07/P08 combined regression: **173 passed**. P07 coverage screen tests проверяют report snapshot scope/cache, user/store isolation, повторное открытие без Ozon re-query и переходы к существующим Return COGS/cost flows. P08 tests проверяют порядок/лимит пяти, факты и timestamps, stale/unknown exclusion, separate missing-data list, stock-without-sales, отсутствие ложного DRR/ROAS, callbacks, production-factory wiring, tenant cache isolation, LRU bound, freshness expiry и Telegram message size cap.
- Main menu compatibility после добавления новой кнопки: `tests/test_product_unit_economics_telegram_ui.py` вместе с P08 cache/summary regressions — **80 passed**.
- Python 3.11 grammar compatibility: `ast.parse(..., feature_version=(3,11))` по 874 файлам `app` и `tests` — 0 syntax errors. Машинный Linux Python 3.11 Verify не запускался: на Windows-host нет Python 3.11, установленного WSL-дистрибутива или Docker; grammar check не считается runtime verification.
- P01 Windows regression повторно выполнен на Python 3.12: **171 passed** для всех `tests/test_task_persistence_*.py`, atomic user-storage tests и `tests/test_telegram_runtime_health_shutdown_contract.py`. Это дополняет, но не заменяет Linux job и архитектурное ревью.
- `tests/test_product_business_decision_query_service.py`: дополнены tenant-isolation и bounded LRU проверки; `tests/test_product_decision_metrics_source_tenant_cache.py` проверяет одинаковый SKU в двух магазинах без пересечения подготовленного sales/stock cache.
- P03 полный suite теперь подтверждён общим успешным isolated pytest (**3,077 passed**); прежний sandbox `WinError 5` остаётся только историей неуспешного раннего запуска.
- P05 итог: после добавления tenant/store-bound callback для ручных периодов/отчётных экранов final P05 regression set — **79 passed**; полный `pytest` после P05 — **3,027 passed in 18.29s**.
- P06 `tests/test_telegram_external_expenses_flow.py`: quick/custom period, list/gaps, preview-before-write, explicit zero confirmation, no implicit coverage, amount/date validation, write failures, idempotent/concurrent confirmation, stale view and store isolation. Вместе с expense evidence, period-profit/factory/onboarding/SKU и compact-report regressions: **70 passed** в изолированной копии.
- P06 `tests/test_external_operating_expense_coverage_v1261_v1270.py`: дополнительно проверены пересекающиеся интервалы покрытия без дублирования expense суммы и subtraction observed expenses ровно один раз при partial coverage.
- P07 result audit: `PeriodProfitQueryService`/final application result carries account summary, SKU/quantity, tax metadata, external-expense evidence, period-bound return evidence and Return COGS evidence. `PeriodProfitReturnCogsBlockerStageService` remains the canonical first-blocker resolver. The delivered bounded tenant/store/user scoped snapshot returns both report and completeness view without network re-query or a second readiness gate. No seller-facing consumer exists for accounting recognition/authorization/commit, so the UI states the limit rather than inventing actions.

- P05 optional Performance budget and non-blocking SKU report: `tests/test_ozon_performance_historical_reports.py`, `tests/test_ozon_performance_client.py`, `tests/test_period_profit_sku_telegram_flow.py`, `tests/test_period_profit_sku_advertising.py`. Verifies a fake-clock deadline, 120-call cap, HTTP timeout propagation, preservation of verified finance when CPC lookup/mapping fails, safe compact diagnostics, and omission of period delta when only one side has confirmed CPC. Combined P05 targeted run, including callback dedup: **126 passed**. Full isolated pytest: **3,027 passed in 12.20s**.
- P05 in-flight callback guard: `tests/test_telegram_calculation_inflight_dedup.py` — **6 passed**. Checks same-request suppression, isolation by user/store/period, excludes custom period setup, and cleanup after success/failure. Full pytest at the first slice: 3,022 passed; the current full result is listed above.
- P04 user-triggered returns and Analytics API diagnostics: `tests/test_experimental_store_economics.py` covers cached-period/user isolation, anonymized totals/shape, missing metrics not becoming zero, bounded one-page Analytics response and the existing FBO/FBS returns diagnostics. `tests/test_ozon_analytics_data_client.py` checks compatible request defaults and observer forwarding; `app/tests/test_ozon_returns_diagnostic_request_attempt_count.py` verifies actual HTTP attempts including a 429 retry for both endpoints. Targeted P04 run across the listed reconciliation files: **79 passed**; `compileall` passed for four changed Python modules. Full suite by `pytest.ini` in a complete isolated copy without `.git`, `.venv`, secret `.env`, databases or runtime-user data: **3,016 passed in 12.09s**, exit code 0. Original `data/users.json` and `data/tasks.json` were neither copied nor changed. P04 accepted 2026-10-13; remaining API reasons and source mismatches are documented as unknown, never converted to zero.

- P04 stage A/C reconciliation and report-label fix: source findings and confidence are documented in `project_brain/P04_SOURCE_RECONCILIATION_2026-10-12.md`; offline/live evidence is not a test run. CSV recheck confirms 6,119 units (6,117 current SKU + 2 archived SKU). User-provided anonymized Analytics diagnostic returned 31 complete daily rows, `ordered_units=6117` (totals equal row sum), and no `cancellations`/`returns` values; this confirms they are unavailable in that response, not zero. No SKU breakdown was requested, so archive inclusion remains unverified. A returns XLSX has 271 FBO items across workflow statuses; live returns API confirms 270 `Cancellation` and 2 `ClientReturn` units in the August query, but not row-level correspondence or full enum semantics. Seller Returns fallback counts only `ClientReturn`; its Telegram label identifies that scope.
- P04 Analytics/операционные количества: `tests/test_experimental_store_economics.py`, `tests/test_ozon_analytics_data_client.py`, `app/tests/test_ozon_fbo_v3_returns_unit_economics.py` и связанные finance tests — **52 passed**. Проверены ограниченная Analytics pagination, отказ при исчерпании лимита, независимые field values, различение HTTP 403/429, cursor FBO/FBS, дедупликация отправлений и возвратов, fail-closed при конфликте товара и скрытие процентов при несовместимой когорте.
- P04 Seller Returns evidence: `tests/test_period_profit_return_evidence_service.py`, `tests/test_period_profit_return_evidence_response.py`, `tests/test_returns_buyout_facts_source.py`, `tests/test_returns_finance_attribution_facts_source.py` — **27 passed**.
- Объединённый повторный прогон перечисленных P04 наборов — **79 passed**; `compileall app tests` также прошёл. Единственное предупреждение pytest: Windows не разрешил записать `.pytest_cache`; тестам это не помешало.
- Returns API permissions, pagination and observed shape are confirmed for the user's August response. The Analytics shape and completeness are observed too; absence of `cancellations`/`returns` is confirmed for this query, but the reason is unknown. P04 is accepted with these source limitations documented. Full suite: **3,016 passed in 12.09s**.
- Независимая сверка без платной подписки по пользовательским выгрузкам: августовский CSV заказов — 6 119 строк/единиц, из них 6 117 по текущему SKU и 2 доставленные по архивному SKU; 5 726 строк сейчас «Доставлен», 393 — «Отменён». Все строки входят по дате принятия в август; отдельная дата отмены и схема FBO/FBS не указаны. Равенство Analytics-итога бота числу единиц текущего SKU указывает на возможное исключение архивной карточки, но не подтверждает API-контракт метрики. Новая XLSX возвратов содержит 271 FBO товар на разных этапах, 270 августовских дат статуса и 18 дат возврата продавцу. Она не означает 271 подтверждённый возврат продавцу и не эквивалентна доказанно Seller Returns API/Analytics. Оборотная ведомость за один день не является источником событий заказов. Это бизнес-данные для reconciliation, не API-shape тест и не результат pytest.
- P03 экспериментальной экономики: `tests/test_experimental_store_economics.py`, `tests/test_experimental_store_economics_factory.py`, `tests/test_finance_service_accrual_fee_breakdown.py` — **37 passed** на Windows Python 3.12. Покрыты баланс непересекающихся категорий, CPC/CPO/CPM, вложенная последняя миля, отдельное хранение, сверочная разница, округление микродолей, приватность и изоляция cached details по tenant/store, повторное открытие без API-вызова, отчёт реализации и строки отчёта ≠ продажи.
- Новая проверка сохраняет исходную подпись размещения из дневных начислений как справочную, если сумма категории подтверждена списком начислений по отправлениям; такая строка не добавляется повторно.
- Исторический полный запуск до последней полной копии: 2 628 passed / 21 failed / 359 errors. Актуальный результат указан в первом P04 пункте выше; предыдущие числа сохранены только как история запуска. Ранее P03-прогон с тем же видом ACL-ограничения также не считался успешным.
- P02 завершён: Windows Python 3.12, `compileall app` прошёл; полный стандартный набор `tests app/tests` — **2 998 passed** в изолированной копии без `.git`, `.venv`, секретного `.env` и runtime data. `PYTHON_DOTENV_DISABLED=true` исключил загрузку родительского `.env`; в копию добавлены только `.env.example` и `data/tax_configuration.json` для соответствующих тестов.
- Все 35 финансовых failures из P01/P02 закрыты. Включая canonical Return COGS status/evidence chain, June reversal fixtures, effective-cost bounds и reaccrual, fail-closed SKU identity diagnostics, direct finance quantity и duplicate same-day sale evidence.
- P02 quantity/identity targeted Windows checks: 34 passed для Return COGS diagnostics/status chain и 45 passed для direct finance quantity, effective-cost diagnostic/timeline, related SKU identity и sale quantity authority. Дополнительный cross-suite check вместе с catalog-SKU cost lookup и seller-cost Telegram flow: 49 passed.
- P02a seller-cost/CSV targeted verification: 27 passed. Coverage: date preview and explicit confirmation, separate two-step whole-history confirmation, cancel, stale store rejection, CSV preview, effective-date requirement for existing costs, atomic multi-row transaction, exact replay idempotency, and latest-date current projection.
- P02a tests: `tests/test_guided_seller_cost_onboarding.py`, `tests/test_seller_cost_table_service.py`, `app/tests/test_seller_cost_confirmation_flow.py`, `app/tests/test_telegram_seller_cost_switch.py`, `app/tests/test_telegram_seller_cost_display_offer_id.py`, `app/tests/test_tenant_seller_cost_switch_storage.py`.
- P02b targeted tests: `app/tests/test_period_profit_compact_return_cogs_authorization_commit_diagnostics.py`, `app/tests/test_period_profit_compact_return_cogs_diagnostics.py`, `app/tests/test_period_profit_compact_return_cogs_recognition_diagnostics.py`, `app/tests/test_period_profit_compact_return_inventory_warning.py`, `app/tests/test_period_profit_return_cogs_final_application_status_chain.py`, `app/tests/test_period_profit_june_reversal_reconciliation.py`, `app/tests/test_period_profit_direct_finance_quantity_chain.py`, `app/tests/test_period_profit_effective_cost_diagnostic.py`, `app/tests/test_period_profit_effective_cost_timeline.py`, `app/tests/test_period_profit_related_sku_identity.py`, `app/tests/test_period_profit_sale_quantity_authority.py`, `tests/test_period_profit_catalog_sku_cost_lookup.py`, `tests/test_sku_cost_profit_flow.py`.
- P02a tests: `tests/test_guided_seller_cost_onboarding.py`, `tests/test_seller_cost_table_service.py`, `app/tests/test_seller_cost_confirmation_flow.py`, `app/tests/test_telegram_seller_cost_switch.py`, `app/tests/test_telegram_seller_cost_display_offer_id.py`, `app/tests/test_tenant_seller_cost_switch_storage.py`.
- Команда стандартного набора: `python -m pytest -q`; `pytest.ini` включает `tests` и `app/tests`, CI использует ту же команду в `.github/workflows/verify.yml`.
- Исторический baseline до P02, Windows Python 3.12: `compileall` прошёл; 2 954 passed / 35 failed / 0 skipped из 2 989. Итог после P02 приведён выше; исходная группировка причин сохранена в `BASELINE_FAILURE_TRIAGE_2026-10-12.md`.
- P01 persistence coverage входит в полный зелёный корневой Windows `tests` run. Ключевые проверки — `test_task_persistence_kernel_lock_v378_v387.py` (включая два процесса), `test_task_persistence_crash_durability_v343_v352.py`, `test_task_persistence_concurrency_v323_v332.py`, `test_task_save_failure_integrity_v313_v322.py`, `test_task_persistence_write_lock_v333_v342.py`, `test_user_storage_atomic_write_integrity_v629_v637.py`, `test_telegram_runtime_health_shutdown_contract.py`, `test_task_persistence_operator_presentation_integrity_v821_v830.py`.
- Verify workflow сохраняет Linux Python 3.11 job и добавляет Windows Python 3.12 полный запуск. Windows локально проверен; Linux job ещё требует удалённого запуска на том же SHA.
- `app/tests` содержит 45 файлов и 217 тестов, главным образом проверки финансов, себестоимости, SKU-идентичности, Return COGS и tenant/Telegram интеграции. Полный Windows suite после P02 зелёный.
- В корне есть 90 старых `test_*.py`, 206 методов unittest. Они инвентаризированы в `LEGACY_TEST_INVENTORY_2026-10-12.md`, но не запускаются по умолчанию и не считаются проверенными. Перед добавлением в CI требуется отдельный безопасный прогон и исправление/объяснение зависимостей.
- Windows Python 3.12: baseline обнаруживает отсутствие backend `fcntl.flock`; Linux GitHub Verify использует Python 3.11. Платформенные исключения должны иметь соответствующие тесты на целевой ОС.

---

# Экспериментальная экономика магазина за период

Добавлены:

- `tests/test_experimental_store_economics.py`
- `tests/test_ozon_analytics_data_client.py`
- `tests/test_finance_service_accrual_fee_breakdown.py`

Обновлён:

- `tests/test_telegram_help_discovery.py`

Проверяет структуру экспериментального отчёта и маршрут до сообщения Telegram, доли денежных сумм от общей выручки, количества отмен/возвратов относительно заказанных единиц, использование нетто-начислений и налога, отдельное отображение CPC по точным SKU-сопоставлениям, группировку рекламных начислений по явным типам, сохранение возвратов отдельно от отмен, безопасные неизвестные/неполные значения, расчёт комиссии по явным типам начислений с переносом разницы в остаток без изменения нетто, обратную логистику в остатке без двойного вычитания, уточнённую подпись остатка, пояснение агрегации типов Ozon и короткое имя начисления размещения.

Проверяет, что агрегат финансовой сводки может отличаться от строк типов комиссии, а экспериментальный отчёт выбирает явные типы продажи и возврата вознаграждения, не показывает их повторно в детализации строки 14 и сохраняет нетто-начисления; проверяет исходные типы комиссии в `FinanceService`.

Проверяет, что валидные заказанные единицы сохраняются при отсутствующей/некорректной метрике отмен; полные Seller API записи FBO/FBS служат fallback для отмен и возвратов до Telegram; неполная страница не превращается в итоговое число; сообщения называют источник, периодный смысл и метрику простыми словами; агрегаты `totals` сохраняют дробные значения; отсутствие campaign ID не отображается как ноль кампаний; финальная клавиатура содержит только возврат к экспериментам и главное меню.

`tests/test_ozon_analytics_data_client.py` проверяет текущий FBS API v4 с курсорной пагинацией и fail-closed ошибкой для повторного курсора.

`tests/test_finance_service_accrual_fee_breakdown.py` использует локальные фикстуры для проверки новых `non_item_fee` и `container_fees`: суммы попадают в расшифровку по типам, а итоговое начисление берётся единственный раз из `total_amount`.

# Отдельный раздел экспериментальных расчётов

Updated:

- `app/services/assistant_keyboard_service.py`
- `app/services/assistant_button_handler_service.py`
- `tests/test_telegram_help_discovery.py`

Проверяет наличие кнопки в главном меню, вход в отдельный раздел, переход к периоду и возврат в главное меню. Сам расчёт изолирован в экспериментальном сервисе и не входит в основные сценарии.

# Форматирование прибыли без себестоимости

Updated:

- `app/services/assistant_period_profit_runtime_service.py`
- `tests/test_period_profit_pre_cogs_mode.py`

Проверяет форматирование крупной выручки, начислений, налога и результата с разделителями тысяч в сообщении Telegram без учёта себестоимости.

# Налоговая база и баллы за скидки Ozon

Обновлены:

- `app/tests/test_period_profit_finance_reconciliation.py`
- `tests/test_tax_calculation_input_result_integrity_v1101_v1110.py`
- `tests/test_period_profit_summary_service.py`
- `tests/test_discount_points_tax_end_to_end.py`
- `tests/test_tax_configuration_foundation.py`
- `tests/test_period_profit_sku_telegram_flow.py`
- `tests/test_period_profit_final_application_v1381_v1390.py`
- `tests/test_product_unit_economics.py`
- `tests/test_product_unit_economics_query.py`
- `tests/test_current_unit_economics_integration.py`
- `tests/test_period_profit_response.py`
- `tests/test_period_profit_compact_report_v1431_v1440.py`

Покрыты извлечение `commission.bonus`, общий и выбранный налоговый расчёт, минимум УСН «Доходы минус расходы», прохождение до сообщений периода и SKU, повторное вычисление после Return COGS, а также фактический процент налога для исторической и текущей юнит-экономики.

# Local capture of malformed CPO reports

Updated:

- `app/api/ozon_performance_historical_reports.py`
- `app/services/period_profit_sku_advertising_service.py`
- `app/services/period_profit_sku_runtime_service.py`
- `tests/test_ozon_performance_historical_reports.py`
- `tests/test_period_profit_sku_advertising.py`
- `tests/test_period_profit_sku_telegram_flow.py`

Covers saving the exact failed CPO CSV or whole ZIP under the ignored
`.runtime-data` directory, tenant-scoped storage paths, propagation of the safe
relative path through the advertising/runtime layers to the Telegram response,
and suppression of raw report values from exception and message diagnostics.
CPC reports are not captured, and no CPO spend fallback is added.

# CPO endpoint and ordinary SKU diagnostics

Updated:

- app/api/ozon_performance_historical_reports.py
- app/services/period_profit_sku_advertising_service.py
- app/services/period_profit_sku_runtime_service.py
- tests/test_ozon_performance_historical_reports.py
- tests/test_period_profit_sku_advertising.py
- tests/test_period_profit_sku_telegram_flow.py

Covers a blank promoted SKU with a populated ordinary order SKU in the selected-products CPO report. The endpoint and a boolean presence flag reach the Telegram message, while order IDs, SKU values, product names, and raw row labels stay out of diagnostics. Confirms selected-product spend remains fail-closed and only the all-products endpoint may use its existing fallback.

# Empty promoted SKU with zero or positive spend

Updated:

- app/api/ozon_performance_historical_reports.py
- tests/test_ozon_performance_historical_reports.py
- tests/test_period_profit_sku_advertising.py

Covers skipping a blank promoted-SKU row with zero spend; all-products CPO falls back to a numeric order SKU for positive spend, while selected-product reports and rows without a numeric order SKU remain fail-closed.

# Empty promoted SKU in CPO diagnostics

Updated:

- app/api/ozon_performance_historical_reports.py
- tests/test_ozon_performance_historical_reports.py
- tests/test_period_profit_sku_advertising.py

Covers a blank promoted-SKU cell from CSV parser through the historical advertising runtime to the Telegram message, where it is presented as a safe empty category.

## End-to-end CPO CSV row-label diagnostics

Updated:

- app/api/ozon_performance_historical_reports.py
- app/services/period_profit_sku_advertising_service.py
- app/services/period_profit_sku_runtime_service.py
- tests/test_period_profit_sku_advertising.py

Covers a real CSV parse failure flowing through the historical report loader,
advertising service, runtime sanitizer, and user-facing diagnostic message.
Only a categorical empty/non-numeric marker is retained; raw row values are not
passed to Telegram.


# Unit Price Scenario Calculator — U00 source audit (2026-10-14)

Baseline on code SHA `655b3a0` (Python 3.12, `PYTHONPATH=app`):

- Existing current economics, source, production wiring and discount-points/tax regression modules: **44 passed**.
- Source audit: `project_brain/UNIT_PRICE_CALCULATOR_SOURCE_AUDIT_2026-10-14.md`.
- Confirmed `sale_amount` is already included in gross sales; `bonus` is separately accumulated. Existing aggregate does not prove explicit bonus completeness, and `sales_count` counts positive product rows, not units.
- No implementation/live Ozon query in U00. New calculation/source/UI tests will be mapped here by their corresponding stages.

## Unit Price Scenario Calculator — U01 pure math

- `tests/test_unit_price_scenario_service.py`: **8 passed**.
- Verifies the signed 500 ₽/600 ₽ numeric fixtures; seller-price tax base; percent vs fixed-fee behavior; variable/fixed changes after repricing; loss and margin semantics; explicit zero vs missing; input validation including NaN/Infinity/bool; tax policy absence; and USN income-minus-expenses minimum-tax delegation.
- U01 production module has no Ozon, Telegram, storage or persistence dependency.

## Unit Price Scenario Calculator — U02 source adapter

- `tests/test_unit_price_scenario_source.py` covers finance evidence completeness, explicit zero vs missing bonus, complete pagination, exact SKU, identical/conflicting duplicates, 28-day weighted ratio, incomplete-day fallback, tenant preflight, cache isolation and deep copies.
- `app/services/finance_service.py::FinanceService.get_daily_discount_points_evidence` checks page completion and returns selected-SKU positive-sale evidence with explicit `bonus`; it does not alter the existing daily financial aggregate contract.
- Combined U01/U02 + current product source/wiring/integration + discount tax + finance pagination/reconciliation regressions: **62 passed** (Python 3.12). No live Ozon source check.

## Unit Price Scenario Calculator — U03 Telegram runtime

- `tests/test_unit_price_scenario_telegram_runtime.py` covers product selection, exact catalog SKU resolution, explicit ad zero vs unknown, localized numeric input, invalid/replayed callback handling, refresh preserving manual values, restore historical points, store scoping, clearing pending stages and current-unit-economics card CTA. It also checks the FBO-only estimate disclaimer.
- `tests/test_current_unit_economics_production_wiring.py` and adjacent current-economics/UI/finance routing regressions run with U01/U02/U03: **61 passed** (Python 3.12).
- `tests/test_period_profit_sku_telegram_flow.py::test_production_factory_exposes_sku_runtime`: **1 passed**. On this Windows sandbox the test was run as an isolated pytest invocation with a pre-created ACL-friendly temp root; its assertions were unchanged.
- `compileall -q` over changed production modules: passed. Full `pytest`, Linux/Windows CI and final review are U04.

## Unit Price Scenario Calculator — U04 local acceptance

- Architecture review confirmed that product selection should reuse the current unit-economics picker. Calculator selection mode now routes into that picker and consumes the existing `unit_economics:<offer_id>` selection; no parallel catalog keyboard is maintained. Regression tests cover the transition and per-store bounded selection state.
- Full Windows test suite on the final local tree: **3 119 passed**. The local harness uses an ACL-friendly pytest temp root because the Windows sandbox denies pytest's default temp ACL; test cases/assertions are unchanged. `AI_ASSISTANT_STORAGE_ROOT` is explicitly empty for legacy-storage compatibility tests.
- `python -m compileall -q app tests`: passed.
- `tests/test_unit_price_scenario_telegram_runtime.py::test_factory_leaves_optional_calculator_disabled_when_sources_are_unavailable` protects factory compatibility with partial external/test providers. Production composition wiring is also verified by `test_production_factory_exposes_sku_runtime`.
- GitHub CI run **38604317400** passed on implementation SHA `acb1e196`: Windows verification, full Linux verification, production Docker image build and runtime smoke. PR #695 remains open for independent architecture review; no merge/deploy was performed.

# Test Map

## Period Profit bounded Ozon quantity reads

Updated:

- `app/api/ozon_client.py`
- `app/services/period_profit_sale_quantity_summary_service.py`
- `app/services/period_profit_effective_cost_sale_quantity_summary_service.py`
- `app/services/period_profit_realization_offer_quantity_summary_service.py`
- `app/services/returns_buyout_facts_source.py`
- `app/tests/test_ozon_fbo_v3_returns_unit_economics.py`
- `app/tests/test_period_profit_direct_finance_quantity_chain.py`
- `app/tests/test_period_profit_sale_quantity_authority.py`
- `tests/test_returns_buyout_facts_source.py`

Covers exact realization evidence skipping redundant finance quantity batches,
retaining direct finance reads for unresolved postings in both total-period and
selected-SKU mode, one bounded FBO cursor pass with exact-detail fallback, and
the prohibition on account-wide FBO listing for selected SKU. Covers exact-full
cursor completion in the returns loader so offset windows cannot replay earlier
pages. Telegram progress, result formatting and production callback wiring are
verified by `tests/test_telegram_loading_feedback_v1451_v1460.py`,
`tests/test_telegram_period_profit_analyst_wiring_v1161_v1170.py`, and
`tests/test_period_profit_tenant_context_production_wiring.py`.

## Period Profit daily finance prefetch reuse

Updated:

- `app/services/period_profit_finance_service.py`
- `app/tests/test_period_profit_parallel_finance_reads.py`

Covers reuse of a complete request-local daily finance prefetch when the general
or selected-SKU calculation enters its summary read session, preventing the same
period's Ozon accruals from being downloaded twice. A different period or an
incomplete cache or request context still triggers a fresh bounded prefetch.

## Routing between total-period and selected-SKU profit

Updated:

- `app/services/assistant_period_profit_runtime_service.py`
- `app/services/assistant_button_handler_service.py`
- `app/services/period_profit_sku_runtime_service.py`
- `app/telegram_app_layer/telegram_response_formatter.py`
- `tests/test_telegram_custom_period_date_input_v1171_v1180.py`
- `tests/test_period_profit_sku_advertising.py`
- `tests/test_period_profit_sku_telegram_flow.py`
- `tests/test_telegram_response_formatter.py`

Covers replacing stale custom-period input when users switch between general,
pre-cost, and selected-SKU profit paths; verifies custom dates remain on the
chosen route through Telegram formatting. CPC double-count protection remains
fail-closed, its selected-SKU error has a safe user message, and unformatted
error dictionaries never expose attached context.

## Unknown SKU label in historical CPC report

Updated:

- `app/api/ozon_performance_historical_reports.py`
- `app/services/period_profit_sku_advertising_service.py`
- `app/services/period_profit_sku_runtime_service.py`
- `tests/test_ozon_performance_historical_reports.py`
- `tests/test_period_profit_sku_advertising.py`
- `tests/test_period_profit_sku_telegram_flow.py`

Covers skipping a nonnumeric CPC SKU row only when its expense parses to zero,
preserving fail-closed behavior for positive/invalid expenses, and safely saving
the failed CPC CSV/ZIP. Verifies endpoint, expense category, and the sanitized
path through the selected-SKU Telegram callback without exposing row values or
credentials.

## Selected-SKU profit excludes CPO

Updated:

- `app/api/ozon_performance_historical_reports.py`
- `app/services/period_profit_sku_advertising_service.py`
- `app/services/period_profit_sku_runtime_service.py`
- `app/services/ozon_performance_account_service.py`
- `tests/test_period_profit_sku_advertising.py`
- `tests/test_period_profit_sku_telegram_flow.py`

Covers CPC-only historical SKU profit, omission of both CPO order-report endpoints,
and an end-to-end Telegram callback fixture where CPC spend is applied while CPO
remains explicitly excluded from profit. The historical loader includes CPO only
when a caller explicitly sets `include_cpo=True`.

## CPO article-presence diagnostics

Updated:

- `app/api/ozon_performance_historical_reports.py`
- `app/services/period_profit_sku_advertising_service.py`
- `app/services/period_profit_sku_runtime_service.py`
- `tests/test_ozon_performance_historical_reports.py`
- `tests/test_period_profit_sku_advertising.py`
- `tests/test_period_profit_sku_telegram_flow.py`

Covers the boolean-only presence of the `Артикул` column value for selected CPO
rows with blank promoted and order SKUs, propagation through report loading and
advertising runtime, and display in Telegram. The article value, order data,
product name, and expense are not copied into diagnostics; article is not used
as a SKU mapping or expense-assignment fallback.

## CPO status dependency endpoint diagnostics

Updated:

- `app/services/period_profit_sku_runtime_service.py`
- `tests/test_period_profit_sku_advertising.py`

Covers allowlisted mapping from `CPO_SELECTED_ORDERS_REPORT_STATUS` to the
status-poll endpoint and an explicit `UNCLASSIFIED` marker when the dependency
error type is absent. This remains a sanitizer contract for explicit CPO loader
use; production selected-SKU profit does not request CPO reports. The report UUID
and all credentials remain out of diagnostics.

## Ozon Performance HTTP 429 backoff

Updated:

- app/api/ozon_performance_client.py
- app/api/ozon_performance_historical_reports.py
- tests/test_ozon_performance_client.py
- tests/test_ozon_performance_historical_reports.py

Covers safe Retry-After parsing, one bounded retry for idempotent GET requests,
no early retry beyond the wait cap, and no retry for GET report creation.

## Ozon campaign lookup failure diagnostics

Updated:

- tests/test_ozon_performance_historical_reports.py
- tests/test_period_profit_sku_advertising.py

Covers safe propagation of HTTP status, transient dependency category, invalid
response, generic unknown failure, bounded retry, and suppression of provider
response text in the user-facing diagnostic.

## Ozon Performance transient request failures

Updated:

- `tests/test_ozon_performance_client.py`
- `tests/test_ozon_performance_historical_reports.py`
- `tests/test_period_profit_sku_advertising.py`

Covers sanitized timeout/connection categories, one retry for idempotent GET
requests, no retry for report-creation POST, and Telegram propagation.

## Ozon Performance unknown CSV row labels

Updated:

- `tests/test_ozon_performance_historical_reports.py`
- `tests/test_period_profit_sku_advertising.py`

Covers skipping an exact repeated full header row, rejecting any other unknown
SKU row label, and propagating only the report kind and safe column names into
the user-facing diagnostic.

## Historical Ozon Performance dependency stage diagnostics

Updated:

- `tests/test_ozon_performance_historical_reports.py`
- `tests/test_period_profit_sku_advertising.py`

Covers safe stage labels for campaign discovery, CPC report creation/status, both
explicitly enabled CPO order report creation/status paths, and diagnostic
sanitization; unexpected labels are suppressed. The selected-SKU advertising
service opts out of CPO reports.


## Current Status


Verification model:

SHA-bound.

Latest confirmed full-suite baseline:

2208 passed on `3f82b65054a2a7a48b9918803c197377bdb3557f`.

GitHub Actions push Verify #1131 completed successfully for this exact main SHA.

Canonical status:

`project_brain/VERIFICATION_STATUS.md`


---


# Stabilization Checkpoint


Tests:


- test_action_context.py


Проверяет:


- сохранение Action schema
- сохранение priority
- сохранение context
- сохранение reason внутри context
- совместимость Action Generator и Action Executor



Result:


63 passed



---


# Core Flow

## Historical Performance SKU advertising reports

Test:

- `tests/test_ozon_performance_historical_reports.py`

Проверяет разбор SKU-level CPC/CPO reports, включая CPC-заголовок `Расход, ₽, с НДС`, выбор колонки рекламного расхода,
разбор итоговой строки `Bcero` с безопасным отказом для ненулевого или пустого
итога без SKU-разбивки, безопасную передачу этапа ошибки CSV/ZIP до выбранного
SKU, передачу ограниченных названий колонок без строк данных при неизвестном
заголовке и отказ от вывода небезопасных значений, разбиение периода на окна,
ожидание готовности отчёта дольше прежнего лимита и ограниченный таймаут,
пропуск известных CPM и CPO кампаний из явного CPC-отчёта, отбрасывание
кампаний вне периода по `fromDate`, `toDate` и `createdAt`, fail-closed реакцию
на отсутствующий `paymentType` у SKU-кампании по документированной схеме Ozon
и fail-closed обработку неизвестного явного значения. Проверяет повторную
загрузку неизвестных ID без фильтра типа объекта,
классификацию при найденном `paymentType`, использование уточнённых дат,
объединение диагностики неизвестных кампаний и безопасную передачу статуса
сверки, `paymentType`, дат, состояния и ID в сообщение ошибки выбранного SKU.

Проверяет CPO-отчёты по заказам для выбранных товаров и всех товаров, передачу `timeBounds.from/to` для второго отчёта, привязку расхода только к `SKU продвигаемого товара` и отказ от CSV со ставками без фактического расхода.

## Period Profit by selected SKU

Tests:

- tests/test_period_profit_sku_telegram_flow.py
- tests/test_telegram_period_profit_analyst_wiring_v1161_v1170.py
- tests/test_period_profit_selected_posting_offer_identity.py
- tests/test_period_profit_selected_scope_concurrency.py
- tests/test_period_profit_previous_period_single_pass.py
- tests/test_period_profit_operation_diagnostics.py

Проверяет Telegram SKU/period navigation, production factory wiring, aggregation of proven legacy/current SKU rows, configured tax recomputation, forged identity rejection, and fail-closed unknown money handling.
Также ограничивает количество Ozon posting-detail вызовов, проверяет однократный
previous-period pass, конкурентную изоляцию selected scope и автоматический stack dump.
Ошибка предзагрузки финансов проверяется на наличие безопасного кода диагностики
в Telegram-сообщении и на отсутствие сырого текста Ozon.
Проверяет восстановление offer identity по позднему posting через один месячный
realization request и fail-closed конфликт нескольких offers.
Проверяет rewritten realization SKU для однозначного posting и отклоняет тот же
fallback для multi-product posting.
Проверяет late-posting FBO snapshot без detail N+1 и возврат доказанной current
прибыли при недоступной identity только в previous comparison period.
Проверяет production-style scope с 200 посторонними finance SKU: один realization
request и отсутствие related/detail вызовов для чужих товаров.
Проверка request timeout использует контролируемый монотонный таймер и точно
подтверждает передачу оставшегося бюджета операции без временной флуктуации.

## Period Profit parallel finance reads

Test:

- tests/test_period_profit_parallel_finance_reads.py

Проверяет bounded parallel accrual/posting reads and request-local daily-cache
isolation when two active store calculations overlap on the same date.

## Telegram guided onboarding

Tests:

- tests/test_telegram_guided_onboarding.py

Проверяет production callback path, resumable missing-step detection, secret non-disclosure, tenant-scoped pending input and factory wiring.


## Main assistant flow


Tests:


- test_full_dependency_flow.py
- test_replanning_integration.py
- test_full_memory_agent_loop.py


Проверяет:


- полный путь пользователя
- создание плана
- выполнение действий
- зависимости
- replanning
- memory cycle



---


# Intent System


Service:


AssistantIntentService


Tests:


- test_intent*.py


Проверяет:


- команды пользователя
- подтверждение
- отмену
- паузу
- продолжение



---


# Task Lifecycle


Service:


AssistantTaskService


Tests:


- test_task_flow.py
- test_task_lifecycle_flow.py
- test_task_state_integration.py
- test_task_state_machine.py
- test_task_states.py


Проверяет:


- создание задачи
- состояния
- переходы
- завершение
- отмену
- паузу
- возобновление



---


# Action System


Services:


- AssistantActionGeneratorService
- AssistantActionPlanExecutorService
- AssistantActionExecutionService


Tests:


- test_action_context.py
- test_action_dependencies.py
- test_memory_guided_actions.py


Проверяет:


- генерацию действий
- priority
- context
- зависимости
- использование опыта при генерации действий
- сохранение Action contract



---


# Executors


Services:


- AssistantSalesExecutorService
- AssistantStockExecutorService
- AssistantMarketingExecutorService
- AssistantActionRouterService


Tests:


- test_action_dependencies.py
- test_full_dependency_flow.py


Проверяет:


- выбор исполнителя
- выполнение действия
- маршрутизацию



---


# Conditions


Tests:


- test_condition_skip.py


Проверяет:


- condition.contains
- блокировку действия
- статус SKIPPED
- skip_reason



---


# History


Services:


- ActionHistoryService
- AssistantTaskService


Tests:


- test_history.py
- test_history_response_skip.py
- test_history_failure.py
- test_retry_history.py
- test_retry_blocked_history.py


Проверяет:


- сохранение истории
- вывод пользователю
- причины пропуска
- ошибки выполнения
- retry события



---


# FAILED Execution Handling


Services:


- AssistantActionExecutionService
- RetryPolicyService


Tests:


- test_action_execution_failure.py
- test_retry_execution.py
- test_retry_policy.py
- test_retry_policy_integration.py
- test_retry_limit.py
- test_retry_limit_integration.py


Проверяет:


- перехват ошибок
- FAILED статус
- сохранение ошибки
- повторное выполнение
- retry policy
- ограничение количества попыток



---


# Smart Planning


Services:


- AssistantPlanningService
- AssistantReplanningService


Tests:


- test_multi_level_dependencies.py
- test_dependency_chain_validation.py
- test_dependency_validation.py
- test_dependency_cycle.py
- test_auto_replanning.py
- test_replanning_service.py
- test_replanning_execution_flow.py
- test_replanning_updates_task.py
- test_automatic_replanning_engine.py
- test_plan_correction.py


Проверяет:


- многоуровневые зависимости
- проверку плана
- обнаружение конфликтов
- автоматическое перепланирование
- корректировку плана



---


# Feedback Loop


Services:


- AssistantFeedbackService


Tests:


- test_feedback_loop.py
- test_feedback_auto_record.py
- test_feedback_execution_hook.py


Проверяет:


- получение результата выполнения
- анализ результата
- создание feedback события



---


# Memory System


Services:


- AssistantMemoryService


Tests:


- test_memory_service.py
- test_memory_integration.py
- test_feedback_memory_integration.py
- test_feedback_to_memory_flow.py


Проверяет:


- сохранение опыта
- получение опыта
- связь Feedback → Memory
- хранение результатов выполнения



---


# Memory-driven Planning


Services:


- AssistantPlanningService
- AssistantActionGeneratorService


Tests:


- test_memory_planning_integration.py
- test_memory_driven_planning.py
- test_memory_context_in_plan.py
- test_memory_guided_actions.py


Проверяет:


- поиск прошлого опыта
- передачу памяти в планирование
- использование опыта при генерации действий



---


# Full Autonomous Memory Loop


Tests:


- test_full_memory_agent_loop.py


Проверяет:


- выполнение задачи
- создание feedback
- сохранение опыта
- использование памяти в будущем



---


# Context


Services:


- AssistantUserContextService
- AssistantRequestContextService
- AssistantTaskContextService


Tests:


- test_action_context.py


Проверяет:


- передачу контекста
- сохранение данных пользователя



---


# Development Autopilot


Service:


AssistantChangeImpactService


Tests:


- test_change_impact.py


Проверяет:


- анализ изменяемого файла
- поиск затронутых сервисов
- поиск связанных тестов
- поиск связанной документации



---


# Development Rule


Новый функционал обязан:


1. иметь тест


2. быть добавлен в эту карту


3. обновить CURRENT_STATE.md


4. обновить CHANGELOG.md при завершении этапа


5. добавить архитектурное решение в DECISIONS.md при изменении структуры системы



---


# Development Autopilot


Service:


AssistantDocumentationManager


Tests:


- test_documentation_manager.py


Проверяет:


- безопасное добавление CHANGELOG записей
- безопасное добавление DECISIONS записей
- сохранение существующей истории
- append-only правило документации

---



# Development Autopilot


Service:


AssistantDocumentationDriftService


Tests:


- test_documentation_drift.py


Проверяет:


- поиск сервисов без документации
- контроль связи app/services и TEST_MAP.md
- обнаружение простого documentation drift

---

# Development Autopilot


Service:


AssistantDevelopmentWorkflowService


Tests:


- test_development_workflow.py


Проверяет:


- запуск development workflow
- создание последовательности шагов
- контроль состояния workflow
- завершение отдельных этапов

---

# Development Autopilot


Service:


AssistantGitCheckpointService


Tests:


- test_git_checkpoint.py


Проверяет:


- подготовку Git checkpoint
- анализ изменённых файлов
- создание checkpoint metadata
- подготовку commit message
- отсутствие автоматического commit

---

# Development Autopilot


Service:


AssistantProjectBrainManager


Tests:


- test_project_brain_manager.py


Проверяет:


- безопасное добавление записей в Project Brain
- сохранение существующей истории
- append-only обновления документации
- подготовку документационных изменений агентом

---

# Sales Intelligence


Service:


SalesIntelligenceService


Tests:


- test_sales_intelligence_service.py


Проверяет:


- constructor injection аналитического сервиса
- нормализацию sales metrics
- передачу previous period context
- формирование sales decline insight
- безопасный проброс ошибки аналитического слоя
- отсутствие зависимости от Action/Executor orchestration

---

# Sales Intelligence Integration


Services:


- SalesIntelligenceService
- AssistantSalesExecutorService


Tests:


- test_sales_intelligence_executor_integration.py


Проверяет:


- constructor injection Sales Intelligence в Sales Executor
- передачу profits и previous_result из Action context
- сохранение существующего executor contract
- преобразование metrics и insights в details
- проброс ошибки Sales Intelligence
- обратную совместимость executor без injected service

---

# Sales Intelligence Context Propagation


Services:


- AssistantRecommendationService
- AssistantPlanningService
- AssistantActionGeneratorService


Tests:


- test_sales_intelligence_context_propagation.py


Проверяет:


- перенос sales_context из report в sales recommendation
- сохранение profits и previous_result при построении plan
- сохранение sales context при генерации Action
- отсутствие обратной мутации recommendation context при enrichment Action
- отсутствие изменений Task Service и Executor pipeline

---

# Sales Intelligence Production Wiring


Composition Root:


- telegram_core_factory.py


Services:


- StoreAnalyticsService
- SalesIntelligenceService
- AssistantSalesExecutorService


Tests:


- test_sales_intelligence_production_wiring.py


Проверяет:


- создание StoreAnalyticsService в production composition root
- constructor injection analytics service в SalesIntelligenceService
- constructor injection SalesIntelligenceService в AssistantSalesExecutorService
- доступ production-wired Sales Executor через существующий Router
- выполнение sales action через production wiring
- отсутствие изменений Task Service, Action Execution и Router

---

# Sales Intelligence Business Data Input


Services:


- AssistantEntryService
- ProductService
- StorePeriodProfitService
- StoreAnalyticsService


Tests:


- test_sales_intelligence_business_data_input.py


Проверяет:


- пользовательский запрос начинается с AssistantEntryService
- загрузку product data через injected ProductService
- расчёт profits текущего и предыдущего периода через injected StorePeriodProfitService
- формирование sales_down из реального period comparison contract
- добавление profits и previous_result в report.sales_context
- сохранение sales_context через recommendation → planning → action generation
- нормализацию существующего SQLite product tuple на data-input boundary
- обратную совместимость AssistantEntryService без data dependencies
- отсутствие изменений Task/Action/Executor pipeline

---

# Stock Intelligence Foundation


Service:


StockIntelligenceService


Tests:


- test_stock_intelligence_service.py


Проверяет:


- расчёт current_stock из подготовленных stock data
- расчёт sales_velocity по sales_count и period_days
- расчёт days_of_stock
- классификацию CRITICAL/HIGH/MEDIUM/LOW reorder priority
- no sales case без деления на ноль
- empty/missing data contract
- отсутствие API clients, repositories и Action pipeline dependencies внутри domain service

---

# Stock Intelligence Integration


Services:


- StockIntelligenceService
- AssistantStockExecutorService


Tests:


- test_stock_intelligence_executor_integration.py


Проверяет:


- constructor injection Stock Intelligence в Stock Executor
- передачу stock_data, sales_data и period_days из Action context
- вызов StockIntelligenceService через существующий Stock Executor
- сохранение существующего executor response contract
- преобразование Stock Intelligence результата в details
- обратную совместимость executor без injected service
- отсутствие изменений Task Service, Action Execution, Router, Planning и Action Generator

---

# Stock Intelligence Context Propagation


Services:


- AssistantEntryService
- AssistantRecommendationService
- AssistantPlanningService
- AssistantActionGeneratorService


Tests:


- test_stock_intelligence_context_propagation.py


Проверяет:


- перенос подготовленного stock_context из request context в report
- передачу stock_context в stock recommendation
- сохранение stock_data, sales_data и period_days при построении plan
- сохранение stock context при генерации Action
- отсутствие обратной мутации recommendation context при Action enrichment
- отсутствие изменений Task Service, Action Execution, Router, Stock Executor и Stock Intelligence Service

---

# Stock Intelligence Production Wiring


Composition Root:


- telegram_core_factory.py


Services:


- StockIntelligenceService
- AssistantStockExecutorService


Tests:


- test_stock_intelligence_production_wiring.py


Проверяет:


- create_telegram_core() создаёт production Stock executor
- constructor injection StockIntelligenceService в AssistantStockExecutorService
- default reorder policy конфигурацию StockIntelligenceService
- доступ production-wired Stock Executor через существующий Router
- отсутствие изменений Task Service, Action Execution, Router, Planning и Action Generator
- отсутствие преждевременного Business Data Input / Ozon stock ingestion

---

# Stock Intelligence Business Data Input


Services:


- AssistantEntryService
- ProductService
- MetricsService
- StoreAnalyticsService
- FinanceService


Tests:


- test_stock_intelligence_business_data_input.py


Проверяет:


- получение FBO current stock через injected MetricsService
- получение sales_count за текущий period через StoreAnalyticsService.analyze_finance()
- формирование report.stock_context с stock_data, sales_data и period_days
- передачу stock_context в stock recommendation
- сохранение stock_context до Action Generator
- безопасный fallback без stock recommendation при недоступных stock data
- отсутствие изменений Task Service, Action Execution, Router, Stock Executor и StockIntelligenceService

---

# Finance Intelligence Foundation


Service:


FinanceIntelligenceService


Tests:


- test_finance_intelligence_service.py


Проверяет:


- нормализацию revenue, expenses, profit и margin
- вычисление profit и margin из подготовленных finance data
- insight для положительной прибыли
- обнаружение падения прибыли относительно предыдущего периода
- обнаружение роста расходов относительно предыдущего периода
- безопасный contract при отсутствии данных
- отсутствие dependencies на repositories, API clients и Action/Task/Executor pipeline

---

# Finance Intelligence Executor Integration


Services:


- FinanceIntelligenceService
- AssistantFinanceExecutorService


Tests:


- test_finance_intelligence_executor_integration.py


Проверяет:


- constructor injection FinanceIntelligenceService в Finance Executor
- передачу finance_data и previous_data из Action context
- вызов FinanceIntelligenceService через Finance Executor
- сохранение существующего executor response contract
- преобразование finance metrics и insights в details
- fallback без injected FinanceIntelligenceService
- отсутствие изменений Task Service, Action Execution, Router, Planning, Sales и Stock workflow

---

# Finance Intelligence Context Propagation


Services:


- AssistantEntryService
- AssistantRecommendationService
- AssistantPlanningService
- AssistantActionGeneratorService


Tests:


- test_finance_intelligence_context_propagation.py


Проверяет:


- перенос prepared finance_context из request context в report
- передачу finance_context в finance recommendation
- сохранение finance_data и previous_data при построении plan
- сохранение finance context при генерации Action
- отсутствие обратной мутации исходного и recommendation context
- отсутствие изменений Task Service, Action Execution, Router, Finance Executor и FinanceIntelligenceService

---

# Finance Intelligence Production Wiring


Composition Root:


- telegram_core_factory.py


Services:


- FinanceIntelligenceService
- AssistantFinanceExecutorService
- AssistantActionRouterService


Tests:


- test_finance_intelligence_production_wiring.py


Проверяет:


- create_telegram_core() создаёт production Finance executor
- constructor injection FinanceIntelligenceService в AssistantFinanceExecutorService
- наличие finance executor в существующем Router registry
- сохранение sales и stock executor mappings
- отсутствие Finance Data Input и новых finance data dependencies

---

# Finance Intelligence Business Data Input


Services:


- AssistantEntryService
- StorePeriodProfitService
- FinanceAnalyticsService
- ProfitService


Tests:


- test_finance_intelligence_business_data_input.py


Проверяет:


- использование existing current/previous period boundaries
- получение реальных по contract period profits через StorePeriodProfitService
- формирование finance_data и previous_data из gross_sales/gross_profit
- расчёт expenses как revenue - profit и margin для каждого периода
- сохранение finance_context в report
- передачу finance_context через recommendation → planning → action.context
- безопасное отсутствие finance recommendation при пустых finance data
- отсутствие новых repositories, API clients и orchestration layers

---

# Product-Level Finance Metrics


Services:


- StorePeriodProfitService
- ProfitService
- ProductProfitabilityProvider
- FinanceContextProvider


Tests:


- test_product_level_finance_metrics.py


Проверяет:


- сохранение product_id и sku на существующей period-profit data boundary
- подготовку product-level sales_count, revenue, cost, profit и margin без повторного расчёта прибыли
- безопасный пустой результат при отсутствии profits
- пропуск неполных sales/cost records вместо формирования вводящих в заблуждение metrics
- сохранение существующего FinanceContextProvider contract без product-level расширения
- отсутствие новых repositories, API clients, workflow и Cross-Domain logic

---

# Product Unit Economics Foundation v1.1


Services:


- ProductUnitEconomicsProvider
- TaxService
- ProductProfitabilityProvider
- ProfitService
- StorePeriodProfitService


Tests:


- test_product_unit_economics.py


Проверяет:


- расчёт SKU-level marketplace fees из revenue и net_accrual
- использование существующего TaxService для product-level tax
- расчёт net_profit, profit_per_unit и margin_percent после налога
- явный incomplete contract при отсутствии tax policy
- безопасный пропуск SKU без cost data
- поддержку нескольких SKU
- сохранение существующего ProductProfitabilityProvider contract
- отсутствие изменений Entry/Recommendation/Planning/Action/Executor workflow

---

# Product Unit Economics Query v1


Services:


- ProductUnitEconomicsQueryService
- ProductService
- StorePeriodProfitService
- ProductUnitEconomicsProvider
- TaxService


Tests:


- test_product_unit_economics_query.py


Проверяет:


- поиск SKU через существующий ProductService contract
- выбор только запрошенного SKU для period-profit calculation
- преобразование aggregate product economics в показатели на одну проданную единицу
- unit_price, cost, marketplace_fees, tax, net_profit_per_unit и margin_percent
- SKU_NOT_FOUND при отсутствии товара
- безопасный unavailable contract при отсутствии finance/cost data или продаж
- missing_fields без подстановки неизвестных расходов нулями
- форматирование advertising, storage, returns и неизвестного tax как «—»
- сохранение ProductProfitabilityProvider contract
- отсутствие изменений Entry/Recommendation/Planning/Action/Executor workflow
- отсутствие Cross-Domain логики и нового data layer

---

# Tax Configuration Foundation v1


Services:


- TaxConfigurationService
- TaxService
- ProductUnitEconomicsProvider


Composition Root:


- telegram_core_factory.py


Tests:


- test_tax_configuration_foundation.py


Проверяет:


- сохранение и загрузку tax policy в data/tax_configuration.json
- различие между отсутствующей конфигурацией и явным NONE
- USN_INCOME с configurable tax_rate
- USN_INCOME_MINUS_EXPENSES с minimum tax rate
- явный NONE как сохранённую пользовательскую policy
- безопасный unconfigured contract без скрытого tax=0
- ProductUnitEconomicsProvider возвращает tax/net profit как None при неизвестной policy
- production factory получает tax policy через DI вместо hardcoded tax_mode=NONE
- сохранение sales, stock и finance executor mappings

---

# Product Unit Economics Production Wiring v1


Composition Root:


- telegram_core_factory.py


Services:


- TaxConfigurationService
- TaxService
- ProductUnitEconomicsProvider
- ProductUnitEconomicsQueryService


Tests:


- test_product_unit_economics_production_wiring.py


Проверяет:


- production factory создаёт ProductUnitEconomicsProvider и ProductUnitEconomicsQueryService
- tax policy передаётся из TaxConfigurationService через constructor injection
- запрос SKU использует USN_INCOME
- запрос SKU использует USN_INCOME_MINUS_EXPENSES
- explicit NONE сохраняет настоящий tax=0
- отсутствие tax configuration сохраняет tax/net profit/margin как None
- существующие sales, stock и finance executor mappings не изменяются
- Telegram UI и Action/Executor workflow не затрагиваются

---

# Product Unit Economics Telegram UI v1


UI Boundary:


- AssistantKeyboardService
- AssistantButtonHandlerService
- telegram_assistant_factory.py
- telegram_api_bot.py


Backend:


- ProductUnitEconomicsQueryService


Tests:


- tests/test_product_unit_economics_telegram_ui.py
- test_assistant_keyboard_flow.py


Проверяет:


- кнопку «💰 Юнит-экономика товаров» в существующем main keyboard
- открытие меню выбора SKU
- получение SKU через существующий ProductService внутри query boundary
- callback unit_economics:<sku>
- вызов существующего ProductUnitEconomicsQueryService.query(sku)
- использование существующего format_response() без UI-расчётов
- отображение advertising, storage и returns как «—»
- отсутствие формулировки «Чистая прибыль»
- безопасный ответ при отсутствии товаров или SKU
- сохранение существующих analyze/plan/history/memory callbacks
- отсутствие изменений Sales/Stock/Finance и Action/Executor workflow
---

# Current Unit Economics Integration / Polish

Services:

- CurrentProductEconomicsSource
- ProductUnitEconomicsProvider
- ProductUnitEconomicsQueryService
- TaxConfigurationService

Production wiring:

- current_unit_economics_factory.py
- telegram_assistant_factory.py

Tests:

- test_current_product_economics_source.py
- test_current_unit_economics_finance_sku.py
- test_current_unit_economics_integration.py
- test_current_unit_economics_polish.py
- test_current_unit_economics_production_wiring.py
- test_unit_economics_offer_id_lookup.py

Проверяет:

- актуальную цену продавца из Ozon Price API
- разделение offer_id и внутреннего Ozon SKU
- получение свежих finance expenses
- отдельные logistics / last mile / acquiring
- отсутствие подстановки неизвестных данных нулём
- расчёт налога по TaxConfigurationService
- расчёт прибыли одной текущей единицы
- отображение расходов в рублях и процентах от цены
- production wiring в Telegram
- сохранение старого historical contract
- безопасный fallback

Full suite result:

217 passed

---

# Product Decisions v3 — Assortment Overview

Services:

- ProductBusinessDecisionQueryService
- AssistantButtonHandlerService
- AssistantKeyboardService

Tests:

- tests/test_product_business_decision_query_service.py
- tests/test_product_business_decision_telegram_ui.py
- tests/test_product_business_decision_production_wiring.py

Проверяет:

- использование артикула продавца для сводного запроса;
- устранение дубликатов товаров;
- сортировку по приоритету, дням запаса и артикулу;
- подсчёт решений для Telegram-сводки;
- кнопки с приоритетом, артикулом и действием;
- совместимость существующих callbacks карточки товара.

---

# Product Decisions v4 — Cache and Pagination

Services:

- ProductBusinessDecisionQueryService
- AssistantButtonHandlerService
- AssistantKeyboardService

Tests:

- tests/test_product_business_decision_query_service.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- повторное использование успешного решения в течение 10 минут;
- истечение TTL и повторный расчёт;
- защиту кэша от внешней мутации;
- отсутствие кэширования ошибок и недостаточных данных;
- восемь товаров на странице Telegram;
- переходы между страницами без изменения callback товара.

---

# Product Decision Memory v1

Services:

- ProductDecisionHistoryService
- ProductDecisionHistoryStorageService
- ProductBusinessDecisionQueryService

Composition:

- product_business_decision_factory.py
- telegram_assistant_factory.py

Tests:

- tests/test_product_decision_history_service.py
- tests/test_product_business_decision_query_service.py
- tests/test_product_business_decision_telegram_ui.py
- tests/test_product_business_decision_production_wiring.py

Проверяет:

- сохранение первой успешной базовой точки;
- отсутствие дубликата неизменившегося решения;
- фиксацию изменения типа решения или приоритета;
- игнорирование ошибок и недостаточных данных;
- ограничение истории на один артикул;
- восстановление истории из JSON;
- передачу истории через query cache;
- понятный переход между решениями в Telegram.

---

# Product Decision Feedback v1

Services:

- ProductDecisionHistoryService
- AssistantButtonHandlerService
- AssistantKeyboardService

Tests:

- tests/test_product_decision_history_service.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- сохранение USEFUL и NOT_RELEVANT в последнем снимке;
- идемпотентность повторной оценки;
- отказ при неизвестном feedback;
- отказ при отсутствии истории решения;
- Telegram-кнопки ручной оценки;
- корректную обработку feedback callback.

---

# Product Decision Outcome Correlation v1

Services:

- ProductDecisionHistoryService
- AssistantButtonHandlerService

Tests:

- tests/test_product_decision_history_service.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- связь feedback предыдущего снимка со следующим изменением;
- распознавание снижения и роста срочности;
- нейтральную смену решения при прежнем приоритете;
- отсутствие вывода без feedback;
- сохранение source_feedback и outcome;
- наблюдательную, не причинную формулировку Telegram.

---

# Product Decision Learning Summary v1

Services:

- ProductDecisionHistoryService
- AssistantButtonHandlerService
- AssistantKeyboardService

Tests:

- tests/test_product_decision_history_service.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- агрегацию товаров, снимков, feedback и outcomes;
- ссылку на итоги обучения из обзора ассортимента;
- вывод фактических количеств без причинных выводов;
- доступ к истории из карточки товара;
- ограничение истории пятью последними снимками в UI;
- перевод решений, приоритетов, feedback и наблюдений.

---

# Safe Product Action Proposals v1

Services:

- ProductDecisionActionProposalService
- ProductBusinessDecisionQueryService
- AssistantButtonHandlerService

Composition:

- product_business_decision_factory.py

Tests:

- tests/test_product_decision_action_proposal_service.py
- tests/test_product_business_decision_query_service.py
- tests/test_product_business_decision_production_wiring.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- безопасное сопоставление каждого типа решения с proposal;
- обязательное подтверждение для операционных проверок;
- monitoring-only без обязательного действия;
- постоянный execution_allowed=False;
- сохранение proposal в query cache;
- подсчёт предложений по ассортименту;
- русское представление следующего шага без технических кодов.

---

# Product Action Proposal Confirmation v1

Services:

- ProductActionProposalConfirmationService
- ProductDecisionHistoryService
- AssistantButtonHandlerService
- AssistantKeyboardService

Tests:

- tests/test_product_action_proposal_confirmation_service.py
- tests/test_product_decision_history_service.py
- tests/test_product_business_decision_query_service.py
- tests/test_product_business_decision_production_wiring.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- сохранение подтверждения и отклонения как намерения;
- идемпотентность повторного статуса;
- отклонение устаревшего и monitoring-only proposal;
- production wiring confirmation-service;
- Telegram callbacks и явный executed=False;
- отсутствие зависимости от Action Executor.

---

# Confirmed Product Task Drafts v1

Services:

- ProductActionTaskDraftService
- ProductActionTaskDraftStorageService
- ProductActionProposalConfirmationService
- AssistantButtonHandlerService

Composition:

- product_business_decision_factory.py

Tests:

- tests/test_product_action_task_draft_service.py
- tests/test_product_action_proposal_confirmation_service.py
- tests/test_product_business_decision_production_wiring.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- создание одного черновика на снимок решения;
- постоянное хранение и восстановление;
- закрытие черновика после отклонения;
- отсутствие выполнений и разрешения на выполнение;
- Telegram-сводку и переход из меню решений;
- production wiring отдельного draft-service.

---

# Product Task Draft Review Lifecycle v1

Services:

- ProductActionTaskDraftService
- ProductBusinessDecisionQueryService
- AssistantButtonHandlerService
- AssistantKeyboardService

Tests:

- tests/test_product_action_task_draft_service.py
- tests/test_product_business_decision_query_service.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- устаревание черновика после изменения снимка или proposal;
- сохранение актуального черновика при полном совпадении;
- идемпотентный терминальный архив;
- миграцию legacy-записей с назначением draft_id;
- reconcile в decision query pipeline;
- Telegram-сводку состояний и безопасную кнопку архива;
- постоянный executed=False.

---

# Product Draft Review Queue Prioritization v1

Services:

- ProductTaskDraftReviewQueueService
- AssistantButtonHandlerService
- AssistantKeyboardService

Composition:

- product_business_decision_factory.py

Tests:

- tests/test_product_task_draft_review_queue_service.py
- tests/test_product_business_decision_production_wiring.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- порядок по актуальности, исходному приоритету и типу review;
- исключение DISMISSED и ARCHIVED;
- oldest-first tie breaker и ограничение выдачи;
- counts по полной очереди до limit;
- русские причины и иконки Telegram;
- постоянный read-only и executed_count=0.

---

# Product Task Draft Detail and Audit v1

Services:

- ProductActionTaskDraftService
- AssistantButtonHandlerService
- AssistantKeyboardService

Tests:

- tests/test_product_action_task_draft_service.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- CREATED при создании черновика;
- полный порядок реальных lifecycle events;
- отсутствие событий от idempotent-команд;
- терминальность ARCHIVED;
- безопасное чтение legacy-записи без вымышленного аудита;
- detail callback, source metrics и русские event labels;
- отсутствие archive-кнопки у терминального черновика;
- executed=False во всех audit/detail результатах.

---

# Product Task Draft Readiness Checklist v1

Services:

- ProductTaskDraftReadinessService
- ProductDecisionHistoryService
- ProductActionTaskDraftService
- AssistantButtonHandlerService

Composition:

- product_business_decision_factory.py

Tests:

- tests/test_product_task_draft_readiness_service.py
- tests/test_product_action_task_draft_service.py
- tests/test_product_business_decision_production_wiring.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- готовность полных данных к ручной проверке;
- missing fields без подстановки оценок;
- блокировку устаревшего черновика;
- отдельные policy blockers для каждого proposal;
- summary counts и нулевую execution readiness;
- перенос исходных фактов в draft snapshot;
- Telegram detail и queue presentation.


---

# Product Decision Learning Coverage Navigation v1

Services:

- AssistantButtonHandlerService
- AssistantKeyboardService

Tests:

- tests/test_product_decision_learning_coverage_v493_v502.py

Проверяет:

- state-specific переход только в существующий `product_decision:<sku>`;
- отсутствие прямых feedback callbacks из coverage queue;
- отсутствие Product Decision query при открытии очереди;
- fail-closed обработку forged/malformed navigation;
- ограничение навигации видимыми top-10 SKU;
- сохранение `executed=False`.


---

# Store Period Default Composition Hardening

Services:

- StorePeriodRunnerService
- StorePeriodReportService
- StorePeriodSummaryService

Tests:

- test_store_period_runner.py
- test_store_period_report.py
- test_store_period_summary.py

Проверяет:

- отсутствие duplicate runner initialization;
- fail-closed результат при отсутствии period profit dependency;
- сохранение injected report-service path;
- fail-closed malformed summary runner output;
- отсутствие AttributeError на default summary composition.


---

# Unknown Advertising Financial Evidence v1

Services / composition:

- telegram_core_factory.create_telegram_core
- BusinessAnalyticsService
- SalesIntelligenceService
- AssistantSalesExecutorService
- AdvertisingDashboardService
- BusinessProfitDashboardService

Tests:

- tests/test_unknown_advertising_financial_evidence_v514_v520.py
- test_business_analytics.py
- tests/test_sales_intelligence_production_wiring.py

Проверяет:

- production default advertising evidence остаётся unknown;
- explicit zero остаётся известным нулём;
- unknown advertising блокирует business_profit и margin;
- unknown tax + advertising перечисляются как missing evidence;
- tax error не маскируется;
- Sales Intelligence не нормализует unknown profit в zero;
- seller-facing analysis/dashboard presentation показывает «—», а не 0/None.


---

# Finance Context Evidence Hardening v1

Services:

- FinanceContextProvider
- FinanceIntelligenceService
- AssistantFinanceExecutorService

Tests:

- tests/test_finance_context_evidence_v521_v526.py
- tests/test_finance_intelligence_business_data_input.py
- tests/test_finance_intelligence_executor_integration.py
- tests/test_intelligence_context_providers_refactor.py

Проверяет:

- fail-closed malformed/missing/non-finite financial facts;
- explicit zero remains valid;
- backward-compatible FinanceContextProvider output shape;
- no optimistic zero normalization;
- neutral gross-result insight wording;
- evidence-scoped Finance Executor labels;
- existing complete-evidence context propagation.


---

# Stock Evidence Availability Hardening v1

Services:

- StockContextProvider
- StockIntelligenceService
- AssistantRecommendationService

Tests:

- tests/test_stock_evidence_availability_v527_v533.py
- tests/test_stock_intelligence_business_data_input.py
- tests/test_stock_intelligence_service.py
- tests/test_intelligence_context_providers_refactor.py

Проверяет:

- unavailable stock evidence != verified safe stock;
- complete safe assortment evidence;
- preserved confirmed low-stock action context;
- partial/missing metrics and sales evidence;
- malformed/non-finite/boolean/negative values;
- cross-product evidence rejection;
- explicit zero sales / NO_SALES;
- non-clean general fallback wording under incomplete stock evidence.


---

# Sales Evidence Availability Hardening v1

Services:

- SalesContextProvider
- AssistantEntryService
- AssistantRecommendationService
- SalesIntelligenceService
- AssistantSalesExecutorService

Tests:

- tests/test_sales_evidence_availability_v534_v540.py
- tests/test_sales_intelligence_business_data_input.py
- tests/test_sales_intelligence_service.py
- tests/test_sales_intelligence_executor_integration.py
- tests/test_intelligence_context_providers_refactor.py

Проверяет:

- configured unavailable sales evidence != verified no-decline;
- preserved legacy no-data Entry fallback;
- preserved confirmed decline action context;
- malformed products / profit rows / comparison evidence;
- explicit zero change and zero sales metrics;
- malformed action context rejection before analytics;
- required revenue/gross-profit facts;
- unknown business-profit/margin preservation;
- no false stable insight from missing change;
- «—» presentation for unknown sales metrics.


---

# Marketing Evidence Integrity v1

Services:
- AssistantRecommendationService
- AssistantMarketingExecutorService
- AssistantActionRouterService

Tests:
- tests/test_marketing_executor.py
- tests/test_marketing_recommendation.py
- tests/test_marketing_evidence_integrity_v548_v553.py

Проверяет explicit evidence gating, malformed evidence fail-closed, no invented marketing facts и FAILED lifecycle через router.run().

---

# Finance Evidence Availability Propagation v1

Services:

- AssistantEntryService
- FinanceContextProvider
- AssistantRecommendationService

Tests:

- tests/test_finance_evidence_availability_v554_v560.py
- tests/test_finance_context_evidence_v521_v526.py

Проверяет:

- derived finance success -> available;
- derived finance failure with period evidence -> unavailable;
- no invented availability without period data;
- explicit finance context precedence;
- unavailable finance evidence blocks clean fallback;
- contradictory unavailable context does not create finance action;
- legacy finance_context-only callers remain compatible;
- no finance formula/provider-shape change.

---

# Business Planner Result Integrity v1

Services:

- AssistantBusinessPlannerService
- AssistantRecommendationService
- AssistantPlanningService
- AssistantActionPlanExecutorService
- AssistantTaskService

Tests:

- tests/test_business_planner_result_integrity_v575_v581.py
- tests/test_action_plan_result_integrity_v568_v574.py

Проверяет:

- сохранение explicit downstream error=True без перепаковки в success;
- fail-closed malformed recommendation/planning/execution/task-create payloads;
- exact boolean error contracts;
- actions/count consistency;
- отсутствие task creation после downstream failure;
- сохранение valid plan result и general-only non-actionable path.

---

# Business Flow Result Integrity v1

Services:

- AssistantBusinessFlowService
- AssistantIntentService
- AssistantBusinessPlannerService
- AssistantActionExecutionService
- AssistantTaskService

Tests:

- tests/test_business_flow_result_integrity_v582_v590.py
- tests/test_business_planner_result_integrity_v575_v581.py
- tests/test_action_plan_result_integrity_v568_v574.py

Проверяет:

- malformed intent/result contracts fail closed;
- planner error=True не перепаковывается в success;
- malformed planner actions/count не становятся пустым successful plan;
- execute error/malformed result не получает текст «Действие выполнено»;
- cancel/pause/resume failure не получает success wording;
- task read malformed payloads fail closed;
- skip next-action error не маскируется как “нет шага”;
- malformed skip target блокируется до mutation;
- committed skip + later next-read failure reports partial state without fake rollback;
- continue validates next-action and pending-action persistence result;
- valid seller-facing shapes remain compatible.


---

# Top-Level Result Integrity v1

Services:

- AssistantOrchestratorBusinessService
- AssistantMainFlowService
- AssistantResponseBuilderService

Tests:

- tests/test_top_level_result_integrity_v591_v596.py
- tests/test_cancel_execution_block.py

Проверяет:

- malformed top-level Business Flow results fail closed instead of becoming success or raising KeyError;
- explicit execution error=True remains a top-level failure with a safe seller-facing message;
- malformed execution payloads cannot receive success wording;
- nested task-read error payloads cannot be repackaged as successful status/history/details/next results;
- business-plan actions/count consistency is validated at the upper orchestration boundary;
- malformed business-service and response-service payloads fail closed;
- explicit upstream errors are preserved by the response builder;
- cancelled-task execution remains error=True rather than a false successful state;
- no new business mutation, Product Decision execution, or Ozon mutation path is enabled.


---

# Entry/Core Result Integrity v1

Services:

- AssistantEntryService
- AssistantCoreService

Tests:

- tests/test_entry_core_result_integrity_v597_v603.py
- tests/test_assistant_entry_freshness_operational_route.py
- tests/test_assistant_entry_period_profit_route.py
- tests/test_task_persistence_operator_access_v368_v377.py
- tests/test_task_persistence_operator_readiness_v358_v367.py

Проверяет:

- direct runtime success/failure payloads require an explicit boolean error marker;
- malformed direct runtime payloads fail closed with deterministic non-secret codes;
- valid explicit runtime failures are preserved;
- malformed orchestrator results fail closed before context attachment;
- legacy fixtures match the actual explicit-success production contract;
- no new mutation or business execution path is enabled.


---

# Context Provider Result Integrity v1

Service:

- AssistantEntryService

Tests:

- tests/test_context_provider_result_integrity_v604_v611.py

Проверяет:

- malformed stock-provider results cannot reach report.update;
- unavailable stock evidence is explicit and does not prove a clean state;
- malformed sales reports cannot be converted/merged as success;
- unavailable sales evidence remains explicit;
- malformed or partial finance-provider output cannot reach report.update;
- unavailable finance evidence remains explicit;
- valid stock/sales/finance context shapes remain compatible;
- no business mutation or execution path is enabled.


---

# User Context Result Integrity v1

Services:

- AssistantUserContextService
- AssistantCoreService

Tests:

- tests/test_user_context_result_integrity_v612_v619.py

Проверяет:

- malformed profile get_user results fail closed before user/context access;
- malformed context and memory payloads are rejected;
- context/memory save result contracts are validated;
- malformed initial user context blocks orchestration before business execution;
- post-execution context persistence/refresh failures do not falsely imply rollback;
- already-produced business result semantics are preserved with a separate context persistence issue marker;
- data/users.json is not modified by the package.


---

# User Storage Load Integrity v1

Service:

- AssistantUserStorageService

Tests:

- tests/test_user_storage_load_integrity_v620_v628.py

Проверяет:

- malformed/unreadable JSON storage becomes explicit unavailable state;
- invalid top-level storage roots fail closed;
- load errors block create/memory/history mutation and preserve the original file;
- malformed existing user records are not replaced;
- save failures return explicit errors;
- uncommitted in-memory user/memory/history mutations roll back when save fails;
- absent-store creation and valid persistence remain compatible;
- regression tests use temporary paths and do not modify repository data/users.json.


---

# Memory Persistence Result Integrity v1

Services:

- AssistantMemoryService
- AssistantMemoryIntegrationService
- AssistantFeedbackService

Tests:

- tests/test_memory_persistence_result_integrity_v652_v659.py

Проверяет:

- storage save `False` no longer becomes memory success;
- explicit boolean rejection rolls back only the uncommitted in-memory mutation;
- storage exceptions and malformed results fail closed without fabricated rollback;
- ambiguous persistence state remains explicit;
- memory integration stops after the first failed save;
- a second-save failure reports partial memory state instead of full success;
- feedback already recorded before memory failure is reported as partial state;
- default in-memory production behavior remains compatible;
- no new persistence layer, business execution, Product Decision execution, or Ozon mutation is enabled.


---

# Telegram Memory Clear Integrity v1

Service:

- AssistantTelegramMemoryService

Production composition:

- telegram_assistant_factory.create_telegram_assistant
- AssistantUserStorageService

Tests:

- tests/test_telegram_memory_clear_integrity_v660_v667.py

Проверяет:

- clear mutates the canonical nested user record instead of the get_user result wrapper;
- explicit user-storage errors are preserved and block save;
- malformed user and memory payloads fail closed before mutation;
- explicit pre-commit save failures restore the previous in-memory memory object;
- malformed or exceptional save outcomes do not fabricate rollback and report unknown persistence state;
- post-commit durability warning keeps the clear committed;
- exception details are not leaked through stable error codes;
- no new persistence layer, business execution, Product Decision execution, or Ozon mutation is enabled;
- repository data/users.json remains untouched.


---

# History Clear Integrity v1

Service:

- AssistantHistoryService

Production composition:

- telegram_assistant_factory.create_telegram_assistant
- AssistantUserStorageService

Tests:

- tests/test_history_clear_integrity_v668_v676.py

Проверяет:

- clear mutates the canonical nested user history instead of the get_user result wrapper;
- canonical history remains a list and is cleared to an empty list;
- explicit user-storage errors are preserved and block save;
- malformed user and history payloads fail closed before mutation;
- explicit pre-commit save failures restore the previous in-memory history list;
- malformed or exceptional save outcomes do not fabricate rollback and report unknown persistence state;
- post-commit durability warning keeps the clear committed;
- exception details are not leaked through stable error codes;
- no new persistence layer, business execution, Product Decision execution, or Ozon mutation is enabled;
- repository data/users.json remains untouched.


---

# Telegram TypeError Retry Integrity v1

Runtime boundaries:

- TelegramRunner
- TelegramBotService
- AssistantTelegramAdapter
- telegram_call_compat.call_with_legacy_arity

Tests:

- tests/test_telegram_dispatch_typeerror_integrity_v677_v686.py

Проверяет:

- legacy one-argument Telegram callables remain supported;
- callable arity is selected before invocation;
- internal handler TypeError is never treated as an arity mismatch after the handler has started;
- Runner message/callback dispatch does not retry a failing bot handler;
- BotService message/callback dispatch does not retry a failing adapter;
- AssistantTelegramAdapter does not retry a failing button handler;
- a partially started handler cannot be invoked a second time by the compatibility fallback;
- no business rule, persistence owner, Product Decision execution, Product Task Draft execution, or Ozon mutation is enabled;
- repository data/users.json remains untouched.


---

# Telegram User Admission Integrity v1

Runtime boundary:

- AssistantTelegramAdapter

Production persistence:

- AssistantUserStorageService via telegram_assistant_factory.create_telegram_assistant

Tests:

- tests/test_telegram_user_admission_integrity_v687_v695.py

Проверяет:

- explicit create_user error blocks successful /start UI;
- explicit profile errors stop text before memory-command and assistant dispatch;
- explicit profile errors stop button callbacks before button-handler dispatch;
- malformed profile results fail closed;
- profile exceptions become stable non-secret errors;
- successful canonical user admission preserves start/text/button behavior;
- no-user-id legacy flows remain compatible;
- no persistence owner/layer, Product Decision execution, Product Task Draft execution, or Ozon mutation is enabled;
- repository data/users.json remains untouched.


---

# Telegram Command Result Integrity v1

Services / boundaries:

- AssistantMemoryCommandService
- AssistantTelegramAdapter
- TelegramBotService

Tests:

- tests/test_telegram_command_result_integrity_v696_v705.py
- tests/test_telegram_user_admission_integrity_v687_v695.py

Проверяет:

- unrecognized memory text is explicit handled=False, not an operational failure;
- recognized memory commands remain handled=True;
- storage failures from recognized memory commands stop before assistant fallback;
- malformed/exceptional memory-command results fail closed;
- TelegramBotService rejects malformed non-None command results;
- explicit command failures are preserved;
- successful /start now has explicit error=False;
- failed intermediate SHA acc3eb4023aa046544056eea2c634e0906bc00b3 remains failed evidence;
- no business execution authorization, Product Decision/Product Task Draft execution, or Ozon mutation is enabled;
- repository data/users.json remains untouched.


---

# Telegram Adapter Downstream Result Integrity v1

Boundary:

- AssistantTelegramAdapter

Tests:

- tests/test_telegram_adapter_downstream_result_integrity_v706_v713.py

Проверяет:

- assistant.ask result must be dict with explicit boolean error;
- malformed assistant results fail closed;
- explicit assistant failures are preserved;
- button_handler.handle result must be dict with explicit boolean error;
- malformed button results fail closed;
- explicit button failures are returned without freshness enrichment;
- valid draft-button successes keep existing freshness enrichment;
- internal exceptions are not caught or retried, preserving the no-duplicate-dispatch contract;
- failed intermediate SHA f990a7cc9abf8b2fd587e8339329d7d3a29e497a remains failed evidence;
- no business execution authorization, Product Decision/Product Task Draft execution, or Ozon mutation is enabled;
- repository data/users.json remains untouched.


---

# Product Decision Telegram Result Integrity v1

Boundary:

- AssistantButtonHandlerService Product Decision overview/detail Telegram paths

Tests:

- tests/test_product_decision_telegram_result_integrity_v714_v721.py

Проверяет:

- explicit query_all error=True is not rewritten as empty assortment success;
- malformed overview results fail closed;
- overview success requires explicit decisions/counts/total/actionable_proposals_count;
- overview total must match decisions length;
- malformed decision items fail closed before keyboard construction;
- valid empty overview remains a legitimate empty success;
- malformed detail results fail closed instead of using optimistic error=False;
- explicit detail failures remain failures without feedback navigation;
- valid read-only Product Decision cards/navigation remain compatible;
- failed intermediate SHA d804b6d89fdee8457dd8473ce6923b9c426d29d4 remains failed evidence;
- no Product Decision rules, thresholds, persistence, Product Task Draft execution, business execution authorization, or Ozon mutation changed;
- repository data/users.json remains untouched.


---

# Financial Telegram Result Integrity v1

Boundary:

- AssistantButtonHandlerService Unit Economics / Returns Finance Impact detail paths

Tests:

- tests/test_financial_telegram_result_integrity_v722_v730.py
- tests/test_product_unit_economics_telegram_ui.py
- tests/test_observed_returns_impact_production_wiring.py

Проверяет:

- Unit Economics query result requires dict + explicit boolean error;
- successful Unit Economics result requires availability/source/SKU/missing-fields evidence;
- legitimate available=False remains evidence-limited success;
- malformed Unit Economics result fails closed before formatter access;
- Returns Finance Impact result requires explicit boolean error and safe period/category/missing-data shape;
- malformed returns categories fail closed before formatter access;
- explicit financial downstream errors remain errors;
- valid incomplete observed-return evidence remains seller-visible without false adjusted-profit claims;
- failed intermediate SHA 64d34b244f790065acb0a636542a5684bd598dec remains failed evidence;
- cancelled intermediate SHA fdd90ff6368178bf14896cc2d02f3aa57af90291 remains unknown/cancelled evidence and is not reused;
- no financial formula, tax/fee arithmetic, Product Decision rule, persistence, Product Task Draft execution, business execution authorization, or Ozon mutation changed;
- repository data/users.json remains untouched.


---

# Product Task Draft Telegram Result Integrity v1

Boundary:

- AssistantButtonHandlerService Product Task Draft summary/detail/archive Telegram paths

Tests:

- tests/test_product_task_draft_telegram_result_integrity_v731_v742.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- summary result requires explicit boolean error and exact DRAFT/STALE/DISMISSED/ARCHIVED counts;
- missing lifecycle counts cannot become seller-facing zero evidence;
- raw task-draft list is validated before review-queue prioritization;
- review queue requires exact priority counts, valid reviewable items and executed_count=0;
- readiness summary and per-draft readiness require explicit non-executable contracts;
- malformed detail result fails closed before rendering task-draft/audit data;
- malformed detail readiness fails closed;
- archive cannot claim success without matching ARCHIVED draft, explicit saved bool, executed=False and execution_allowed=False;
- idempotent saved=False archive remains a legitimate non-executable success;
- failed intermediate SHA fb64d3deeb5d7bd9a6e42772fe7614630ad6ed03 remains failed evidence;
- cancelled intermediate SHA 61db8a964cfeed77e0b5caf451c705c6a77e3b51 remains cancelled/unknown evidence;
- no Product Task Draft execution, Action Executor connection, business execution authorization or Ozon mutation is enabled;
- repository data/users.json remains untouched.


---

# Product Decision Interaction Persistence Integrity v1

Services / boundaries:

- ProductDecisionHistoryService
- ProductActionProposalConfirmationService
- AssistantButtonHandlerService Product Decision feedback / proposal confirmation Telegram paths

Tests:

- tests/test_product_decision_interaction_persistence_result_integrity_v743_v754.py
- tests/test_product_business_decision_telegram_ui.py

Проверяет:

- explicit storage save=False for feedback/proposal status is treated as a proven non-commit and only that local interaction mutation is rolled back;
- storage exceptions and malformed save results remain ambiguous persistence state with saved=None and no fabricated rollback;
- exception text is not leaked through interaction persistence errors;
- Product Action Proposal Confirmation validates history-write results before any Task Draft create/dismiss side effect;
- rejected, ambiguous or malformed history-write results cannot create or dismiss Product Task Drafts;
- seller-facing Telegram feedback and proposal confirmation require dict + explicit boolean error contracts;
- successful Telegram interaction results require matching SKU/status/type plus real boolean saved;
- proposal confirmation success requires explicit executed=False and execution_allowed=False;
- malformed Task Draft result payloads are not promoted into successful created-draft presentation;
- valid idempotent saved=False feedback/proposal semantics remain supported;
- Product Decision rules, thresholds, feedback meaning, proposal meaning and Product Task Draft execution policy are unchanged;
- no Action Executor connection, business execution authorization, quantity/price inference or Ozon mutation is enabled;
- repository data/users.json remains untouched.


---

# Product Decision Learning Telegram Result Integrity v1

Boundary:

- AssistantButtonHandlerService Product Decision learning summary/history Telegram paths

Tests:

- tests/test_product_decision_learning_telegram_result_integrity_v755_v765.py

Проверяет:

- learning summary result must be a dict with explicit real boolean `error`;
- successful summary counts must be non-negative non-booleans;
- feedback and outcome subtotal counts must be internally consistent;
- missing summary evidence cannot become seller-facing zero through optimistic defaults;
- a structurally valid all-zero summary remains legitimate read-only success;
- decision history must be a real list; `None` or malformed payload cannot become empty success;
- history records must match the requested SKU and use known decision/priority values plus a non-empty recorded timestamp;
- optional feedback/outcome values are validated before label formatting;
- unknown feedback is not mislabeled as `NOT_RELEVANT`;
- a structurally valid empty history remains legitimate read-only success;
- stable failures do not expose internal exception text;
- production evidence is exact-SHA bound: entering main #440, feature #442, PR merge-ref #443, squash-main #444;
- no Product Decision rule/threshold, persistence behavior, Product Task Draft execution, Action Executor connection, business mutation authorization, quantity/price inference, or Ozon mutation changed;
- repository data/users.json remains untouched;
- `externally_verified=False`.


---

# Telegram Analyze / Plan History Integrity v1

Boundary:

- `AssistantButtonHandlerService` Telegram `analyze` / `plan` buttons
- canonical history persistence result boundary

Tests:

- `tests/test_telegram_analyze_plan_history_integrity_v766_v773.py`

Проверяет:

- explicit assistant `error=True` is preserved and does not write success history;
- malformed assistant result fails closed before history persistence;
- valid assistant success records the exact event once;
- explicit history failure is surfaced after assistant completion;
- malformed history result preserves unknown persistence state;
- history exceptions are sanitized and do not fabricate rollback;
- no-user / absent-history-service compatibility is preserved;
- exact-SHA evidence: main #449, feature #451, PR merge-ref #452, squash-main #453;
- no execution authorization, Ozon mutation, quantity/price inference, or new persistence layer;
- `data/users.json` untouched; `externally_verified=False`.


---

# Telegram History / Memory Read Integrity v1

Boundary:

- `AssistantButtonHandlerService` History / Memory Telegram reads

Tests:

- `tests/test_telegram_history_memory_read_integrity_v774_v783.py`

Проверяет:

- unavailable service cannot become clean empty data;
- missing user context cannot become zero/clean evidence;
- read exceptions return stable non-secret failures;
- result must be dict with exact boolean `error`;
- History success requires list `history`;
- Memory success requires dict `memory`;
- explicit downstream failures are preserved;
- legitimate empty and non-empty read-only data remain success;
- exact-SHA evidence: main #457, feature #459, PR merge-ref #460, squash-main #461;
- no execution authorization, Ozon mutation, quantity/price inference, or persistence-layer change;
- `data/users.json` untouched; `externally_verified=False`.


---

# Telegram Context Preparation Integrity v1

Boundary:

- `AssistantButtonHandlerService.prepare_context`
- Telegram analyze / plan orchestration before assistant execution
- existing `AssistantUserContextService.update` / `AssistantTaskContextService.update_task` result contracts

Tests:

- `tests/test_telegram_context_preparation_integrity_v784_v792.py`

Проверяет:

- first context update failure/malformed result stops downstream task update and assistant/history side effects;
- context exceptions return stable non-secret failures and are not retried;
- second update failure after proven first success reports partial context state instead of fabricated rollback;
- malformed/exceptional second update preserves unknown current-task state;
- valid context preparation invokes assistant once and records history once;
- absent context service and absent user ID preserve optional-context behavior;
- exact-SHA evidence: entering main #465, cancelled #466, final feature #468, PR merge-ref #469, squash-main #470;
- cancelled #466 is not green evidence even though its test/artifact steps completed;
- no Product Decision/Product Task Draft execution, Action Executor connection, business mutation authorization, quantity/price inference, Ozon mutation, or persistence-layer addition;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Task Draft Freshness Telegram Presentation Integrity v1

Boundary:

- `AssistantTelegramAdapter` Product Task Draft list/detail freshness enrichment
- read-only presentation only; Product Task Draft execution remains disabled

Tests:

- `tests/test_product_task_draft_freshness_telegram_presentation_integrity_v793_v802.py`

Проверяет:

- malformed readiness summary containers fail closed;
- partial/negative/boolean freshness count maps cannot invent zero categories;
- valid all-zero freshness counts remain legitimate success;
- malformed optional coverage/source-timestamp/refresh maps fail closed when present;
- absent optional presentation evidence is omitted rather than synthesized;
- malformed detail readiness/freshness/status/age/reason fails closed before formatter use;
- malformed coverage components and refresh guidance targets fail closed;
- legitimate UNKNOWN freshness, observed-only evidence and refresh guidance remain read-only success;
- exact-SHA evidence: entering main #474, feature #476, PR merge-ref #477, squash-main #478;
- no Product Decision rule/threshold, Task Draft readiness rule, persistence behavior, Action Executor connection, execution authorization, quantity/price inference, or Ozon mutation changed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Telegram Adapter Runtime Exception Containment v1

Boundary:

- `AssistantTelegramAdapter` assistant/button/keyboard runtime exception boundary

Tests:

- `tests/test_telegram_adapter_runtime_exception_containment_v803_v810.py`

Проверяет:

- internal assistant/button/keyboard exceptions are contained;
- TypeError is not retried after invocation;
- legacy handler arity remains pre-call selection only;
- exception text is sanitized;
- one invocation remains one invocation;
- exact-SHA evidence: entering main #482, cancelled #483, failed #484, final feature #485, PR merge-ref #486, squash-main #487;
- no Product Decision/Product Task Draft execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Post-Decision Observation Integrity v1

Boundary:

- `build_product_decision_user_action_post_decision_observation`
- user-reported completion evidence to later Product Decision observation

Tests:

- `tests/test_product_decision_user_action_post_decision_observation.py`
- `tests/test_product_decision_user_action_post_decision_observation_integrity_v811_v820.py`

Проверяет:

- malformed containers fail closed;
- explicit checklist error=False and USER_REPORT semantics are required;
- numeric identity coercion is rejected;
- explicit later-decision failure is preserved;
- canonical decision/priority/confidence values are required;
- reasons cannot be synthesized from malformed strings;
- valid observations remain non-causal, non-executable and not externally verified;
- exact-SHA evidence: entering main #492, feature #494, PR merge-ref #495, squash-main #496;
- no Product Decision recomputation, Product Task Draft execution, Action Executor connection or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Task Persistence Operator Presentation Integrity v1

Boundary:

- `TaskPersistenceOperatorPresentationService`
- operator-only operational / release / provenance presentation

Tests:

- `tests/test_task_persistence_operator_presentation_integrity_v821_v830.py`
- existing task-persistence operator readiness/access/release/provenance regression suites

Проверяет:

- explicit error=False before presenting trusted operator state;
- blockers/warnings/categories must be real unique string lists;
- operational state/count/attention consistency;
- release-ready/incident/human-review consistency;
- provenance revision and CI binding shape;
- external-verification, mutation and execution overclaims fail closed;
- valid messages never expose paths, user IDs, inferred lock owner or inferred lock age;
- failed SHA `41c289221c100ce4dc1462603b42349434f2f406` / Verify #498 remains failed evidence;
- final exact-SHA evidence: feature #499, PR merge-ref #500, squash-main #501;
- no persistence owner change, automatic retry, lock removal, business execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Persistence Verification Integrity v1

Boundary:

- `ProductDecisionPersistenceVerificationService`
- durable Product Decision read-back trust boundary before downstream user-action guidance

Tests:

- `tests/test_product_decision_persistence_verification_service.py`
- `tests/test_product_decision_persistence_verification_integrity_v831_v840.py`

Проверяет:

- non-mapping application input fails closed;
- lineage IDs, draft ID and SKU require real non-empty strings;
- numeric identity coercion cannot create verified lineage;
- explicit persisted-preview error markers, when present, must be boolean;
- decision type, priority and confidence are canonical;
- reasons are a real non-empty list of non-empty strings;
- malformed durable history snapshots cannot be promoted to verification success;
- recorded-at binding requires a real string;
- matching malformed expected/history values do not become valid through coercive normalization;
- valid output remains read-only, non-executable and `externally_verified=False`;
- exact-SHA evidence: entering main #509, feature #516, PR merge-ref #517, squash-main #518;
- cancelled duplicate branch-creation Verify #514 remains cancelled evidence and is not used as green evidence;
- no Product Decision rule/threshold, persistence owner, Product Task Draft execution, Telegram production wiring, Action Executor connection or Ozon mutation changed;
- `data/users.json` untouched.


---

# Product Decision User Action Guidance Integrity v1

Boundary:

- `build_product_decision_user_action_guidance`
- verified Product Decision persistence lineage to seller manual-action guidance

Tests:

- `tests/test_product_decision_user_action_guidance.py`
- `tests/test_product_decision_user_action_guidance_integrity_v841_v850.py`

Проверяет:

- non-mapping verification input fails closed;
- verification/application IDs and SKU require real non-empty strings;
- explicit verifier `error=False`, verified status and decision-persistence verification are required;
- non-empty mismatch evidence cannot be presented as trusted guidance;
- external-verification and execution/persistence overclaims fail closed;
- verified recorded-at must match the durable snapshot timestamp;
- priority and confidence require canonical values;
- reasons cannot be synthesized from malformed strings;
- valid guidance carries read-only verified lineage and remains user-executed/non-automatic;
- exact-SHA evidence: entering main #528, feature #532, PR merge-ref #533, squash-main #534;
- no failed intermediate production SHA occurred in v841-v850;
- no Product Decision rule/threshold, persistence owner, Product Task Draft execution, Telegram production wiring, Action Executor connection or Ozon mutation changed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Checklist Integrity v1

Boundary:

- `build_product_decision_user_action_checklist`
- verified Product Decision seller guidance to manual user checklist

Tests:

- `tests/test_product_decision_user_action_checklist.py`
- `tests/test_product_decision_user_action_checklist_integrity_v851_v860.py`

Проверяет:

- non-mapping guidance input fails closed;
- guidance / verification / application IDs, SKU and verified-recorded-at require real non-empty strings;
- explicit guidance `error=False`, ready status and decision-persistence verification are required;
- verification ID remains bound to the persistence application ID;
- external-verification and persistence/execution overclaims fail closed;
- decision/action pairing, priority, confidence, title and reasons are canonical;
- manual checklist steps cannot be synthesized through `str(...)` coercion;
- valid checklist carries the verified persistence lineage forward and remains user-owned/non-executable;
- exact-SHA evidence: entering main #544, feature #548, PR merge-ref #549, squash-main #550;
- no failed intermediate production SHA occurred in v851-v860;
- no Product Decision rule/threshold, persistence owner, Product Task Draft execution, Telegram production wiring, Action Executor connection or Ozon mutation changed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Completion Evidence Integrity v1

Boundary:

- `build_product_decision_user_action_completion_evidence`
- verified Product Decision user checklist to explicit USER_REPORT completion evidence

Tests:

- `tests/test_product_decision_user_action_completion_evidence.py`
- `tests/test_product_decision_user_action_completion_evidence_integrity_v861_v870.py`

Проверяет:

- non-mapping checklist input fails closed;
- checklist / guidance / verification / application IDs, SKU, item ID and verified-recorded-at require real non-empty strings;
- exact guidance → verification → application lineage is retained;
- explicit checklist `error=False`, ready status and decision-persistence verification are required;
- non-string completion decisions are not coercively normalized;
- external-verification and persistence/execution overclaims fail closed;
- item count, completed count, positions, user ownership and instructions are structurally validated;
- valid completion evidence remains USER_REPORT, non-persistent before its dedicated persistence step and non-executable;
- exact-SHA evidence: entering main #560, feature #565, PR merge-ref #566, squash-main #567;
- no failed intermediate production SHA occurred in v861-v870;
- no Product Decision rule/threshold, persistence owner, Product Task Draft execution, Telegram production wiring, Action Executor connection or Ozon mutation changed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Completion Persistence Integrity v1

Boundary:

- `ProductDecisionUserActionCompletionPersistenceService`
- explicit USER_REPORT completion evidence to durable completion storage
- revision producer lineage propagation compatibility

Tests:

- `tests/test_product_decision_user_action_completion_persistence_service.py`
- `tests/test_product_decision_user_action_completion_persistence_integrity_v871_v880.py`
- `tests/test_product_decision_user_action_completion_revision.py`

Проверяет:

- non-mapping evidence fails closed;
- completion / checklist / guidance / verification / application lineage remains exact;
- source `error=False`, decision-persistence verification and USER_REPORT source are required;
- completion status/decision/user boolean consistency;
- canonical root and revision evidence ID lineage;
- malformed load result and malformed existing records fail closed;
- explicit `save(False)` cannot become durable success;
- root→revision persistence keeps verified lineage, item/instruction and revision metadata;
- exact-SHA evidence: entering main #577, feature #582, PR merge-ref #583, squash-main #584;
- no failed intermediate production SHA occurred in v871-v880;
- no Product Decision rule/threshold, persistence owner, Product Task Draft execution, Telegram production wiring, Action Executor connection or Ozon mutation changed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Completion Revision Predecessor Integrity v1

Boundary:

- `ProductDecisionUserActionCompletionPersistenceService`
- durable completion revision chain predecessor existence and lineage

Tests:

- `tests/test_product_decision_user_action_completion_predecessor_integrity_v881_v890.py`

Проверяет:

- revision 2+ cannot persist without an actually stored predecessor;
- duplicate predecessor IDs are ambiguous and fail closed;
- predecessor exact checklist/guidance/verification/application/SKU/item/instruction lineage;
- predecessor verified Product Decision and USER_REPORT safety semantics;
- predecessor status/decision/report consistency;
- canonical predecessor revision/root/previous-ID lineage for revision 3+;
- duplicate current revision IDs fail closed;
- valid root → revision 2 → revision 3 durable chain;
- exact-SHA evidence: entering main #594, feature #597, PR merge-ref #598, squash-main #599;
- no failed intermediate production SHA occurred in v881-v890;
- no runtime execution or Ozon mutation wiring changed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Checklist Status Persistence Lineage Integrity v1

Boundary:

- `build_product_decision_user_action_checklist_status`
- verified Product Decision checklist + persisted USER_REPORT completion receipts → aggregate seller checklist status

Tests:

- `tests/test_product_decision_user_action_checklist_status.py`
- `tests/test_product_decision_user_action_checklist_status_integrity_v891_v900.py`

Проверяет:

- non-mapping checklist and non-list report collection fail closed;
- exact checklist/guidance/verification/application/SKU/timestamp lineage;
- checklist success, verification, item shape and safety contract;
- matching persisted receipt success/source/persistence/safety contract;
- matching receipt item/instruction and verified lineage binding;
- exact integer completion revision without coercion;
- canonical root/evidence/previous revision IDs;
- duplicate item+revision ambiguity;
- contiguous revision chain from 1 through latest;
- malformed matching report cannot become no-report success;
- valid aggregate carries persisted-decision verification lineage and remains externally unverified/non-executable;
- exact-SHA evidence: entering main #610, feature #614, PR merge-ref #615, squash-main #616;
- no failed intermediate production SHA occurred in v891-v900;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Post-Decision Observation Lineage Integrity v1

Boundary:

- `build_product_decision_user_action_post_decision_observation`
- verified checklist-status → read-only later Product Decision observation

Tests:

- `tests/test_product_decision_user_action_post_decision_observation.py`
- `tests/test_product_decision_user_action_post_decision_observation_integrity_v811_v820.py`
- `tests/test_product_decision_user_action_post_decision_observation_integrity_v901_v910.py`

Проверяет:

- non-mapping checklist status and later-decision payloads fail closed;
- canonical checklist-status/checklist/guidance/verification/application/SKU/timestamp lineage;
- explicit persisted Product Decision verification;
- exact complete-report count and item-ID consistency;
- no numeric/coercive item identity;
- explicit later-decision success marker and canonical fields;
- matching SKU;
- safe read-only/non-causal/non-executable observation output;
- exact-SHA evidence: entering main #620, failed intermediate #623, final feature #624, PR merge-ref #625, squash-main #626;
- failed intermediate `0896d8112971966aec9fb61c7a2250436f19d76a` remains failed evidence at 1804 passed / 7 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Post-Decision Outcome Lineage Integrity v1

Boundary:

- `build_product_decision_user_action_post_decision_outcome`
- verified post-decision observation + prior Product Decision → non-causal outcome classification

Tests:

- `tests/test_product_decision_user_action_post_decision_outcome.py`
- `tests/test_product_decision_user_action_post_decision_outcome_integrity_v911_v920.py`

Проверяет:

- non-mapping observation/prior inputs fail closed;
- exact observation/checklist-status/checklist/guidance/verification/application/SKU/timestamp lineage;
- explicit observation success and persisted Product Decision verification;
- complete USER_REPORT count/item evidence;
- no identity/priority coercion;
- canonical prior/later Product Decision type, priority, confidence and reasons;
- exact prior SKU binding;
- rejection of noncanonical MEDIUM priority;
- support for canonical NONE priority;
- safe non-causal/non-executable outcome;
- exact-SHA evidence: entering main #630, feature #632, PR merge-ref #633, squash-main #634;
- no failed intermediate production SHA occurred in v911-v920;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Learning Summary Outcome Integrity v1

Boundary:

- `build_product_decision_user_action_learning_summary`
- verified post-decision outcome list → descriptive learning summary

Tests:

- `tests/test_product_decision_user_action_learning_summary.py`
- `tests/test_product_decision_user_action_learning_summary_integrity_v921_v930.py`

Проверяет:

- non-list input cannot become a clean empty summary;
- every row must be a mapping;
- exact v911-v920 outcome lineage and explicit success;
- persisted Product Decision verification and complete USER_REPORT evidence;
- unsafe outcomes fail closed instead of disappearing;
- canonical prior/later Product Decision classification;
- contradictory outcome classification;
- duplicate outcome-ID inflation protection;
- canonical NONE priority support and MEDIUM rejection;
- deterministic safe empty/non-empty summary semantics;
- exact-SHA evidence: entering main #638, failed intermediate #640, final feature #641, PR merge-ref #642, squash-main #643;
- failed intermediate `21051b20acdfc0036a15d875d01b488283791ff3` remains failed evidence at 1830 passed / 1 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision User Action Learning Evidence Quality Summary Integrity v1

Boundary:

- `build_product_decision_user_action_learning_evidence_quality`
- canonical learning summary → descriptive evidence-quality classification

Tests:

- `tests/test_product_decision_user_action_learning_evidence_quality.py`
- `tests/test_product_decision_user_action_learning_evidence_quality_integrity_v931_v940.py`

Проверяет:

- non-mapping/missing-success summary fails closed;
- exact integer observation/SKU counts without coercion;
- canonical outcome/priority/SKU aggregate maps;
- aggregate sum and SKU-count consistency;
- exact unique outcome-ID count;
- strict zero-evidence semantics;
- unchanged quality thresholds;
- safe externally-unverified/non-executable output;
- exact-SHA evidence: entering main #647, failed intermediate #649, final feature #650, PR merge-ref #651, squash-main #652;
- failed `849b0d0e78e441f3080631419ecbc0ea192890ec` remains failed evidence;
- `data/users.json` untouched.


---

# Product Decision User Action Learning Confidence Evidence Integrity v1

Boundary:

- `build_product_decision_user_action_learning_confidence`
- canonical evidence-quality result → descriptive confidence classification

Tests:

- `tests/test_product_decision_user_action_learning_confidence.py`
- `tests/test_product_decision_user_action_learning_confidence_integrity_v941_v950.py`

Проверяет:

- non-mapping/missing-success quality fails closed;
- exact integer observation/SKU counts without coercion;
- canonical quality name/score;
- quality/score/sample consistency;
- canonical outcome/priority/SKU aggregate maps;
- aggregate sum and SKU-count consistency;
- exact unique outcome-ID count;
- unchanged confidence thresholds;
- safe externally-unverified/non-executable output;
- exact-SHA evidence: entering main #656, feature #658, PR merge-ref #659, squash-main #660;
- no failed intermediate production SHA occurred in v941-v950;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Action Proposal Result Integrity v1

Boundary:

- `ProductBusinessDecisionQueryService._with_action_proposal`
- seller-facing Product Decision → action proposal → task-draft lifecycle / Telegram presentation

Tests:

- `tests/test_product_decision_action_proposal_result_integrity_v951_v960.py`

Проверяет:

- non-mapping proposal fails closed;
- proposal exceptions fail closed without exception detail leakage;
- missing boolean markers cannot become success;
- execution overclaim is blocked;
- exact SKU identity;
- exact proposal type ↔ Product Decision semantics;
- exact canonical reasons;
- confirmation/action-required consistency;
- assortment query fails closed on invalid nested proposal;
- valid proposal remains non-executable and Telegram-safe;
- exact-SHA evidence: entering main #664, feature #666, PR merge-ref #667, squash-main #668;
- no failed intermediate production SHA occurred in v951-v960;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision History Context Result Integrity v1

Boundary:

- `ProductBusinessDecisionQueryService._with_decision_history`
- `AssistantButtonHandlerService._with_latest_proposal_status`
- Product Decision → history interaction context → cache / draft lifecycle / Telegram

Tests:

- `tests/test_product_decision_history_context_integrity_v961_v970.py`

Проверяет:

- history record context cannot overwrite Product Decision identity;
- non-mapping history context is unknown, not clean success;
- required history booleans are exact;
- history count is exact integer or unknown, never coerced;
- history exceptions are sanitized;
- valid history context remains cacheable;
- invalid history context blocks task-draft lifecycle;
- Telegram skips latest reads for invalid history context;
- malformed/cross-SKU/unknown-status latest history cannot enter card;
- valid safe latest proposal status and task draft remain available;
- failed intermediate `bfcc3551166431288f38ba0c06912133bed56818`: Verify #674, 1870 passed / 1 failed;
- final feature `ab24a87c19072b5bbb3b9efd6b1630b513bf6645`: Verify #675, 1871 passed / 0 failed;
- PR #328 synthetic `85e808a3dcc04ef9197bc673950546445ee15749`: Verify #676, 1871 passed / 0 failed;
- squash main `10977368ac4179f1f7168943a38fcdbc01ecfd78`: Verify #677, 1871 passed / 0 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Unit Economics Returns Finance Impact Integrity v1

Boundary:

- `ProductUnitEconomicsQueryService._attach_returns_impact`
- `ProductUnitEconomicsQueryService._estimate_returns_impact`
- returns-finance evidence → unit economics confirmed/estimated returns adjustment

Tests:

- `tests/test_unit_economics_returns_impact_integrity_v971_v980.py`
- updated canonical cache fixture in `tests/test_product_unit_economics_query_cache.py`

Проверяет:

- non-mapping returns impact remains unknown;
- returns impact exceptions are sanitized;
- missing explicit error marker is invalid;
- string `complete="false"` cannot become truthy confirmed completeness;
- categories and required category records must be mappings;
- counts are exact integers and never string/missing coercions;
- observed count cannot exceed matched/event counts;
- complete finance requires complete finance/category state;
- invalid evidence does not create zero observed cost or confirmed profit;
- valid estimated and confirmed calculations remain unchanged;
- failed intermediate `b4f0d33d163ee0a81d0252e466519169c55fd1f2`: Verify #683, 1880 passed / 1 failed;
- final feature `0a2ece03b60e019b264b5ecda8a010bca873e7bb`: Verify #684, 1881 passed / 0 failed;
- PR #330 synthetic `d8e9c3f5fb978cb4ae2d3675d229ad6bbc48b358`: Verify #685, 1881 passed / 0 failed;
- squash main `db5ab92503f499dfe470402ffefc00b15b9c6e59`: Verify #686, 1881 passed / 0 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Result Integrity v1

Boundary:

- `ProductBusinessDecisionQueryService._query_product`
- Product Decision service output → history / proposal / cache / task-draft lifecycle / Telegram

Tests:

- `tests/test_product_decision_result_integrity_v981_v990.py`
- canonicalized legacy fixture in `tests/test_product_decision_freshness_evidence_propagation.py`

Проверяет:

- non-mapping decision result fails closed;
- decision exceptions are sanitized;
- injected error/code fields are rejected;
- exact SKU/product identity;
- exact decision type → priority contract;
- canonical unique reason list;
- canonical unique missing-data list;
- invalid decision has no history/proposal/cache side effects;
- valid decision remains seller-safe and non-executable;
- Telegram invalid-decision response has no keyboard;
- cancelled intermediate #693/#694 have no transferable verification claim;
- failed intermediate `8a286947bdc5862834a05794e330d87ef370ffe7`: Verify #695, 1889 passed / 2 failed;
- final feature `8b90c11763622cc413802a488171738cf2332a1a`: Verify #696, 1891 passed / 0 failed;
- PR #332 synthetic `da5e7689cc87a0597944f371dfe4246082d92806`: Verify #697, 1891 passed / 0 failed;
- squash main `5f0534bb72dba2471c3c339a69cd7041552dfb4a`: Verify #698, 1891 passed / 0 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Assortment Overview Integrity v1

Boundary:

- `AssistantButtonHandlerService._validate_product_decisions_overview`
- Product Decision assortment overview → counts / proposal statistics / pagination / Telegram keyboard

Tests:

- `tests/test_product_decision_assortment_overview_integrity_v991_v1000.py`
- canonicalized legacy overview fakes in Product Decision Telegram/learning tests

Проверяет:

- exact decision-count recomputation;
- exact positive integer count semantics;
- unknown count-key rejection;
- duplicate SKU rejection;
- canonical decision type → priority pairing;
- exact proposal-count recomputation;
- exact actionable proposal count;
- nested proposal safety and known proposal types;
- valid mixed overview preserves seller statistics;
- validator is deterministic and non-mutating;
- failed intermediates #704/#705/#706 remain failed evidence;
- final feature `63870a305972f7b7e8f33cad251fc6f13235d1fc`: Verify #707, 1901 passed / 0 failed;
- PR #334 synthetic `1bbee7e03477b197a474a6807093d6ee344b7505`: Verify #708, 1901 passed / 0 failed;
- squash main `84d714909d5082958bf2bb21a30b7b097eb17955`: Verify #709, 1901 passed / 0 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Task Draft Lifecycle Result Integrity v1

Boundary:

- `ProductBusinessDecisionQueryService._with_task_draft_lifecycle`
- Product Task Draft reconcile result → cached/seller-facing Product Decision / assortment result

Tests:

- `tests/test_product_decision_task_draft_lifecycle_result_integrity_v1001_v1010.py`
- canonicalized lifecycle fake in `tests/test_product_business_decision_query_service.py`

Проверяет:

- non-mapping lifecycle result fails closed;
- missing or true error marker is not success;
- execution overclaim is rejected;
- stale count/list shape and cardinality are exact;
- cross-SKU stale drafts are rejected;
- current revision cannot be classified as stale;
- stale status/proposal type are canonical;
- stale drafts remain non-executable;
- reconcile exceptions are sanitized;
- invalid lifecycle state is not cached;
- assortment query propagates lifecycle integrity failure;
- valid lifecycle is copied defensively;
- final feature `12e4f1d4f38296b8f46680302478f377121644a8`: Verify #715, 1911 passed / 0 failed;
- PR #336 synthetic `005ac13b1fbb01bb6e95314d1f8c89b994ba85c6`: Verify #716, 1911 passed / 0 failed;
- squash main `288c6452703eee4082414d1ad36680b4ddf02caa`: Verify #717, 1911 passed / 0 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Unit Economics Result Integrity v1

Boundary:

- `ProductBusinessDecisionQueryService._query_product`
- `ProductBusinessDecisionQueryService._valid_unit_economics_result`
- Product Unit Economics result → Product Decision finance facts

Tests:

- `tests/test_product_decision_unit_economics_result_integrity_v1011_v1020.py`
- aligned canonical fixtures in Product Decision and freshness propagation tests

Проверяет:

- non-mapping/missing/non-boolean result markers fail closed;
- downstream exceptions are sanitized;
- explicit downstream errors remain unknown, not zero;
- unavailable economics cannot claim profit/margin;
- missing-field shape and uniqueness are enforced;
- NaN/infinity/bool finance values are rejected;
- confirmed returns-adjusted profit requires complete evidence;
- estimated returns profit requires exact readiness and evidence;
- invalid results are not cached;
- valid producer result still drives decisions;
- failed `c27b1fbfba804d36167855228f1881c08c4ef506`: Verify #723, 1917 passed / 4 failed;
- failed `1114863bdc5b23969fe8cf2d3c9166fe5e7cd523`: Verify #724, 1918 passed / 3 failed;
- final feature `fa9cd0e874347ba00320c8e9c36c85d0efb530a0`: Verify #725, 1921 passed / 0 failed;
- PR #338 synthetic `8014a74ae903863da672ee4b82f9fb565ad3d6cc`: Verify #726, 1921 passed / 0 failed;
- squash main `982dc4f58fec6172a4fa99475ae72800c107981f`: Verify #727, 1921 passed / 0 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Operational Metrics Result Integrity v1

Boundary:

- `ProductBusinessDecisionQueryService._query_operational_metrics_source`
- `ProductBusinessDecisionQueryService._valid_operational_metrics_result`
- Sales/Stock operational metrics → Product Decision business facts

Tests:

- `tests/test_product_decision_operational_metrics_result_integrity_v1021_v1030.py`
- existing freshness propagation tests validate the supported `stock_priority` alias contract

Проверяет:

- sales/stock source exceptions are sanitized;
- non-mapping source results fail closed;
- non-boolean explicit error marker is rejected;
- explicit error=True remains unknown rather than zero;
- unsafe sales velocity is rejected;
- noncanonical sales trend is rejected;
- unsafe stock quantity/days values are rejected;
- stock priority/day relationship is canonical;
- `priority` and `stock_priority` aliases cannot contradict;
- malformed missing-data/evidence fields are rejected;
- invalid metrics are not cached;
- valid path still produces a Product Decision;
- failed `678739dea2fa85af3f71933f048f9bfb193fdc62`: Verify #733, 1929 passed / 2 failed;
- final feature `6af041c39b86791821249058d0632070f2f68685`: Verify #734, 1931 passed / 0 failed;
- PR #340 synthetic `7e64fcd23df9fb405c8c422359e3703b6a720f56`: Verify #735, 1931 passed / 0 failed;
- squash main `70466d338951b2b7cc2bb7c48a9d2c7ee2dc91df`: Verify #736, 1931 passed / 0 failed;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Persistence Commit Receipt Integrity v1

Boundaries:

- `ProductDecisionHistoryService.record`
- `ProductDecisionHistoryService.record_persistent`
- `ProductDecisionPersistenceApplicationService.apply`
- `ProductDecisionPersistenceVerificationService.verify`

Tests:

- `tests/test_product_decision_persistence_commit_receipt_v1031_v1040.py`
- canonicalized persistence application/verification fixtures

Проверяет:

- storage save=False cannot become successful history;
- storage save state UNKNOWN cannot become successful history;
- failed history writes do not remain in in-memory state;
- durable persistence requires storage, not in-memory history;
- COMMITTED receipt carries exact SKU/recorded_at/count/context;
- application refuses missing receipt capability;
- rejected/unknown durable writes never claim product_decision_persisted;
- application carries defensive committed receipt;
- verification requires committed receipt before readback;
- valid receipt + readback verifies without execution;
- failed `14a0709209228310625dd91871e963a866ab6cc9`: Verify #742, 1940 passed / 1 failed;
- final feature `88372919c9275a51482703e59fe21d8c4d9c5682`: Verify #743, 1941 passed / 0 failed;
- PR #342 synthetic `7e54ca702706ad192eb70da63e351e96efdb31b5`: Verify #744, 1941 passed / 0 failed;
- squash main `7d53fecac126973122270eacfdfc122e50ae3de3`: Verify #745, 1941 passed / 0 failed;
- Telegram persistence wiring remains disabled;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Durable Application Lineage v1

Boundaries:

- `ProductDecisionPersistenceApplicationService.apply`
- `ProductDecisionHistoryService.record_persistent`
- `ProductDecisionHistoryService._snapshot`
- `ProductDecisionPersistenceVerificationService.verify`
- existing `ProductDecisionHistoryStorageService`

Tests:

- `tests/test_product_decision_durable_application_lineage_v1041_v1050.py`
- canonicalized persistence application/verification fixtures

Проверяет:

- exact application lineage is constructed before durable write;
- lineage binds application/readiness/authorization/eligibility/review/delta/preview IDs, draft_id and SKU;
- malformed lineage is rejected before save;
- cross-SKU lineage is rejected before save;
- durable snapshot and COMMITTED receipt carry the same lineage;
- forged receipt lineage blocks persistence application;
- forged receipt lineage blocks verification before readback;
- forged durable snapshot lineage blocks verification;
- JSON storage restart preserves lineage;
- feedback mutation preserves lineage;
- restart readback verifies without execution;
- failed `cfeb3528d5f902625819b6897db192bf794fddda`: Verify #751, 1915 passed / 36 failed;
- final feature `5e856591925d2288db871ac9632eab5ee7f7a649`: Verify #752, 1951 passed / 0 failed;
- PR #344 synthetic `13f8cb191c24eb0589cf4f5ba892d7b13b402bc5`: Verify #753, 1951 passed / 0 failed;
- squash main `19851b9d40827b3ca5e3889c3858ca32c5602f67`: Verify #754, 1951 passed / 0 failed;
- Telegram remains read-only and not persistence-wired;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Read-Only Persistence Verification v1

Boundaries:

- `ProductDecisionHistoryStorageService.read_durable`
- `ProductDecisionHistoryService.latest_persistent`
- `ProductDecisionPersistenceVerificationService.verify_latest`

Tests:

- `tests/test_product_decision_readonly_persistence_verification_v1051_v1060.py`

Проверяет:

- durable read receipt is explicit;
- corrupted JSON is invalid, not empty history;
- non-list/mixed durable data fails closed;
- latest_persistent reads durable storage rather than memory;
- in-memory history cannot verify persistence;
- malformed durable read receipt fails closed;
- missing/cross-SKU/broken application lineage fails closed;
- valid restart produces canonical verified persistence payload;
- verify_latest is read-only and does not mutate file or in-memory state;
- final feature `c0da07cbafeb1fe38001729eebca94648149d96b`: Verify #760, 1961 passed / 0 failed;
- PR #346 synthetic `0ccae174a2adfe5c650ca96bf7dcf90ceafaec80`: Verify #761, 1961 passed / 0 failed;
- squash main `b0bfdd5dd79349244ceaf64d1d4df9899211344a`: Verify #762, 1961 passed / 0 failed;
- no persistence application side effect;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Telegram Verified Product Decision Guidance / Checklist Wiring v1

Boundaries:

- `telegram_assistant_factory.create_telegram_assistant`
- `AssistantButtonHandlerService._show_product_decision`
- `AssistantButtonHandlerService._with_verified_product_decision_user_action`
- `ProductDecisionPersistenceVerificationService.verify_latest`
- existing Product Decision guidance/checklist builders

Tests:

- `tests/test_product_decision_verified_guidance_telegram_wiring_v1061_v1070.py`
- existing Product Decision Telegram UI/result-integrity tests

Проверяет:

- missing verified dependencies preserve the existing decision card;
- blocked or malformed durable verification never becomes verified UI;
- verified snapshot must match the current decision by SKU, recorded_at, decision_type, priority, confidence and reasons;
- malformed guidance prevents checklist presentation;
- malformed checklist prevents verified presentation;
- unsafe guidance flags cannot reach verified UI;
- verifier exceptions are contained without secret leakage;
- valid durable verification produces a seller-facing manual checklist;
- automatic execution remains explicitly prohibited;
- Telegram factory shares the exact Product Decision History owner with the read-only verifier;
- failed `f449e7d738b56fb72f39e0836eb2ea3464b899a9`: Verify #768, 1970 passed / 1 failed;
- final feature `09abed3a9db1c1cf90a13d4393bb3771f09c964d`: Verify #769, 1971 passed / 0 failed;
- PR #348 synthetic `400bbfa95038edd3876a2ea0eb4b2e28db65fefb`: Verify #770, 1971 passed / 0 failed;
- squash main `dbec4ecfc5f38b31aeba5e86a6d0ad09c40d58bb`: Verify #771, 1971 passed / 0 failed;
- no persistence application side effect;
- no execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Product Decision Telegram Query Exception Containment v1

Boundaries:

- `AssistantButtonHandlerService._open_product_decisions_menu`
- `AssistantButtonHandlerService._show_product_decision`
- `AssistantTelegramAdapter.handle_button`

Tests:

- `tests/test_product_decision_telegram_query_exception_containment_v1071_v1080.py`
- existing Product Decision Telegram result-integrity tests
- existing Telegram adapter runtime exception-containment tests

Проверяет:

- overview RuntimeError is contained locally and does not leak exception text;
- overview TypeError is not retried;
- detail RuntimeError is contained locally and does not leak exception text;
- detail TypeError is not retried;
- local domain failure reaches Telegram adapter unchanged;
- generic `TELEGRAM_BUTTON_DISPATCH_FAILED` is not substituted for contained Product Decision query failure;
- explicit overview failure semantics remain unchanged;
- valid overview behavior remains unchanged;
- explicit detail failure semantics remain unchanged;
- valid detail behavior remains unchanged with defensive copy;
- failed `31902d6e4f1302a5fe221e091b54bd5e2c4a8f3d`: Verify #777, 1980 passed / 1 failed;
- final feature `30da677a1db0fdca3cd4ac2b0928859e0b9b81a8`: Verify #778, 1981 passed / 0 failed;
- PR #350 synthetic `a0bbb0059c67c3d4e0583f2b13883f5dd3f8857e`: Verify #779, 1981 passed / 0 failed;
- squash main `41473566a558bb09899f64d581010b72e4053fbd`: Verify #780, 1981 passed / 0 failed;
- no retry, persistence mutation, execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Financial Telegram Query Exception Containment v1

Boundaries:

- `AssistantButtonHandlerService._open_unit_economics_menu`
- `AssistantButtonHandlerService._show_unit_economics`
- `AssistantButtonHandlerService._open_returns_finance_impact_menu`
- `AssistantButtonHandlerService._show_returns_finance_impact`
- `AssistantTelegramAdapter.handle_button`

Tests:

- `tests/test_financial_telegram_query_exception_containment_v1081_v1090.py`
- existing financial Telegram result-integrity/UI tests

Проверяет:

- Unit Economics product source exceptions fail closed without secret leakage;
- Returns Finance Impact product source exceptions fail closed;
- Unit Economics query exceptions are one-shot and skip formatting;
- Returns Finance Impact query exceptions are one-shot;
- Unit Economics formatter exceptions are contained locally;
- TypeError does not trigger retry;
- domain financial failure reaches Telegram adapter unchanged;
- valid Unit Economics menu/detail remains compatible;
- valid Returns Finance Impact menu/detail remains compatible;
- final feature `6cf579771939ceb765a996fa761a406175e003d3`: Verify #786, 1991 passed / 0 failed;
- PR #352 synthetic `69383b1fcfe87aab31dfb6bb29cd4f73bf051e13`: Verify #787, 1991 passed / 0 failed;
- squash main `0f484141713f2452f451e818caf600d113df6ad4`: Verify #788, 1991 passed / 0 failed;
- finance formulas unchanged;
- no retry, persistence mutation, execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Tax Configuration Persistence & Result Integrity v1

Boundaries:

- `TaxConfigurationService.get_policy`
- `TaxConfigurationService.save_policy`
- `TaxConfigurationService._validate_policy`
- production `telegram_core_factory.create_telegram_core`

Tests:

- `tests/test_tax_configuration_persistence_result_integrity_v1091_v1100.py`
- existing `tests/test_tax_configuration_foundation.py`

Проверяет:

- non-mapping persisted root fails closed as unconfigured;
- non-numeric persisted tax rate fails closed;
- NaN and positive/negative infinity fail closed;
- negative, >100% and boolean tax rates are rejected before write;
- invalid minimum-tax rates are rejected before write;
- NONE preserves explicit zero-tax normalization;
- valid policy is normalized and atomically persisted;
- failed atomic replace preserves the previous durable policy and cleans the temp file;
- truncated JSON becomes unconfigured instead of a startup exception;
- production factory starts with malformed tax config while keeping tax unknown;
- final feature `8cc003f6fa66eb499c67d7d3d74f90c0c75abecf`: Verify #794, 2001 passed / 0 failed;
- PR #354 synthetic `5167b644bc53edc27a40c7b15c7068e0c669d2fc`: Verify #795, 2001 passed / 0 failed;
- squash main `38e54ddc6d289f0f75121cc63efa0268ef2784f8`: Verify #796, 2001 passed / 0 failed;
- TaxService formulas unchanged;
- no execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Tax Calculation Input & Result Integrity v1

Boundaries:

- `TaxService.calculate`
- `TaxService._normalize_amount`
- `TaxService._normalize_rate`
- `ProductUnitEconomicsProvider._calculate_tax`

Tests:

- `tests/test_tax_calculation_input_result_integrity_v1101_v1110.py`
- existing tax configuration/unit-economics tests

Проверяет:

- missing tax mode preserves the explicit unconfigured result;
- unsupported tax mode is rejected before numeric conversion;
- non-numeric revenue/gross-profit inputs fail closed;
- NaN/inf revenue/gross-profit inputs fail closed;
- boolean amounts are not accepted as numeric tax inputs;
- invalid USN_INCOME tax rates fail closed;
- invalid minimum-tax rates fail closed;
- overflow/non-finite tax result never returns NaN/inf;
- numeric-string compatibility and valid formula outputs remain unchanged;
- negative revenue/profit continue to clip tax base to zero;
- Unit Economics maps invalid TaxService result to unknown tax rather than fabricated profit;
- final feature `85fc4b76baa725cbc586ca39e8454e30a70fb168`: Verify #802, 2011 passed / 0 failed;
- PR #356 synthetic `7d070c91d97e811491849475ddcd65552eadd1c7`: Verify #803, 2011 passed / 0 failed;
- squash main `1bc8cfc745a94c7bfe3442bf2c774947f79bce8b`: Verify #804, 2011 passed / 0 failed;
- no persistence mutation, execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Advertising & Expense Finite Result Integrity v1

Boundaries:

- `AdvertisingService.calculate`
- `AdvertisingService.total`
- `ExpenseService.calculate`
- `ExpenseService.calculate_single`
- `BusinessAnalyticsService.calculate`

Tests:

- `tests/test_advertising_expense_finite_result_integrity_v1111_v1120.py`
- existing unknown-advertising financial evidence tests

Проверяет:

- advertising NaN/inf inputs fail closed;
- advertising boolean inputs fail closed;
- negative advertising preserves existing explicit error;
- campaign aggregation ignores invalid rows but stays finite;
- campaign aggregate overflow fails closed;
- expense aggregation ignores invalid rows but stays finite;
- expense aggregate overflow fails closed;
- single expense rejects boolean and NaN/inf inputs;
- valid numeric-string financial inputs remain compatible;
- Business Analytics does not emit business profit after invalid advertising or expense overflow;
- final feature `c45284c99d70a45b1bed2b5f62049a7bb5c40df6`: Verify #810, 2021 passed / 0 failed;
- PR #358 synthetic `8b8bcfda3b61518637637a05b1b60109a7907192`: Verify #811, 2021 passed / 0 failed;
- squash main `cb0148a1d6ad14b2e53f18ca948b66e8422da3c4`: Verify #812, 2021 passed / 0 failed;
- finance formulas unchanged;
- no persistence mutation, execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Store Profit Aggregation Result Integrity v1

Boundaries:

- `StoreProfitService.calculate`
- `StoreProfitService._count`
- `StoreProfitService._number`
- `BusinessAnalyticsService.calculate`
- `SalesIntelligenceService.analyze`
- `AssistantSalesExecutorService.execute`

Tests:

- `tests/test_store_profit_aggregation_result_integrity_v1121_v1130.py`

Проверяет:

- non-list/tuple store-profit input fails closed;
- non-mapping product-profit rows fail closed;
- sales_count rejects bool, negative, fractional, non-numeric and non-finite values;
- financial aggregate fields reject bool, non-numeric and NaN/inf values;
- aggregate overflow and non-finite margin fail closed;
- failed product rows remain skipped;
- missing numeric fields retain zero defaults;
- valid numeric strings and loss classification remain compatible;
- BusinessAnalytics stops before tax/advertising/expense calculations on store-profit failure;
- Sales Intelligence and sales executor preserve that failure end-to-end;
- final feature `a888d3c4aa35aaba7526df186bfdbdd2902f9369`: Verify #818, 2031 passed / 0 failed;
- PR #360 synthetic `decce34f5a0cf348a4f9ab1ab80c50179d5e9d2b`: Verify #819, 2031 passed / 0 failed;
- squash main `87c95cf2eb139cd8782d8df79d43b2313939bba0`: Verify #820, 2031 passed / 0 failed;
- aggregation formulas unchanged;
- no persistence mutation, execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Business Profit Calculation Result Integrity v1

Boundaries:

- `BusinessProfitService.calculate`
- numeric/cost/result validation helpers
- `BusinessAnalyticsService.calculate`
- `SalesIntelligenceService.analyze`
- `AssistantSalesExecutorService.execute`

Tests:

- `tests/test_business_profit_calculation_result_integrity_v1131_v1140.py`

Проверяет:

- malformed store-profit/tax structures and markers fail closed;
- gross-sales/gross-profit are finite non-boolean numbers;
- advertising/other-expense costs are finite and non-negative;
- tax amount is finite and non-negative;
- unknown tax remains unknown;
- existing tax error message contract remains compatible;
- business-profit/margin overflow fails closed;
- numeric-string/formula compatibility remains;
- new integrity failures propagate to the sales executor;
- final feature `98edb5b5500c25e53b77237016afe3a223360ab8`: Verify #826, 2041 passed / 0 failed;
- PR #362 synthetic `6e335e508c07903d6e4488f1aac40d28a9e4152f`: Verify #827, 2041 passed / 0 failed;
- squash main `189455bb5b44c47bbf5abf188d1b456dad14b1ba`: Verify #828, 2041 passed / 0 failed;
- formulas unchanged;
- no persistence mutation, execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.


---

# Finance Period Aggregation Result Integrity v1

Boundaries:

- `FinanceAnalyticsService.get_period_finance`
- `FinanceAnalyticsService._normalize_daily`
- finance count/number validation helpers
- period failed-day and aggregate-failure helpers
- `StoreAnalyticsService.analyze_finance`

Tests:

- `tests/test_finance_period_aggregation_result_integrity_v1141_v1150.py`

Проверяет:

- daily source exceptions are contained and sanitized as failed-day evidence;
- non-mapping daily results fail closed;
- malformed explicit error markers fail the day;
- operations/sales_count reject bool, negative, fractional, non-numeric and NaN/inf values;
- amount fields reject bool, non-numeric and NaN/inf values;
- malformed/non-finite fee breakdown fails the whole day;
- invalid days cannot partially commit period totals;
- valid partial-period behavior remains compatible;
- amount and fee-breakdown aggregate overflow fails closed;
- valid numeric strings and signed fees remain compatible;
- StoreAnalytics finance path preserves contained source failure;
- failed intermediate `f54132ebf109240242a87037a81b1db5ed052d5b`: Verify #834, 2050 passed / 1 failed; test-only false positive remains failed evidence;
- final feature `52661a7c37068759d20797644943a3b9e5e5ebcc`: Verify #835, 2051 passed / 0 failed;
- PR #364 synthetic `ef001cc855661041bd3987604496d03e55acaf30`: Verify #836, 2051 passed / 0 failed;
- squash main `d1655adf6719e6000f996b4635253c6b99193ba3`: Verify #837, 2051 passed / 0 failed;
- finance formulas and partial-period semantics unchanged;
- no persistence mutation, execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.

---

# Period Profit Summary Input & Result Integrity v1

Boundaries:

- `PeriodProfitSummaryService.calculate`
- `PeriodProfitSummaryService._calculate_product`
- finance count/amount/fee normalization helpers
- cost resolution and tax-rate validation
- product/day/period aggregate finiteness
- `PeriodProfitQueryService.query`
- `AssistantPeriodProfitRuntimeService.handle_text`

Tests:

- `tests/test_period_profit_summary_input_result_integrity_v1151_v1160.py`

Проверяет:

- daily finance source exceptions are contained and sanitized;
- non-mapping finance results and malformed error markers fail closed;
- sales_count rejects bool, negative, fractional, non-numeric and NaN/inf values;
- finance amount fields reject bool, non-numeric and NaN/inf values;
- fee_breakdown requires finite numeric values;
- direct/stored cost inputs reject bool, negative, malformed and non-finite values;
- cost-source exceptions are contained;
- malformed/non-finite/negative tax rates fail closed without constructor exception;
- amount and fee aggregate overflow fails closed;
- valid numeric strings and signed fees remain compatible;
- existing period-profit formula remains unchanged;
- query/runtime preserve the integrity failure end-to-end;
- final feature `4ab53fe054504c633fbcd6fb708ccb7dc557eaa4`: Verify #847, 2061 passed / 0 failed;
- PR #367 synthetic `a9030acff2031b118c0c0600c008804c3d6ff08a`: Verify #848, 2061 passed / 0 failed;
- squash main `0ca4d226f3f75e2b20035a87a13b1a10d6c71581`: Verify #849, 2061 passed / 0 failed;
- no failed production SHA occurred in v1151-v1160;
- no persistence mutation, execution or Ozon mutation;
- `data/users.json` untouched;
- `externally_verified=False`.

---

# Telegram Period Profit Analyst Wiring v1

Boundaries:

- `telegram_core_factory.create_telegram_core`
- `telegram_assistant_factory.create_telegram_assistant`
- `AssistantKeyboardService.build_main_keyboard`
- `AssistantKeyboardService.build_period_profit_keyboard`
- `AssistantButtonHandlerService.handle`
- `AssistantButtonHandlerService._open_period_profit_menu`
- `AssistantButtonHandlerService._show_period_profit`
- `TelegramResponseFormatter.format`
- `AssistantPeriodProfitRuntimeService.handle_text`
- `AssistantPeriodProfitRuntimeService.handle_callback`

Tests:

- `tests/test_telegram_period_profit_analyst_wiring_v1161_v1170.py`
- compatibility update in `tests/test_product_unit_economics_telegram_ui.py`

Проверяет:

- main Telegram menu exposes period-profit analytics;
- period menu normalizes safe Today / 7 / 28 / 56 / 90-day callbacks;
- menu remains read-only and non-executing;
- callbacks delegate only to the period-profit read-only runtime;
- runtime exceptions are contained;
- malformed callback results fail closed;
- execution-adjacent success payloads fail closed;
- analytical `text` renders as Telegram text;
- Telegram core wires the production period-profit runtime/query;
- natural-language period-profit requests bypass the general action/execution flow;
- existing partial-core fixtures remain backward compatible;
- no Ozon mutation path is introduced;
- `data/users.json` untouched by this package;
- `externally_verified=False`.

Verification:

- failed intermediate `e7fce70c39f976e97bf78687621ace5125f9d30a`: Verify #866, 2069 passed / 2 failed;
- final feature `9c5d14f0220e5f13ee0a7d834855f7e07db58cab`: Verify #868, 2071 passed / 0 failed;
- PR #369 synthetic `04b20cc49a253bfb357626cf62a71b779a75112e`: Verify #869, 2071 passed / 0 failed;
- squash main `d06a5f8cc23814e3177f58f6182bef6fbceb0697`: Verify #870, 2071 passed / 0 failed.

---

# Telegram Custom Period Date Input v1

Boundaries:

- `AssistantPeriodProfitRuntimeService.handle_text`
- `AssistantPeriodProfitRuntimeService._extract_custom_dates`
- `AssistantPeriodProfitRuntimeService._invalid_custom_period`
- `AssistantEntryService.handle`

Tests:

- `tests/test_telegram_custom_period_date_input_v1171_v1180.py`

Проверяет:

- `ДД.ММ.ГГГГ - ДД.ММ.ГГГГ` routes as normalized ISO dates;
- en dash and em dash separators;
- single-digit day/month input;
- existing ISO custom-period compatibility;
- mixed supported date formats normalize consistently;
- invalid calendar dates fail closed without query;
- incomplete custom date input fails closed;
- seller-facing missing-period prompt includes localized example;
- localized custom Period Profit bypasses general execution flow;
- all successful downstream Period Profit results remain read-only/non-executing;
- no Ozon mutation or finance formula changes.

Verification:

- feature `62b040e392514bc410b34d82eccb8e0385b9c548`: Verify #884, 2081 passed / 0 failed;
- PR #371 synthetic `b865b551289ba4592d8d32594323ea8a6dc64c61`: Verify #885, 2081 passed / 0 failed;
- squash main `05f94da42e21c5ad5f7d78cb7f55bb2d40730f77`: Verify #886, 2081 passed / 0 failed;
- `externally_verified=False`.

---

# Tax Policy Production Availability v1

Boundaries:

- `TaxConfigurationService.get_policy`
- `TaxConfigurationService._get_environment_policy`
- `TaxConfigurationService._validate_policy`
- repository `data/tax_configuration.json`
- `telegram_core_factory.create_telegram_core`
- `ProductUnitEconomicsProvider.build_current`

Tests:

- `tests/test_tax_policy_production_availability_v1181_v1190.py`

Проверяет:

- repository production policy is explicit USN Income 6%;
- explicit env policy is used only when persisted file is absent;
- missing file + missing env remains unconfigured;
- invalid env policy fails closed;
- explicit NONE env is a real configured zero-tax policy;
- persisted policy wins over env;
- malformed persisted policy does not silently fall back;
- production Telegram core receives repository tax policy;
- hook-2-like current economics calculates 6.00 ₽ tax;
- hook-2-like base unit profit is 35.83 ₽ before return-risk adjustment;
- unconfigured tax still blocks profit instead of assuming zero;
- no Ozon mutation or execution changes.

Verification:

- feature `1d0df2799fb87b57d916843a96a080389e2ac07b`: Verify #900, 2091 passed / 0 failed;
- PR #373 synthetic `a6493407f0bb915f366573404fcffd220e6757a1`: Verify #901, 2091 passed / 0 failed;
- squash main `9c9d379e36edf2123a466ad2b3cd1d000d81bae3`: Verify #902, 2091 passed / 0 failed;
- `externally_verified=False`.

---

# Period Profit Returns Protobuf Timestamp Compatibility v1

Boundaries:

- `OzonClient.get_returns`
- `OzonClient._returns_timestamp`
- `PeriodProfitReturnEvidenceService.load`
- `PeriodProfitQueryService.query`

Tests:

- `tests/test_period_profit_returns_timestamp_v1191_v1200.py`

Проверяет:

- date-only start/end normalize to RFC3339 protobuf timestamps;
- full RFC3339/offset timestamps remain unchanged;
- Returns filter/pagination/timeout contract remains unchanged;
- custom and preset Period Profit ranges use valid timestamps;
- return evidence remains read-only/non-financial;
- no Ozon mutation or execution changes.

Verification:

- feature `9e2c5b27a1df9f32c8e950766abc809ba93f7976`: Verify #918, 2101 passed / 0 failed;
- PR #375 synthetic `86bc4a07477e910fcaf56a1a1b908fa28a4a68f5`: Verify #919, 2101 passed / 0 failed;
- squash main `c1c3da7cb69d6ce2af550e57bc6c5e38a0bb8a89`: Verify #920, 2101 passed / 0 failed;
- `externally_verified=False`.

---

# Period Profit Data Completeness Integrity v1

Boundaries:

- `PeriodProfitSummaryService.calculate`
- `PeriodProfitSummaryService._normalize_product`
- `PeriodProfitReturnEvidenceService.load`
- `PeriodProfitReturnEvidenceService._has_next`
- `PeriodProfitReturnEvidenceService._next_id`
- `build_period_profit_response`

Tests:

- `tests/test_period_profit_data_completeness_v1201_v1210.py`

Проверяет:

- persisted SQLite tuple `(id, offer_id, sku)` is normalized and included in Period Profit;
- empty/malformed product sets fail closed instead of returning 0.00 ₽ success;
- existing dict product contract remains compatible;
- Returns evidence paginates past the first 500 records;
- `last_id` advances across pages;
- bounded pagination marks capped results incomplete;
- later-page failures preserve partial evidence without claiming exact totals;
- incomplete return counts are presented as `как минимум N`;
- exact return counts retain existing presentation;
- legacy READY response fixtures remain compatible;
- no finance formula, return-cost inference, execution or Ozon mutation changes.

Verification:

- failed `e3d8b2ed1600e3759135bda4f62865ba38a43ae9`: Verify #935, 2103 passed / 2 failed;
- failed `49c02ae1790b7d395794932e7ac4fa95cbac1644`: Verify #936, 2109 passed / 2 failed;
- final feature `16c53622612b72bce2aa43fd97d5ff66d47466c3`: Verify #937, 2111 passed / 0 failed;
- PR #377 synthetic `f1593267f67339f2dd68d235056cdbc69960160a`: Verify #938, 2111 passed / 0 failed;
- squash main `7b2b570278c9cc71f3eb6dbb23b5554d41de07f7`: Verify #939, 2111 passed / 0 failed;
- `externally_verified=False`.

---

# Period Profit Tax Rate Unit Integrity v1

Boundaries:

- `period_profit_factory._period_profit_tax_fraction`
- `period_profit_factory.create_period_profit_query`
- `PeriodProfitSummaryService._tax_fraction`
- production TaxConfigurationService policy

Tests:

- `tests/test_period_profit_tax_rate_unit_v1211_v1220.py`
- updated `tests/test_period_profit_factory.py`

Проверяет:

- USN Income 6.0 percent converts to 0.06 fraction;
- NONE converts to 0.0;
- unconfigured/invalid/non-finite tax policy fails closed;
- unsupported USN Income Minus Expenses fails closed;
- summary rejects percent-scale multiplier 6.0;
- summary accepts 0.06 as six percent;
- live seller sample produces tax 80 902.27 ₽, profit 310 701.55 ₽, margin 23.04%;
- production factory reads repository tax policy and exposes 0.06 to summary;
- Period Profit tax path remains read-only.

Verification:

- failed `a7d5cead4c7c49907d6d045b54a3cec30d48efad`: Verify #953, 2110 passed / 1 failed;
- failed `ee463cd1000113998ae5b895da02334bb5a5f495`: Verify #954, 2120 passed / 1 failed;
- final feature `4c50429bc4c2f6515d80b497b85fe8c9663e24eb`: Verify #955, 2121 passed / 0 failed;
- PR #379 synthetic `68c0f7360dd93738377f7111f5f4732d0b4d48af`: Verify #956, 2121 passed / 0 failed;
- squash main `2f438bd6bb739938cee4fe56b83af8f4a563f942`: Verify #957, 2121 passed / 0 failed;
- `externally_verified=False`.

---

# Period Profit Revenue Share Presentation v1

Boundaries:

- `build_period_profit_response`
- `_money_with_revenue_share`

Tests:

- `tests/test_period_profit_revenue_share_presentation_v1221_v1230.py`

Проверяет:

- revenue displays 100.00%;
- net Ozon accrual displays revenue share;
- commission/logistics/acquiring/other fees display absolute deduction shares;
- product cost, tax and profit display revenue shares;
- negative profit keeps negative share;
- zero revenue suppresses derived percentages;
- existing comparison percentage keeps previous-period meaning;
- existing margin and scope warning remain unchanged;
- no finance/tax formula or execution changes.

Verification:

- feature `77994ccb67c060f7c01694ac65eea5c8aec24e1d`: Verify #970, 2131 passed / 0 failed;
- PR #381 synthetic `b9a72b875081d6f12fe7f5b50d4b0c6f6af13e89`: Verify #971, 2131 passed / 0 failed;
- squash main `08d0d0fa6860101921ead603ec4a00b95c9ee8bf`: Verify #972, 2131 passed / 0 failed;
- `externally_verified=False`.

---

# Finance Accrual Pagination & Read Session Integrity v1

Boundaries:

- `OzonClient.get_accruals_by_day`
- `FinanceService.begin_read_session`
- `FinanceService._get_accruals_by_day`
- `FinanceService.get_daily_finance`
- `PeriodProfitSummaryService.calculate`

Tests:

- `tests/test_finance_accrual_pagination_read_session_v1231_v1240.py`

Проверяет:

- first accrual page sends required empty `last_id`;
- subsequent pages follow Ozon cursor until exhaustion;
- malformed accrual-page response fails closed;
- repeated cursor fails closed;
- max-page exhaustion does not return partial finance as complete;
- same day is downloaded once for multiple SKUs inside one read session;
- new read session clears day cache;
- Period Profit starts one fresh finance read session;
- read-session exceptions are contained;
- target SKU finance on the second accrual page is included.

Verification:

- failed `8d159ed09410ed978bef6cfdb5719a67bc5491b1`: Verify #990, 2140 passed / 1 failed;
- final feature `ad215b8d86c547e740dcb3583e7b7f580e9fb823`: Verify #991, 2141 passed / 0 failed;
- PR #383 synthetic `4b1f8e48de3f92c6aecc590232697890c8814d08`: Verify #992, 2141 passed / 0 failed;
- squash main `e66125d5e2c737497762178bef86dd36a62721f3`: Verify #993, 2141 passed / 0 failed;
- `externally_verified=False`.

---

# Account-Level Ozon Profit Reconciliation v1

Boundaries:

- `FinanceService.get_daily_account_finance`
- `PeriodProfitSummaryService.calculate`
- `PeriodProfitSummaryService._calculate_account_period`
- `PeriodProfitSummaryService._amounts_reconcile`
- `build_period_profit_response`
- `build_period_profit_coverage`
- Decision 037

Tests:

- `tests/test_account_level_period_profit_reconciliation_v1241_v1250.py`

Проверяет:

- account-level Ozon net accrual is the authoritative period monetary total;
- account-level non-SKU money changes profit exactly once;
- SKU revenue must reconcile to account revenue;
- mismatched revenue coverage fails closed;
- account total corrects duplicated SKU-attributed posting net;
- account fee breakdown replaces summed SKU fee breakdown;
- account finance failure blocks Period Profit;
- Telegram explains account reconciliation and no-double-subtract semantics;
- coverage exposes account-level inclusion/reconciliation;
- legacy finance without account boundary keeps V1 compatibility;
- authorized mapped account expense remains evidence and is not deducted again.

Verification:

- feature `a0e528f36b1b4721af0e8d0b419c414d20fabea6`: Verify #1010, 2151 passed / 0 failed;
- PR #385 synthetic `4a361a58d62e56c2e2aa4c608620ae86992ac05f`: Verify #1011, 2151 passed / 0 failed;
- squash main `a359e3d8e68784849caa659dec0123fb15dc6932`: Verify #1012, 2151 passed / 0 failed;
- `externally_verified=False`.

---

# Return COGS Recovery Evidence v1

Boundaries:

- `PeriodProfitReturnEvidenceService._normalize_record`
- `PeriodProfitReturnCogsRecoveryEvidenceService`
- `PeriodProfitQueryService`
- `create_period_profit_query`
- `build_period_profit_response`
- `build_period_profit_coverage`

Tests:

- `tests/test_return_cogs_recovery_evidence_v1251_v1260.py`
- updated `tests/test_period_profit_factory.py`

Проверяет:

- nested Returns API product, visual, compensation and logistics fields are preserved;
- arrived customer-return units become candidate recovery only;
- candidate value uses current configured product cost;
- compensated units are separated from recovery candidates;
- unproven visual status remains unresolved;
- missing cost remains unknown instead of zero;
- partial return sample cannot become complete recovery evidence;
- historical cost basis remains unconfirmed;
- originating sale-period lineage remains unconfirmed;
- saleable inventory recovery remains unconfirmed;
- candidate recovery does not mutate Period Profit;
- response and coverage expose candidate evidence and limitations;
- factory wiring shares the ProductCostService dependency;
- legacy positional PeriodProfitQueryService constructor remains compatible.

Verification:

- failed `2339d8aa8da1ec43c3298be2da8506a1e6dd8b9b`: Verify #1033, 2159 passed / 2 failed;
- final feature `30f3edafd9d2af603f2277701cb13492a334dd30`: Verify #1038, 2161 passed / 0 failed;
- PR #387 synthetic `c5947439450297dabb353b3dfd125e3fc6417576`: Verify #1039, 2161 passed / 0 failed;
- squash main `d845c7183ef5a914853a15b788e18b0cebfd1c93`: Verify #1040, 2161 passed / 0 failed;
- `externally_verified=False`.

---

# External Operating Expense Coverage v1

Boundaries:

- `ExpenseRepository`
- `PeriodProfitExternalExpenseEvidenceService`
- `PeriodProfitQueryService`
- `create_period_profit_query`
- `build_period_profit_response`
- `build_period_profit_coverage`
- `confirm_expense_coverage.py`
- Decision 038

Tests:

- `tests/test_external_operating_expense_coverage_v1261_v1270.py`
- updated `tests/test_period_profit_factory.py`

Проверяет:

- explicit external expense coverage intervals are persisted and read by period;
- coverage is complete only when confirmed intervals cover every requested calendar day;
- empty uncovered periods remain unknown rather than zero;
- empty fully covered periods are explicit confirmed zero expense;
- partial expense evidence is labelled incomplete;
- complete coverage permits a complete derived profit-after-external-expenses value;
- invalid dates are rejected;
- bool, NaN and infinite amounts are rejected;
- external expense evidence is wired into the production Period Profit query;
- Telegram distinguishes base profit from external-expense-adjusted views;
- coverage exposes external expense completeness and totals;
- comparison semantics stay on base Period Profit;
- Ozon-account expenses already included in account net accrual are not deducted again;
- return COGS recovery uncertainty and accounting-net-profit boundary remain unchanged;
- factory wiring includes the external expense evidence service.

Verification:

- failed `55d8f189dc170cc524aa8798aea42b1b7ae6251c`: Verify #1054, 2150 passed / 11 failed, artifact 9894680388, digest `sha256:49302f69375d247b9094b7a58f1a16c5671124eb894eef0153edd3dc1276c376`;
- failed `9f32163739d849dfe3681a9de6358fb64db40100`: Verify #1055, 2150 passed / 11 failed, artifact 9894698643, digest `sha256:e37593e820234269a9230e6be4f8c61fc591d7108f4093201bdb3192e09956d0`;
- failed `e788e5110109eb678767313278580989b192f689`: Verify #1060, 2160 passed / 1 failed, artifact 9894794990, digest `sha256:af0ffe3ef3fe9ddfce906ac6bbb3a33c10f5ac445f1884705aa3b85e483fb1fc`;
- cancelled intermediate SHAs carry no transferable success evidence;
- final feature `07f9a35eb238280e95b52bc14d18cc6aba735703`: Verify #1062, 2171 passed / 0 failed, artifact 9894853461, digest `sha256:9d28a3a5ae753f1215fd042622fd62d7e4985fa96eeba0f2f140318166617298`;
- PR #389 synthetic `77dd43cfeb36ebe0066f8747c6c51580083848a6`: Verify #1063, 2171 passed / 0 failed, artifact 9894897854, digest `sha256:9111b865c015e95c360ba417c3ef68f82377e82f9e2eddfc7c7e7d8c61ae93a0`;
- squash main `875cc4a783a48eb9a9059b9e2e9ba85316fbdc0d`: Verify #1064, 2171 passed / 0 failed, artifact 9894942156, digest `sha256:6ba30eda33b5a1315469e4fbf9253058d932cbc756e634b8996b2f31b2158e53`;
- `externally_verified=False`.

---

# Return Sale-Period Lineage Evidence v1

Boundaries:

- `FinanceService.get_daily_sale_posting_evidence`
- `PeriodProfitReturnSaleLineageEvidenceService`
- `PeriodProfitReturnCogsRecoveryEvidenceService`
- `create_period_profit_query`
- `build_period_profit_response`
- `build_period_profit_coverage`

Tests:

- `tests/test_return_sale_lineage_evidence_v1271_v1280.py`
- updated `tests/test_period_profit_factory.py`

Проверяет:

- only positive POSTING sale accruals become sale-lineage evidence;
- malformed positive sale records keep finance evidence partial;
- finance failure stays unavailable rather than becoming an empty zero;
- return lineage matches by exact `posting_number + SKU`;
- same posting with another SKU does not match;
- one unique positive sale-accrual date is a selected-period match;
- multiple sale dates are ambiguous;
- missing finance days keep lineage partial even when another day matches;
- missing return identifiers remain unresolved;
- incomplete return sample cannot produce aggregate sale-period confirmation;
- compensated returns never become COGS recovery candidates because lineage exists;
- sale-lineage service exceptions are contained and do not destroy base candidate evidence;
- confirmed sale-period lineage does not confirm historical COGS;
- confirmed sale-period lineage does not prove saleable/restored inventory;
- `confirmed_cogs_recovery_amount` remains 0;
- profit adjustment remains forbidden;
- Telegram distinguishes confirmed lineage from remaining COGS blockers;
- coverage exposes lineage without accounting-net-profit claim;
- factory shares the exact FinanceService instance between Period Profit summary and sale-lineage evidence.

Verification:

- entering exact docs-reconciled main `356fa301a9025e15a5a9fbb94da706d10670416a`: Verify #1074, 2171 passed / 0 failed, artifact 9897945762, digest `sha256:9b883028d77316bcabd7634b934f9ab38664a84468eab5622195ff73929c7653`;
- failed `db2c6c0fa900720c303a8f8face32ef3eec3be11`: Verify #1081, 2170 passed / 1 failed, artifact 9898277377, digest `sha256:2e8365779ec323568d2be3649d17d7a79e8d5a5da745f128cc11555750cd7b2e`;
- cancelled intermediate SHAs carry no transferable success evidence;
- final feature `e96fb63007647857045f226c9c41fd8157ae962e`: Verify #1083, 2185 passed / 0 failed, artifact 9898333361, digest `sha256:7ac52123e97a821e6fb65fcc7dc15dfb61d68a8be6fd40c9598b7505a174c3f5`;
- PR #391 synthetic `26d6ca0e9b2ef2b4a358cc6a517bd13bf152bffc`: Verify #1084, 2185 passed / 0 failed, artifact 9898386674, digest `sha256:a4ac6ad8520a2a0726aff061f5f579a74742f868e17e2ced9d89ac84c3798d47`;
- squash main `5c0ed4bd40207e3f4bcce3770e89e71e163288b1`: Verify #1085, 2185 passed / 0 failed, artifact 9898420551, digest `sha256:4a187e0b83b0b5950e64aaf749d31b78d7d5435132a77fde2e044667fe06b864`;
- `externally_verified=False`.

---

# Historical Product Cost Evidence v1

Boundaries:

- `ProductCostService.create_table`
- `ProductCostService.record_historical_cost`
- `ProductCostService.get_historical_cost_evidence`
- `PeriodProfitReturnCogsRecoveryEvidenceService`
- `build_period_profit_response`
- `build_period_profit_coverage`
- `record_product_cost_history.py`
- Decision 039

Tests:

- `tests/test_historical_product_cost_evidence_v1281_v1290.py`

Проверяет:

- mutable current cost does not backfill historical evidence;
- explicit effective-dated versions resolve for later sale dates;
- latest effective version applies without rewriting earlier versions;
- duplicate product/date version conflicts do not silently overwrite evidence;
- ambiguous product identity remains unconfirmed;
- dates before first historical version remain missing rather than falling back to current cost;
- Return COGS historical lookup uses the matched originating sale date;
- historical candidate value may differ from current-cost diagnostic value;
- all candidate rows must resolve for aggregate historical cost confirmation;
- missing one historical version keeps aggregate basis unconfirmed;
- Telegram shows confirmed historical cost while retaining inventory-recovery blocker;
- coverage exposes historical cost confirmation without accounting-net-profit claim;
- `confirmed_cogs_recovery_amount` remains 0;
- profit adjustment remains forbidden.

Verification:

- entering exact docs-reconciled main `212df575cc60a809032954d425902fad86623956`: Verify #1095, 2185 passed / 0 failed, artifact 9906001699, digest `sha256:a50fb08552d73f187bbacc608751655880f293578a7ac4408154808d82a16f79`;
- no failed production SHA occurred;
- cancelled intermediate SHAs carry no transferable success evidence;
- final feature `f3fcb80588f394eb05e5944ca2812ed59adf7649`: Verify #1103, 2195 passed / 0 failed, artifact 9906200014, digest `sha256:c776260a5026572cbe27c2bab5212d2a64d92d95f7a9170a433a2d5b12b46af7`;
- PR #393 synthetic `672e18f904768742917df9c808c48ec476d9fd3e`: Verify #1104, 2195 passed / 0 failed, artifact 9906235551, digest `sha256:d849f4a6413df1de6c6b3e28ed4f5c45465b292266db2c31dbac3602251fcfb0`;
- squash main `9ca4497dda61615076b8203d0404502630ab7e81`: Verify #1105, 2195 passed / 0 failed, artifact 9906262083, digest `sha256:6bc9ab6699976e56572a216dab839e96c8921f484047c522eb00535163626987`;
- `externally_verified=False`.
---

# Ozon Store Selector Discoverability

Updated tests:

- `tests/test_telegram_help_discovery.py`
- `tests/test_product_unit_economics_telegram_ui.py`

Covers visibility of the main-menu selector action and its route into the
tenant-aware existing store list.

---

# Persistent Ozon Credential State Diagnostics

Updated tests:

- `tests/test_ozon_credential_production_persistence.py`
- `tests/test_multi_tenant_ozon_onboarding.py`
- `tests/test_telegram_guided_onboarding.py`

Covers missing and mismatched master keys, preserving the ciphertext, safe
onboarding diagnostics, tenant context reset, preservation of an existing key
when tenant storage initialization fails, and refusing to advance after a failed
read-only Ozon probe.

---

# Telegram Help and Feature Discovery

Tests:

- `tests/test_telegram_help_discovery.py`
- updated `tests/test_product_unit_economics_telegram_ui.py`
- existing `tests/test_period_profit_historical_sku_cost_input_v1421_v1430.py`

Covers:

- visible help entry in the real main keyboard;
- `/help` and inline callback parity;
- production Telegram bot/adapter/button-handler callback wiring;
- complete supported slash-command inventory;
- examples for memory, custom Period Profit, effective-dated cost, and SKU identity;
- navigation back to existing workflows and main menu;
- no Ozon execution from help responses.

---

# Return Inventory Recovery Evidence v1

Boundaries:

- `ReturnInventoryRecoveryRepository`
- `PeriodProfitReturnCogsRecoveryEvidenceService`
- `create_period_profit_query`
- `build_period_profit_response`
- `build_period_profit_coverage`
- `record_return_inventory_recovery.py`
- Decision 040

Tests:

- `tests/test_return_inventory_recovery_evidence_v1291_v1300.py`
- updated `tests/test_period_profit_factory.py`

Проверяет:

- explicit `SALEABLE_RESTORED` evidence is persisted and read by exact return identity;
- explicit `NON_SALEABLE` evidence is preserved as a blocking recovery state;
- invalid state and invalid/non-positive/boolean quantity fail closed;
- duplicate `return_id + confirmed_on` evidence is rejected;
- identity drift for one `return_id` becomes conflict/unconfirmed;
- missing recovery evidence remains unknown and never infers recovery from current stock or stock delta;
- exact evidence quantity must match candidate return quantity;
- quantity mismatch blocks saleable recovery confirmation;
- one explicit non-saleable candidate blocks aggregate saleable recovery confirmation;
- compensated returns stay outside saleable recovery candidacy;
- repository exceptions are contained and do not fabricate recovery evidence;
- complete explicit saleable recovery can confirm `saleable_inventory_recovery_confirmed=True` without changing Period Profit;
- response wording exposes explicit recovery state and remaining accounting blockers;
- coverage exposes inventory-recovery completeness/counts without an accounting-net-profit claim;
- `originating_sale_quantity_confirmed=False` remains explicit;
- `recovery_period_attribution_confirmed=False` remains explicit;
- `compensation_accounting_treatment_confirmed=False` remains explicit;
- `confirmed_cogs_recovery_amount=0.0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- current Ozon stock observations/deltas are never accepted as recovery proof.

Verification:

- entering exact docs-reconciled main `7f859d1073338c5c0144edea8fe15574460e5210`: Verify #1115, 2195 passed / 0 failed, artifact 9906440691, digest `sha256:42618c7cd0f12fdd9b1c49f2231c990c71c6931727af3a09e1035719f248929a`;
- failed `41b409edcd2a96016bf49e8e8303a7aec00c1886`: Verify #1125, compile failure (`SyntaxError`), no verification artifact;
- failed `4643126328c9e461712aae30f5f7a694a7549e89`: Verify #1126, compile failure at `app/period_profit_response.py:706`, no verification artifact;
- failed `d90549d21c8fb46b0a9012c205520c68e012dbfa`: Verify #1127, compile failure with unmatched `)` at `app/period_profit_response.py:744`, no verification artifact;
- failed `13e4cfbacf617bb60c5b897137b619f079c3d500`: Verify #1128, 2203 passed / 5 failed, artifact 9906768012, digest `sha256:59dd7f0d342951b258bdef1d45b934cd107a858fc986d9326d1f06df016c2944`;
- final feature `1a83e5466bfebd79370e9576ce00b43b79bb668d`: Verify #1129, 2208 passed / 0 failed, artifact 9906795648, digest `sha256:a20b8f66b8d28365b7c9d887250782e7ab01d7885ddcca75c5bfab90541bd875`;
- PR #395 synthetic `7d7b3a5e180a2505850345cc753a7d40ba391cbf`: Verify #1130, 2208 passed / 0 failed, artifact 9906847145, digest `sha256:36f7babc92f4f0d39e708927a61e95122eada8b76892dc4eb7da8912f3e01fa4`;
- squash main `3f82b65054a2a7a48b9918803c197377bdb3557f`: Verify #1131, 2208 passed / 0 failed, artifact 9906878610, digest `sha256:45eb967f32521ae3c7a2007663f6acfffcf6fa2f1fbdddb58bc332f56a02311d`;
- failed SHAs remain failed evidence permanently and carry no transferable success claim;
- `externally_verified=False`.

---

# Period Profit Tenant Context Production Wiring

Tests:

- `tests/test_period_profit_tenant_context_production_wiring.py`

Covers:

- Telegram callback tenant binding for 7D, 28D, 56D, and 90D;
- Telegram text tenant binding for a custom date range;
- tenant credentials remain available inside concurrent Ozon finance worker threads;
- the real `PeriodProfitFinanceService`, `PeriodProfitRelatedSkuOzonClient`, `OzonCredentialProvider`, and `TelegramBotService` wiring;
- Ozon calls remain READ-ONLY and finance prefetch remains all-or-fail.

---

# Safe Period Profit Finance Diagnostics

Tests:

- `tests/test_period_profit_finance_safe_diagnostics.py`
- `tests/test_period_profit_sku_telegram_flow.py`

Covers safe HTTP classification, canonical finance error preservation, payload removal, read-only Telegram diagnostic presentation, plain-language guidance for confirming an unresolved Ozon SKU against a catalog SKU, and the warning-button route through product and period selection before confirmation.

---

# Period Profit Monetary Validation Stage Diagnostics

Updated:

- `tests/test_period_profit_finance_safe_diagnostics.py`

Covers end-to-end propagation of a sanitized formula-critical money validation stage through prefetch and Telegram runtime.

---

# Period Profit Related-SKU Runtime Finance Regression

Updated:

- `app/tests/test_period_profit_related_sku_identity.py`

Covers the production factory assignment shape, absent/null non-sale commission normalization, retained account accrual evidence, and fail-closed malformed commission handling.

---

# Selected-SKU bounded reverse identity lookup

Updated:

- `tests/test_period_profit_selected_posting_offer_identity.py`

Covers one reverse related-SKU request for 500 unrelated finance SKUs, request-local
identity reuse, and zero account-wide FBO list calls both for a proven match and for
fail-closed missing identity.
Also covers an asymmetric historical → current relation across 501 finance SKUs,
with exact singleton confirmation and a bounded number of related-SKU calls.
Also covers one batched posting sample for each of 501 finance SKUs, request-local
identity reuse, and rejection of a rewritten SKU on a shared posting.

`tests/test_period_profit_operation_diagnostics.py` also verifies structured,
secret-free identity-stage evidence in persisted snapshots.
`tests/test_period_profit_selected_posting_offer_identity.py` runs the selected
production scope with an active trace and verifies final-stage counts.
It also covers 21 parallel representative posting probes, FBO-to-FBS fallback,
tenant ContextVar propagation, rewritten SKU acceptance by exact offer, request
cache reuse, bounded call count, and multi-offer rejection.

# Guided historical selected-SKU confirmation

Updated:

- `tests/test_period_profit_selected_posting_offer_identity.py`
- `tests/test_period_profit_sku_telegram_flow.py`

Covers exposure of a nonmatching historical offer only from unique-owner,
single-offer posting evidence; Telegram candidate presentation; explicit
confirmation; fresh candidate revalidation; tenant-local mapping persistence;
automatic recalculation; and rejection of forged/stale candidates before storage.

# Seller-confirmed SKU identity revocation

Updated:

- `app/tests/test_period_profit_seller_confirmed_identity_mapping.py`
- `tests/test_telegram_help_discovery.py`

Covers exact-pair transactional revocation, mismatch fail-closed behavior, retained
audit evidence, immediate mapping absence, safe later remapping, Telegram text
routing without a profit query, invalidation wording, and help discoverability.
`tests/test_period_profit_sku_telegram_flow.py` also covers the visible report
button, explicit revocation confirmation, exact repository revalidation, one-click
recalculation, and rejection of a forged revocation callback before mutation.
It also covers ordinary later reports: only an alias actively confirmed for the
exact current product gets a revoke button. Repository coverage verifies deduplicated
batch loading of active aliases for the report surface.
Selected-SKU Telegram coverage also verifies revenue-share percentages for every
money line and suppression of undefined percentages when revenue is zero.

# Telegram custom Period Profit button

Updated:

- `tests/test_telegram_custom_period_date_input_v1171_v1180.py`

Covers menu discoverability, the date-only `ДД.ММ.ГГГГ-ДД.ММ.ГГГГ` response,
canonical ISO query arguments with previous-period comparison, invalid format and
calendar-date retry, per-user pending-state isolation, and explicit cancellation.

# Request-bound tax and onboarding cost completion

Updated:

- `tests/test_telegram_guided_onboarding.py`
- `tests/test_period_profit_request_bound_tax_policy.py`
- `tests/test_period_profit_factory.py`

Covers skipping the seller-cost prompt only for proven complete catalog coverage,
retaining the step for missing costs, production dependency wiring, and one
long-lived Period Profit service alternating between two active-store tenant scopes
with different tax rates without cross-store reuse.

# Store-wide Period Profit bounded identity recovery

Updated:

- `tests/test_period_profit_store_wide_no_fbo_snapshot.py`
- `tests/test_period_profit_selected_posting_offer_identity.py`
- `tests/test_period_profit_previous_period_single_pass.py`

Covers zero account-wide `/v3/posting/fbo/list` calls during unresolved store-wide
identity recovery, bounded exact posting fallback, and preservation of an already
proven current-period result when the optional previous period fails, without a
second current-period query.
Also covers safe Telegram presentation of multiple identity blockers, unresolved
finance SKU visibility, and guidance into the selected-SKU confirmation flow.
The same regression verifies the direct product-picker callback and the visible
seller-confirmation command template.

# Selected-SKU custom period

Updated:

- `tests/test_period_profit_sku_telegram_flow.py`

Covers button discoverability, the date-only input contract, selected-SKU retention,
per-user pending-state isolation, and canonical date-range query arguments.

# Period Profit before COGS

Added:

- `tests/test_period_profit_pre_cogs_mode.py`

Covers the separate menu and period picker, explicit incomplete-result contract,
missing-cost independence, request-local cost exclusion, custom dates, and per-user
pending-state isolation.

# Unit price batch plan — C00/C01 and domain C02

Added:

- `tests/test_unit_price_batch_plan_service.py`

Covers exact 2–10 catalog identity boundaries, duplicate/invalid selection, stable row IDs and selection ordering, one catalog snapshot, row-level FBS/source failures, shared parent HTTP cap, complete/incomplete rows, independent candidate forward-result check, local zero-cost/ad assumptions, bulk-advertising preview and confirmation/version checks, explicit refresh preserving manual provenance, and no extra source calls during local edits.

Updated:

- `tests/test_unit_price_scenario_source.py`

Covers exact supplied catalog product without a second catalog load, parent budget propagation, cache-age preservation on batch identity cache hits, and isolation of same-SKU product/offer identity aliases.

Focused local result: **75 passed**. `compileall -q app tests` and `git diff --check` passed. Full exact-head CI is required at G01.
# Unit price batch plan (module C)

- `tests/test_unit_price_batch_plan_service.py`: bounds and exact identities; one catalog read; partial source failure/FBS; parent HTTP budget; exact forward-result confirmation; local zero-valued assumptions; version-bound advertising confirmation; source refresh preserving assumptions.
- `tests/test_unit_price_scenario_source.py`: exact catalog row reuse, identity-separated cache/in-flight operations, source age retention, parent operation trace.
- `tests/test_telegram_unit_price_batch_plan_runtime_service.py`: text stages, bounded UTF-16 report and callback payloads, local edits/sorts, stale token rejection, tenant change during build, advertising preview/confirm/cancel revocation, overview handler routing, public candidate handoff, no source reload on handoff, and text ownership until the user exits the batch flow.
- Verified local profile: **116 passed** across batch service, source, target solver, scenario calculator and Telegram runtime; `compileall -q services` and `git diff --check` passed. Full CI is required for complete repository validation.

- Module C acceptance on exact code SHA `07b9d595df32b11b736aaa2dc13c822df7f52ec4`: local related B/C product profile **193 passed**, `compileall -q app tests` and `git diff --check` passed. Verify runs `39063730904` and `39063717597` both passed Windows and full-verification jobs, including full pytest, compileall, production Docker build and runtime smoke. PR #699 is open for review; no merge/deployment.

# Unit price sensitivity — D00–D03

- `tests/test_unit_price_sensitivity_service.py`: absolute input parsing and limits, 3–7 values/axis, exact 49-cell matrix, no interpolation, exact target-margin marking, unknown inputs, stale source, invalid/bool/nonfinite/overflow, existing minimum-tax branch, parallel sweeps and snapshot immutability.
- `tests/test_telegram_unit_price_sensitivity_runtime_service.py`: single and batch entry, callback routing, exact source/version/tenant binding, all 49 cells across pages, stale historical view without apply, explicit fresh-cell transfer with forward recalculation, source-free operation, text ownership/return cleanup, and parallel/read isolation.
- `tests/test_telegram_unit_price_batch_plan_runtime_service.py`: exact batch-row context, identity and source-as-of binding for the sensitivity entry.
- D focused profile: **117 passed** across sensitivity, Telegram batch/single runtimes, scenario and target planning; `compileall -q app tests` and `git diff --check` passed.
- Full local Windows run: **2,978 passed, 21 failed, 369 errors**. Failures/errors are blocked by the workspace Windows temp ACL (`PermissionError: WinError 5`; SQLite cannot open files under the created temp directory). No project-data JSON hashes changed. Exact-head `d7c33dfa9d4d1e3ffde626d375dd17d2f0d38824` passed Windows/full-verification in runs `39065039552` and `39065028764`; D03 is accepted, PR #700 remains open and unmerged.

# Telegram document contract — E00

- `tests/test_telegram_document_contract.py`: recognized document kinds, matching MIME/extension, safe filename and path rejection, UTF-8 payload conversion, analytics-vs-cost-import caption separation, malformed content rejection.
- `tests/test_telegram_cost_table_transport.py`: preserves existing cost CSV transport and caption; transport exception yields a failure status/message and never reports success before delivery.
- `tests/test_seller_cost_table_service.py`: existing export emits explicit `seller_cost_import_template` kind without changing CSV schema or import behavior.
- E00 profile: **12 passed**; compileall and `git diff --check` passed. E01 extends this contract with versioned serializers and file size handling.

# Analytics export serializer — E01

- `tests/test_analytics_export_serializer.py`: UTF-8 BOM/semicolon CSV, embedded metadata/schema, formula injection in text (including leading whitespace/tab), quoted newline/quotes, decimal comma, numeric negative money, null-vs-zero, JSON schema v1/units/provenance, NaN rejection, unknown columns, row and byte limits with no truncation.
- Related E00 contract/cost-export tests: **17 passed total**; compileall and `git diff --check` passed.

# Analytics snapshot export — E02–E04

- `tests/test_analytics_export_service.py`: period comparison/bridge/reconciliation/TOP_K semantics; all filtered overview rows; complete batch and sensitivity scopes; planned-vs-factual metadata; null/zero preservation; invalid snapshot/schema fail-closed.
- `tests/test_analytics_export_runtime.py`: exact report cache snapshot, owner/store isolation, fixed TTL, copy isolation, no source queries; public callback returns a file from the cached result.
- `tests/test_product_overview_telegram_flow.py`: overview export uses the exact snapshot without a second catalog query and includes seven rows despite five-row display pages.
- `tests/test_telegram_unit_price_batch_plan_runtime_service.py` and `tests/test_telegram_unit_price_sensitivity_runtime_service.py`: exports include all 8 batch rows / 9 matrix cells; one-time callbacks and no source reload.
- `tests/test_telegram_cost_table_transport.py`: public Telegram callback delivers analytics export with the read-only caption; legacy cost export and send-failure behavior remain covered.
- Combined E00–E04 profile: **73 passed**; `compileall -q app tests` and `git diff --check` passed. Clean Windows/Linux full verification and Docker smoke remain required on exact PR head.

# Product workbench cross-feature acceptance — G00

Added:

- `tests/test_product_workbench_acceptance.py`: runs the public Telegram handler through overview filtering, exact product selection, real batch-plan calculator with a local missing-cost correction, sensitivity sweep, and complete batch/sensitivity exports. Verifies one overview query, one catalog read, exactly one snapshot read per selected SKU, and read-only document results.

Updated:

- `tests/test_period_profit_analytics_runtime.py`: connects the finalized period comparison with cached CSV/JSON and support-diagnostic JSON; asserts the period query runs once.
- `tests/test_product_overview_telegram_flow.py`: checks that legacy main-menu sections remain available alongside workbench navigation.

G00 focused profile: **54 passed, 1 existing `tmp_path` factory test deselected** because the local Windows temp root is ACL-restricted while pytest tmpdir is disabled. New acceptance tests pass. Exact acceptance head `12447d4cb48823fea938513fbb16dc4f41a080c2` passed Verify `39069249065`; review-handoff head `1a6664429533e092b239a6240e0b1173358f0cfa` passed Verify `39069517726` (Windows, Linux full verification, Docker smoke).

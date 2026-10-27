# Журнал: помощник выбора цены по прибыли с единицы

Дата подготовки: 26.10.2026.
Задание: `LUNA_PRICE_PROFIT_PER_UNIT_TASK_2026-10-26.md`.
Статус: IN_PROGRESS; Q00–Q12 завершены, Q13–Q35 ожидают выполнения.

## Исходная точка

- Main после PR #718: `07a84b5d7a9ffa7d0007947e0d8d4e9032052e01`.
- ТЗ подготовлено в отдельном чистом worktree, ветка `codex/price-profit-per-unit-spec-20261026`.
- Основной Desktop checkout с существующими изменениями/данными не редактировался.
- Выполнена предметная сверка существующих price/tariff/source/plan/observation contracts; runtime-код не изменялся.
- Принятые решения: цель ₽/шт. после учтённых расходов; seller price; тарифы по диапазонам с обязательным ручным fallback; гипотеза изменения ДРР отделена от наблюдений.
- Текущие ставки конкретного SKU не подтверждены. 14%/20% из старой публикации не использовать как defaults.
- Обнаруженное ограничение факта: существующий SKU-report/CPC attribution не доказывает полный учёт всех расходов. ТЗ разделяет сценарий, модель по наблюдавшимся входам и сопоставимый canonical факт.
- Зафиксировано canonical ROUND_HALF_UP: в synthetic N01 при цене 95 ₽ и ДРР 16,5% реклама 15,68 ₽, прибыль 12,27 ₽; пороги равенства и строгого улучшения различаются.

## Карта этапов

| Этап | Статус | Результат / проверки |
|---|---|---|
| Q00 | DONE | PR #719 открыт, exact-head Verify #40363801273 успешен; main/spec SHA совпадают с исходной точкой, выделена реализационная ветка; рабочий tree чистый; локальные ignored runtime/cache каталоги сохранены нетронутыми. Подробности ниже. |
| Q01 | DONE | Предметный аудит завершён: существующая формула, source scope, Telegram route, saved-plan schema/CAS и отсутствие price-observation workflow подтверждены в `LUNA_PRICE_PROFIT_PER_UNIT_AUDIT_Q01_2026-10-27.md`. Runtime не менялся; Q02 baseline впереди. |
| Q02 | DONE | Изолированный baseline Windows/Python 3.12: 247 passed; Python dotenv/live credentials отключены, storage/basetemp вынесены в новую temp-папку, hashes всех 5 tracked `data/*.json` совпали до/после. Первый фактический запуск найденного runner с исправленным `PYTHONPATH=app` прошёл. |
| Q03 | DONE | Зафиксированы outcome/tariff/ad/snapshot/observation contracts, layer boundary, limits и additive planning persistence в `UNIT_PRICE_PROFIT_CONTRACT_Q03_2026-10-27.md`; Decision 061. Runtime поведение пока не заявляется. |
| Q04 | DONE | Добавлен pure `UnitPriceTariffResolver`; точные inclusive cents ranges, gaps, overlap/conflict, exact profile selection, current-price point, scope/date/scheme checks и numeric limits. Новый изолированный профиль: **34 passed in 0.44s**; подробности ниже. |
| Q05 | DONE | Official FAQ/API source checked; current FBO rate exposed only as exact current-price point via pure adapter; range remains `RANGE_SOURCE_UNAVAILABLE`. Focused profile: 88 passed; five tracked data hashes unchanged. |
| Q06 | DONE | Manual tariff persistence + rollback profile: 115 passed; five tracked data JSON hashes unchanged. See `UNIT_PRICE_PROFILE_PERSISTENCE_Q06_2026-10-27.md`. |
| Q07 | DONE | Public Telegram flow for manual FBO point/ranges: preview/explicit persistent or session-only confirmation, edit/cancel/refresh; stale/replay-safe draft bound to owner/store/SKU/scenario version. Session-only profile was also accepted by the pure resolver. Final combined profile: 199 passed. Implementation commit `cea8a8e4`; see `UNIT_PRICE_TARIFF_TELEGRAM_Q07_2026-10-27.md`. |
| Q08 | DONE | Frozen tariff snapshot and saved-plan schema v3 integrated; linked isolated Q04–Q08 profile 371 passed; 5 protected JSON hashes unchanged. Acceptance: `UNIT_PRICE_SAVED_PLAN_Q08_2026-10-27.md`. |
| Q09 | DONE | Сравнение 2–10 цен по canonical прибыли/шт. использует один frozen tariff snapshot; неизвестный вариант не получает прибыль 0; **378 passed**, owner-data hashes unchanged; commit ниже. |
| Q10 | VERIFIED | SAME_DRR / PER_PRICE_DRR / total spend per successful unit; rounded non-worse/strictly-better thresholds and unreachable status use canonical forward. Focused 112 passed; linked Q04–Q10 390 passed, five protected JSON hashes unchanged. Acceptance: `UNIT_PRICE_ADVERTISING_COMPENSATION_Q10_2026-10-27.md`. |
| Q11 | VERIFIED | Bounded seller-price grid, tariff boundaries plus adjacent cents, no silent truncation, max 200 candidates / 20 tariff rules, 10-row pagination and selected-only compensation thresholds. Focused profile 104 passed; linked Q04–Q11 398 passed. See acceptance below. |
| Q12 | VERIFIED | Frozen tariff bands partition target search into covered intervals; gaps/conflicts remain unknown; direct candidate/previous-cent checks; 20-rule and 1,024-forward limits. Focused 115 passed; linked Q04–Q12 profile 404 passed across 21 modules. Acceptance: `UNIT_PRICE_TARGET_TARIFF_SEARCH_Q12_2026-10-27.md`. |
| Q13 | NOT_STARTED | — |
| Q14 | NOT_STARTED | — |
| Q15 | NOT_STARTED | — |
| Q16 | NOT_STARTED | — |
| Q17 | NOT_STARTED | — |
| Q18 | NOT_STARTED | — |
| Q19 | NOT_STARTED | — |
| Q20 | NOT_STARTED | — |
| Q21 | NOT_STARTED | — |
| Q22 | NOT_STARTED | — |
| Q23 | NOT_STARTED | — |
| Q24 | NOT_STARTED | — |
| Q25 | NOT_STARTED | — |
| Q26 | NOT_STARTED | — |
| Q27 | NOT_STARTED | — |
| Q28 | NOT_STARTED | — |
| Q29 | NOT_STARTED | — |
| Q30 | NOT_STARTED | — |
| Q31 | NOT_STARTED | — |
| Q32 | NOT_STARTED | — |
| Q33 | NOT_STARTED | — |
| Q34 | NOT_STARTED | — |
| Q35 | NOT_STARTED | — |

## Проверки подготовки документа

Реализация и pytest для неё не запускались: изменяется только документация.

- Однократная read-only проверка структуры: 36 уникальных упорядоченных этапов Q00–Q35, полная ациклическая dependency table, все 36 строк NOT_STARTED в журнале, 13 групп приёмки N01–N13 — PASS.
- Проверено существование 25 перечисленных source/document paths — PASS.
- Шесть примеров прибыли/рекламы и три примера комиссии пересчитаны прямым вызовом существующих чистых `UnitPriceScenarioService` и `TaxService` с `tax_mode=NONE` — PASS. Примеры взвешенной агрегации и разных баз ДРР проверены Decimal-арифметикой — PASS.
- Проверка выполнялась Python 3.12 из ранее изолированного venv с `-B`, без запуска приложения, записи storage и сетевых запросов. Новый тестовый файл не добавлялся.
- Проверки `git diff --check` и полного `git diff --cached --check` прошли; staged diff содержит только шесть Markdown-файлов задания/журнала/указателей.
- `DECISIONS.md` не менялся: архитектурная реализация ещё не начата. CHANGELOG/CURRENT_STATE/ROADMAP/TEST_MAP ссылаются на новый план, не объявляя его готовым функционалом.
- Старый exact-head CI PR #718 является доказательством базы, не проверкой будущей реализации. CI документального PR отслеживается отдельно.

## Следующее действие / resume

1. Выполнить Q11: построить bounded grid/step, включая границы frozen tariff bands; раскрыть исследованный набор и не выдавать его за глобальный оптимум.
2. Continue in dependency order; after every stage record commands, exact outcomes, protected-data hashes and commits below.

## Записи исполнения

### Q00 — зафиксирована база реализации (2026-10-27)

- PR #719: открыт, mergeable, ветка задания `codex/price-profit-per-unit-spec-20261026`, HEAD `7c554a1411717cfe1d5dab0722fe025affbf32f6`; основание PR и фактический `origin/main` — `07a84b5d7a9ffa7d0007947e0d8d4e9032052e01`. Задание выполняется stacked branch/PR поверх PR #719, чтобы не дублировать его документацию и не ждать слияния.
- Проверка точного HEAD PR #719: Verify run `40363801273`, conclusion `success` (Windows/Python 3.12, Linux/Python 3.11, production Docker build/runtime smoke; доказательство относится только к документальной базе).
- Выделенная рабочая копия `daily-readiness-foundation` была clean до переключения; реализационная ветка создана без копирования/изменения чужого diff: `codex/price-profit-per-unit-implementation-20261027` на SHA `7c554a1411717cfe1d5dab0722fe025affbf32f6`.
- Защищённые owner-data пути: отслеживаемые `data/history.json`, `data/profiles.json`, `data/tasks.json`, `data/tax_configuration.json`, `data/users.json`; локальный ignored `.runtime-data` в выделенной копии не открывался и не меняется. В Desktop checkout и соседних worktree не вносятся изменения. Реальный бот, `.env`, Telegram/Ozon API и сетевые данные не используются.
- Команды проверки: `git status --short --branch`, `git rev-parse HEAD`, `git fetch --no-tags origin main`, `git rev-parse FETCH_HEAD`, GitHub `get_pr_info(#719)`, `fetch_commit_workflow_runs(7c554a1411717cfe1d5dab0722fe025affbf32f6)`.
- Фактический результат: перед созданием ветки tree clean; PR head соответствует текущему main + документальный commit; ветка исполнения выделена. Q00 — PASS. Pytest не запускался: этап только фиксирует базу, среду изолированных проверок определит Q02.
- Q00 следующий этап после commit: Q01 — предметный аудит маршрутов и существующих контрактов.

### Q01 — предметный аудит (2026-10-27)

- Добавлен read-only audit `LUNA_PRICE_PROFIT_PER_UNIT_AUDIT_Q01_2026-10-27.md` со ссылками на реализацию, тесты, наблюдаемые parser/search/storage limits, подтверждённые существующие контракты и отсутствующие функции.
- Подтверждено: canonical forward/TaxService VERSION=2 и ROUND_HALF_UP уже существуют; current FBO fee — только точечный тариф; input source маркирует fixed fees/ad manual-required; сравнение цен — 2–5 вариантов с единой переданной ставкой; ad cap не является порогом сохранения ₽/шт.; Planning SQLite имеет tenant scope, revisions/CAS, schema v2 и allowlist, но нет tariff/observation entities; отдельного price-observation handler/repository нет.
- Публичные consumer paths подтверждены по `assistant_button_handler_service.py`, `assistant_keyboard_service.py`, `telegram_unit_price_calculator_runtime_service.py`, `telegram_assistant_factory.py`; existing regression suites указаны в audit.
- Проверки: `rg` по tracked services/adapters/tests и точечное чтение существующих сервисов/схемы — PASS; runtime и storage не изменялись, pytest не нужен на audit-only этапе.
- Архитектурный вывод оставлен к Q03: расширить существующую tenant planning SQLite additive tariff/observation entities, переиспользовать canonical engine и UI route; DECISIONS пока не менялся.
- Q01 — PASS. Следующее: Q02 — полностью изолированный baseline.

### Q02 — изолированный базовый профиль (2026-10-27)

- Runner: существующий Python 3.12.10 venv `.z20-isolated-env` из предыдущего verification worktree; в него не ставились/не обновлялись пакеты. Запускался только как interpreter/pytest, тестовый код и результаты принадлежат реализации worktree.
- Для каждого pytest запуска создавались отдельные случайные `%TEMP%/codex-q02-price-profit-*` roots: `AI_ASSISTANT_STORAGE_ROOT=.../storage`, `--basetemp=.../pytest-temp`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHON_DOTENV_DISABLED=1`, `PYTEST_ADDOPTS=''`, `PYTHONPATH=<implementation-worktree>/app`; credentials keys из процесса удалены без чтения/логирования значений. pytest cache plugin выключен.
- Команда успешного baseline: `python -m pytest -q -p no:cacheprovider --basetemp <fresh-temp> <16 related test files>`; файлы: `test_unit_price_scenario_service.py`, `test_unit_price_scenario_source.py`, `test_current_product_economics_source.py`, `test_current_unit_economics_production_wiring.py`, `test_unit_price_scenario_architecture_review_regressions.py`, `test_unit_price_scenario_repeat_review_regressions.py`, `test_unit_price_target_planning_service.py`, `test_unit_price_advertising_cap_service.py`, `test_unit_price_sensitivity_service.py`, `test_telegram_unit_price_sensitivity_runtime_service.py`, `test_unit_price_scenario_telegram_runtime.py`, `test_planning_workspace_repository.py`, `test_saved_planning_plan_telegram_flow.py`, `test_period_profit_plan_fact_comparison.py`, `test_analytics_export_service.py`, `test_analytics_export_serializer.py`.
- Результат Windows/Python 3.12.10: **247 passed in 7.60s**.
- SHA-256 всех пяти tracked files `data/history.json`, `data/profiles.json`, `data/tasks.json`, `data/tax_configuration.json`, `data/users.json` совпали до/после. `AI_ASSISTANT_STORAGE_ROOT` и pytest basetemp были новыми; существующие `.runtime-data`, кеш и user checkouts не открывались и не изменялись.
- До успешного запуска были две безвредные подготовительные ошибки команды (один несуществующий test filename и отсутствующий `PYTHONPATH=app`): pytest не собрал тесты в первой попытке, второй запуск остановился на collection import errors; обе попытки завершились hash check без изменений owner data. Исправленный запуск — PASS.
- Q02 — PASS; baseline зафиксирован для будущих регрессий. Следующее: Q03 — formalize shared contracts/decision.

### Q03 — shared contracts and persistence ownership (2026-10-27)

- Добавлены `UNIT_PRICE_PROFIT_CONTRACT_Q03_2026-10-27.md`, detailed `DECISIONS_061.md` и индексированное архитектурное решение 061 в `DECISIONS.md`.
- Зафиксированы: objective ₽ за успешную единицу; seller-price basis; отдельные status/evidence basis; exact-scope bounded tariff resolution; три рекламных режима с revenue basis; пороги равенства/строгого роста через canonical forward; frozen source snapshot; bounded candidates/HTTP; owner-triggered read-only observations; quality-gated recommendations; explicit saved-plan upgrade и old v1/v2 frozen readers.
- Ownership: existing tenant SQLite + `PlanningWorkspaceRepository` единственные владельцы схемы/миграций/транзакций новых tariff/observation entities; application services — тонкая orchestration; pure resolver/compare — без I/O. Saved plans сохраняют frozen profile revision; observations append-only с idempotency/CAS; текущий backup/restore boundary сохраняется.
- Проверки: сверены секции 2, 4–11, 13 ТЗ, DECISIONS 036–050/059–060, текущие planning schema и baseline suites. Q03 — contract-only; pytest новых runtime функций не запускался.
- Q03 — PASS, runtime implementation ещё не заявлена. Следующее: Q04 — pure tariff resolver.

### Q04 — pure tariff range resolver (2026-10-27)

- Добавлены `app/services/unit_price_tariff_resolver.py` и `tests/test_unit_price_tariff_resolver.py`. Resolver не обращается к Telegram/Ozon/SQLite; принимает bounded normalized profiles и exact seller price cents, identity, FBO schema и date.
- Resolver реализует inclusive integer-cent bounds, explicit current-price point, manual/confirmed origins, exact profile/revision selection, explicit conflict, gaps as UNKNOWN, expiration, FBO-only support, owner/store/product/offer/SKU/date scope checks, 20-profile/20-band limits и существующий forward price ceiling. Ставки принимаются только как Decimal/string/int (без bool/float), `[0,100]`, non-finite отклоняются, 0% сохраняется. Об overlap включённой границы отказ; ссылка источника проходит allowlist до projection.
- N03 boundary cross-check передаёт тариф resolver → canonical `UnitPriceScenarioService`: комиссии 11.00 ₽ для 100.00, 22.00 ₽ для 100.01 и 22.22 ₽ для 101.00.
- N04 regressions проверяют дырку, inclusive overlap, конкурирующие профили и явный выбор revision, stale state revision, current point vs neighboring prices, foreign scopes/date, FBS, zero/invalid/NaN/Infinity/bool/float, истёкший профиль, скрытие небезопасного source ref и limits.
- Изолированный Windows/Python 3.12.10 профиль: `tests/test_unit_price_tariff_resolver.py` — **34 passed in 0.44s**. Использовались новый temp/storage, dotenv disabled, credentials удалены из process env, pytest cache disabled. Никаких live запросов или owner-data изменений.
- Q04 — PASS. По Q05 автоматический источник рассматривается отдельно; resolver не придумывает тарифы и не подставляет устаревшие defaults.

### Q05 — current-price commission source boundary (2026-10-27)

- Official Ozon Seller API FAQ and linked `ProductAPI_GetProductInfoPricesV4` page were checked; current project client calls `/v5/product/info/prices`. Official FAQ confirms a method to read a product commission percentage, but accessible contract does not confirm hypothetical seller-price input or a rate grid. See `UNIT_PRICE_TARIFF_SOURCE_Q05_2026-10-27.md` for source links and exact limitations.
- Added `app/services/unit_price_tariff_source.py`, a pure adapter over the already fetched `UnitPriceScenarioSource` snapshot. It exposes only a same-price/same-date FBO `CURRENT_PRICE_POINT`; it never performs a second API call, persists data or propagates a point to other prices. Other prices remain `RANGE_SOURCE_UNAVAILABLE` for Q06–Q07 manual continuation.
- Added `tests/test_unit_price_tariff_source.py`; isolated `test_unit_price_tariff_source.py`, `test_unit_price_tariff_resolver.py`, `test_unit_price_scenario_source.py` and `test_current_product_economics_source.py` on Windows/Python 3.12.10: **88 passed in 1.47s**. An earlier focused attempt had 6 failures caused by an incorrect synthetic tenant delimiter; fixture was corrected to repository convention. The final expanded source integration + source + resolver run passed.
- Five tracked `data/*.json` SHA-256 hashes were unchanged. No live API, credentials, owner storage or bot process was used.
- Q05 — PASS. Next dependency: Q06 durable manual tariff profile repository. Q06 subsequently passed; next dependency is Q07 Telegram input/confirmation.


### Q06 — постоянные ручные тарифные профили (2026-10-27)

- Расширена существующая `PlanningWorkspaceRepository` аддитивной версией БД v3; версия payload сохранённых планов остаётся v1/v2. Добавлены tenant-scoped таблицы активных/архивных тарифов, append-only content revisions и bounded idempotency records. Все операции выполняются транзакционно в этом репозитории.
- Профиль принимает только подтверждённое владельцем допущение FBO по точной identity product/offer/SKU, цене продавца в копейках, рублям и effective dates. Запрещены лишние поля, неподтверждённый ввод, FBS, bool вместо целого/ставки, невалидные даты, пересечение inclusive диапазонов и превышение лимитов. Текущая API-точка не конвертируется в тарифный диапазон.
- Create/update/archive используют tenant scope, idempotency и CAS по content/state revision. Идентичность immutable; есть bounded quotas/pagination. Архив меняет только state revision, чтение latest возвращает актуальный state, историческая тарифная ревизия остаётся точной. Restart/reopen профиль передаёт в pure resolver как `MANUAL_RANGE`.
- Добавлены `tests/test_planning_workspace_tariff_profiles.py` и обновлены миграционные ожидания в `tests/test_planning_workspace_repository.py`: round-trip/reopen/resolver, повтор create/update, stale CAS, immutable identity, owner/store isolation, archive/history, allowlist и quotas, атомарный rollback записи и v2→v3 rollback.
- Адресный изолированный Windows/Python 3.12.10 профиль: `tests/test_planning_workspace_tariff_profiles.py`, `tests/test_planning_workspace_repository.py`, `tests/test_unit_price_tariff_resolver.py`, `tests/test_unit_price_tariff_source.py`, `tests/test_unit_price_scenario_source.py`, `tests/test_current_product_economics_source.py` — **115 passed in 2.26s**. При контрольном запуске пять tracked `data/*.json` SHA-256 совпали. `py_compile` и `git diff --check` прошли.
- Проверка проходила с новым `%TEMP%` storage и basetemp, dotenv/live credential env отключён, без сети, реального API, пользовательской БД и запуска бота. Старые сохранённые плановые payload contracts не менялись.
- Q06 — PASS; implementation commit `a5c78d75` (`Persist manual unit price tariff profiles`). Q07 is complete; details follow.

### Q07 — Telegram-ввод и подтверждение ручного тарифа (2026-10-27)

- Добавлены parser и owner-facing маршрут через production `AssistantTelegramAdapter` → `AssistantButtonHandlerService` → `TelegramUnitPriceTariffProfileRuntimeService`. FBO-кнопка принимает точечную ставку или до 20 точных непересекающихся диапазонов в рублях/копейках; можно указать дату начала действия. До подтверждения данные существуют только как ограниченный временный черновик.
- Явная кнопка сохраняет профиль либо создаёт session-only профиль; доступны редактирование, отмена и явное обновление цены Ozon. Перед подтверждением сверяются пользователь, магазин, SKU, схема, scenario id/version и TTL; старые/повторные кнопки не создают запись. Постоянная запись использует Q06 repository allowlist/CAS/idempotency; обновление сохраняет историю версий.
- Session-only getter возвращает профиль только тому же owner/store/scenario и истекает через час; он не записывается в SQLite. Q08 ещё должен передавать этот профиль в resolver/сценарий и замораживать выбранную редакцию в сохранённом плане. После возврата с Q07 экран калькулятора использует прежние входные допущения до Q08.
- Добавлены `tests/test_unit_price_tariff_input_parser.py` и `tests/test_telegram_unit_price_tariff_profile_runtime.py`: формат/границы/перекрытия/limits, полный public Telegram route, подтверждение/reopen, replay, revision update, session-only/no persistence, edit/cancel/invalid input, FBS deny, stale version/draft/store; session-only профиль принимается pure resolver. Финальная проверка совместно с тарифным resolver/source/repository, калькулятором и saved-plan Telegram suite: **199 passed in 4.47s** (изолированный Windows/Python 3.12.10, fresh TEMP storage/basetemp, dotenv off, без сети/API/бота).
- Все затронутые Python-модули прошли `py_compile`; `git diff --check` завершился без замечаний. Тестовая база и pytest basetemp находились в отдельной TEMP-папке; protected tracked owner-data files не входят в изменения.
- Q07 — PASS; implementation commit `cea8a8e4c03753eb34a133497271543596d47f3b` (`Add Telegram manual tariff confirmation flow`). Next: Q08 — resolver/snapshot/saved-plan integration. Реальный Telegram/Ozon сценарий не запускался.

### Q08 — тарифный снимок и совместимость сохранённых планов (2026-10-27)

- Подключены persistent и session-only тарифные профили к текущему экрану расчёта через внедряемый resolver. Захват сохранённого сценария фиксирует exact profile/revision/state revision, допустимые ценовые диапазоны, разрешённую ставку и основание рекламы; повторное открытие использует только frozen snapshot.
- Введён single-plan schema v3 с `calculation_version=2`; существующие v1/v2 остаются читаемыми без повторного API/БД чтения и не пересчитываются автоматически. Для legacy-плана сохранённая комиссия применима только к исходной цене. При изменении цены она остаётся неизвестной до подтверждённого ручного ввода либо явного обновления снимка. Обновление копии не переносит устаревшее ручное значение.
- Snapshot adapter разрешает frozen профиль для другой цены без I/O, но только при полном, проверенном наборе кандидатов. `SOURCE_UNAVAILABLE`, пустое покрытие, чужая identity или испорченная ревизия не превращаются в rate. При единственном подтверждённом диапазоне он имеет приоритет над совпавшей точкой текущей цены; два пересекающихся диапазона остаются конфликтом.
- Исправлены замеченные при интеграции дефекты: соблюдение фактического лимита page size репозитория (10), единый ключ owner id при восстановлении, устранение дублирования профиля session/persistent, защита от разрешения частичного source-unavailable набора и возврата кросс-ценового сравнения для legacy runtime без tariff resolver.
- Проверка: изолированный Windows/Python 3.12.10 Q04–Q08 профиль — **371 passed in 8.41s**. Запуск: `python -m pytest -q -p no:cacheprovider --basetemp <fresh-temp> <22 tariff/source/scenario/planning test files>`. `AI_ASSISTANT_STORAGE_ROOT` и pytest basetemp были новыми временными каталогами; dotenv и plugin autoload отключены.
- SHA-256 пяти защищённых tracked JSON (`data/history.json`, `data/profiles.json`, `data/tasks.json`, `data/tax_configuration.json`, `data/users.json`) совпали до и после запуска. Сеть, реальные Ozon/Telegram API, bot process, `.env`, рабочая пользовательская БД и ignored runtime data не использовались.
- Документы Q08 обновлены: `CHANGELOG.md`, `CURRENT_STATE.md`, `TEST_MAP.md`, Decision 061 и `UNIT_PRICE_SAVED_PLAN_Q08_2026-10-27.md`. Код затрагивает 8 сервисов/фабрику и 4 тестовых файла плюс новый adapter/test; это **Architecture Review Required**. Полный pytest/CI — не запускался; он запланирован в Q33–Q35.
- Q08 — PASS; implementation/docs commit `2cf24a71` (`Freeze tariffs in unit price plans`). Следующее: Q09, сравнение 2–10 цен по ₽/шт. на общем frozen snapshot.

### Q09 — сравнение 2–10 цен по прибыли с единицы (2026-10-27)

- Сравнение принимает от 2 до 10 явных вариантов и использует существующий `UnitPriceScenarioService` для каждой доступной строки. Комиссия разрешается отдельно для каждой цены из одного замороженного набора профилей; current-price point и legacy ставка применяются только к точной исходной цене. Неизвестный/непокрытый вариант получает `profit=None` и не может победить числом 0.
- Экран показывает исходную базу, рекламное основание одинаковой ДРР, подтверждённый максимум только среди рассчитанных цен, ставку комиссии и изменение прибыли к базе. Сохранённая целевая маржа остаётся в результате при переходе к сравнению. Выбор цены повторно проверяется canonical forward с тарифом строки и только после совпадения применяет цену к локальному сценарию.
- Frozen tariff snapshot фиксируется при первом построении экрана и сохраняется в session state только при совпадении owner/store/scenario/version. Последующие изменения цен не вызывают повторных source/profile reads. Явное подтверждение нового тарифа создаёт новое состояние снимка; старые callbacks и результаты инвалидируются.
- Ручная комиссия, введённая в самом сценарии поверх сохранённого диапазона, трактуется как точечное допущение только для захваченной цены. Она может разрешить точную строку, не расширяется на соседние варианты и не ломает разрешение оставшихся цен из диапазона.
- Добавлены регрессии в `tests/test_unit_price_target_planning_service.py`, `tests/test_unit_price_scenario_telegram_runtime.py`, `tests/test_unit_price_tariff_snapshot_adapter.py`. Критические случаи: тарифный скачок на 100 ₽, unknown current-price point, legacy exact-price-only, 10/11 кандидатов, равная округлённая прибыль, отсутствие повторных source reads и повторная проверка при применении.
- Проверки Windows/Python 3.12.10 в новой `%TEMP%`-среде: focused runtime/profile — **120 passed in 3.16s**; полный связанный Q04–Q09 профиль — **378 passed in 8.90s**. Перед/после профильного запуска SHA-256 пяти защищённых `data/*.json` совпали. Dotenv и plugin autoload выключены, credentials-переменные удалены из процесса; сеть, Ozon/Telegram API, рабочая БД и реальный бот не использовались. `git diff --check` — PASS; предупреждения Git о нормализации LF→CRLF не меняют содержимое.
- Q09 — VERIFIED. Implementation/docs commit `02c80f1a993a424a32cbaead0bad5036a2fb1a73` (`Compare unit-price candidates with frozen tariffs`). Это изменение расширяет существующие price-planning и Telegram contracts, поэтому классификация — **Architecture Review Required**. Следующий этап: Q10.

### Q10 — рекламные режимы и пороги компенсации (2026-10-27)

- Сравнение цен поддерживает SAME_DRR (текущая явно указанная seller-revenue ДРР), PER_PRICE_DRR (ввод одной ДРР на каждую цену с проверкой количества и порядка), MANUAL_COST_PER_SUCCESSFUL_UNIT (общие рекламные расходы / число успешных продаж). Для ручного режима знаменатель сохраняется как `SUCCESSFUL_UNITS`, расход на единицу округляется до копейки, эквивалентная candidate DRR остаётся допущением. Никакой режим не утверждает причинный эффект цены на конверсию, спрос или рекламные расходы.
- Для каждого рассчитанного кандидата pure bounded `UnitPriceAdvertisingCompensationService` ищет по шкале 0–100% с шагом 0,01 процентного пункта порог прибыли за единицу не ниже и строго выше базовой. Каждый порог и следующий tick перепроверяются прямым вызовом `UnitPriceScenarioService`, поэтому налог, зависящий от расходов на рекламу, остаётся внутри канонической формулы. Недостижимый порог возвращается как `NOT_REACHABLE`; invalid/unknown/partial outcomes не подменяются нулём. Ограничения: 64 forward calls per candidate, 1,024 per comparison; монотонность подтверждается граничными probes, а результат обозначен как проверенный сценарный порог, не forecast.
- Telegram-поток использует versioned pending state для двух режимов, принимает bounded input и сохраняет исходный сценарий до явного выбора. Выбранный candidate revalidates canonical profit; только после совпадения выбранная цена и advertising assumption сохраняются в локальном scenario state. Ozon API/source reads and seller price mutations не добавлялись. Review исправил concurrent-state read: prices/stage copied under lock before prompt is built.
- Добавлены N01/N02 forward vectors, denominator/invalid input, tax-dependent forward boundary and `NOT_REACHABLE` assertions в `tests/test_unit_price_target_planning_service.py`; public input/apply assertions расширены в `tests/test_unit_price_scenario_telegram_runtime.py`.
- Focused isolated Windows/Python 3.12.10 profile: `tests/test_unit_price_target_planning_service.py tests/test_unit_price_scenario_telegram_runtime.py tests/test_unit_price_advertising_cap_service.py tests/test_unit_price_scenario_service.py` — **112 passed in 1.70s**. Same Python runner `-B -m py_compile` over `unit_price_advertising_compensation_service.py`, `unit_price_target_planning_service.py`, `telegram_unit_price_calculator_runtime_service.py`, and `assistant_keyboard_service.py` — exit 0.
- Final linked isolated Q04–Q10 profile: 22 tariff/planning/scenario/source/consumer files — **390 passed in 7.90s**. Five protected tracked JSON SHA-256 hashes (`data/history.json`, `data/profiles.json`, `data/tasks.json`, `data/tax_configuration.json`, `data/users.json`) unchanged. New `%TEMP%` storage and pytest basetemp used, dotenv/plugin autoload disabled and credential-named process variables removed without printing values; no `.env`, network/API, live bot, ignored runtime store or owner DB read/write.
- `git diff --check` and `git diff --cached --check` passed after removing two trailing Markdown spaces from the acceptance header. Q10 implementation/docs commit: `c6d75a0437d82cc39297c85f960a1a9493b0b57a` (`Add advertising compensation to unit price comparison`); a small follow-up documentation whitespace cleanup is recorded separately. Acceptance: `UNIT_PRICE_ADVERTISING_COMPENSATION_Q10_2026-10-27.md`. Code/docs touch the calculation service contract, public Telegram flow and a new pure solver: **Architecture Review Required**. Q10 — VERIFIED. Next: Q11 bounded candidate grid and tariff boundaries.

### Q11 — ограниченная ценовая сетка и тарифные границы (2026-10-27)

- В `UnitPriceTargetPlanningService` добавлен ввод диапазона цены продавца `начало; конец; шаг`. Конечная цена включается, даже если шаг не делит интервал; кандидаты упорядочиваются и дедуплицируются по копейкам.
- Для каждого сохранённого тарифного диапазона внутри запрошенного интервала добавляются нижняя/верхняя границы и соседние копейки. Сумма правил по frozen profiles ограничена 20; кандидатный набор — 200. При превышении любого лимита расчёт не усечён: пользователь получает просьбу сузить сетку или уточнить тариф.
- Сетка использует frozen tariff snapshot и существующий canonical forward. Неизвестный тариф/ставка остаются без прибыли, строки результата хранят компактные суммы без повторного payload forward. Исследованный набор записан в `price_grid.searched_prices`; статус максимума явно ограничен проверенной сеткой. Оценка рекламной компенсации отложена для всех строк и вычисляется после выбора одной цены.
- Telegram выдаёт по 10 строк на страницу с глобальной нумерацией и корректным selector. Прокрутка страниц остаётся доступной при устаревшем источнике, но действие подстановки отключено. Выбранная цена повторно проходит canonical forward до локального применения; сетевых запросов на кандидата не добавлено.
- Обнаруженные регрессии при проверке: инициализирован компактный список кросс-докинга в result formatter; исправлен тестовый путь notice; пагинация отделена от разрешения на применение.
- Focused isolated Windows/Python 3.12.10 Q11 profile (`test_unit_price_target_planning_service.py`, `test_unit_price_scenario_telegram_runtime.py`, `test_unit_price_tariff_snapshot_adapter.py`): **104 passed in 1.55s**. Linked Q04–Q11 profile over 22 tariff/planning/scenario/source/consumer modules: **398 passed in 8.05s**. Three changed Python modules compiled in memory; `git diff --check` passed after final code changes.
- Test root and pytest basetemp were new `%TEMP%` paths; dotenv and pytest plugin autoload disabled, credential-named environment variables removed without values. The five protected tracked `data/*.json` paths are git-clean; their newline-normalized SHA-256 matches Git HEAD. Raw worktree bytes are CRLF-normalized. No owner DB, ignored runtime data, `.env`, API/network or live bot was used.
- Q11 modifies the existing planning service contract, Telegram result mode and keyboard actions: **Architecture Review Required**. Acceptance: `UNIT_PRICE_PRICE_GRID_Q11_2026-10-27.md`. Q11 — VERIFIED. Next: Q12 segmented target-price search across tariff jumps.
- Q11 implementation/docs checkpoint: `66d1120995fcf906f9dfe7b7d816cfe200415ba5` (`Add bounded unit price grid`). Q11 journal/verification and Q12 start marker are recorded in the following documentation-only checkpoint.

### Q12 — поиск минимальной целевой цены при скачках тарифа (2026-10-27)

- Проверена исходная single-rate реализация `_find_candidate`: её бинарный поиск предполагает одну ставку и был бы некорректен при пересечении тарифной границы. Этот путь оставлен только для вызовов, которые не требуют tariff resolution; исходный лимит 128 forward calculations сохранён.
- Для tariff-aware `solve()` добавлена отдельная ветка: snapshot проверяется по identity/current seller price; количество правил ограничено 20; ценовой домен режется в inclusive целочисленных копейках по каждой frozen band. Вычисляются только интервалы с единым resolved profile/rate; gaps, conflicts, expired/source-unavailable остаются unknown.
- Внутри каждого рассчитанного интервала target search сначала проверяет пять упорядоченных точек, останавливается при наблюдаемом нарушении монотонности и бинарно сужает только локальный false/true bracket. Поиск посещает интервалы по возрастанию; между тарифными диапазонами бинарный переход не выполняется. Точный candidate и предыдущая копейка внутри диапазона повторно проверяются через `UnitPriceScenarioService`.
- Старый сохранённый тариф без frozen snapshot допустим только на его точной цене. Telegram теперь вызывает `_prepare_tariff`, передаёт frozen snapshot/legacy exact point, показывает непокрытые диапазоны и ограничение «минимум только среди рассчитанных сегментов». Применение остаётся локальным и проходит прежнюю проверку прибыли/комиссии; Ozon API и изменение цены не добавлены.
- Регрессии покрывают N03 (синтетический скачок 11%→22%, цель достижима до скачка, недостижима сразу после и снова достижима позже), поиск только в более позднем сегменте, gap/conflict, 20/21 rules, 1 024-call budget, source-unavailable, legacy exact-price, наблюдаемую немонотонность, Telegram coverage disclosure и tariff-aware apply.
- Focused isolated Windows/Python 3.12.10 (`test_unit_price_target_planning_service.py`, `test_unit_price_scenario_telegram_runtime.py`, `test_unit_price_tariff_snapshot_adapter.py`): **115 passed in 1.65s**. Linked Q04–Q12 isolated profile over 21 tariff/planning/saved-plan/scenario/source/Telegram modules: **404 passed in 7.97s**. `git diff --check` passed; tracked protected JSON files remained clean. Temp root was new; dotenv/plugin autoload disabled, credential-named environment variables removed; no network/API, bot or owner DB used.
- Acceptance: `UNIT_PRICE_TARGET_TARIFF_SEARCH_Q12_2026-10-27.md`. Existing service/runtime contract is extended: **Architecture Review Required**. Q12 — VERIFIED. Next: Q13 audit of consumers of price/tariff changes.

# Журнал: помощник выбора цены по прибыли с единицы

Дата подготовки: 26.10.2026.
Задание: `LUNA_PRICE_PROFIT_PER_UNIT_TASK_2026-10-26.md`.
Статус: IN_PROGRESS; Q00 завершён, Q01–Q35 ожидают выполнения.

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
| Q04 | NOT_STARTED | — |
| Q05 | NOT_STARTED | — |
| Q06 | NOT_STARTED | — |
| Q07 | NOT_STARTED | — |
| Q08 | NOT_STARTED | — |
| Q09 | NOT_STARTED | — |
| Q10 | NOT_STARTED | — |
| Q11 | NOT_STARTED | — |
| Q12 | NOT_STARTED | — |
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

1. Начать Q04: реализовать pure tariff range resolver с N03/N04 regressions.
2. После Q04 перейти к Q05/Q06; Q15 выполнять по dependency table.
3. После каждого этапа обновлять эту таблицу и дописывать точные команды/результаты ниже.

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

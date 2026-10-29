# Журнал: расширенная экономика SKU и ценовые эксперименты

Дата: 28–29.10.2026.
ТЗ: LUNA_FULL_UNIT_ECONOMICS_AND_PRICE_EXPERIMENTS_TASK_2026-10-28.md.
Статус: IN_PROGRESS. W00–W09 завершены; следующий доступный этап — W10.
База подготовки: main 9315046cf29c9e8c68da1cab027cb2568040f142 (PR #719 и #720 merged).
Ветка подготовки: codex/full-unit-economics-experiments-spec-20261028.
Ветка реализации: codex/full-unit-economics-experiments-implementation-20261028.
Аудит подготовки: FULL_UNIT_ECONOMICS_AND_PRICE_EXPERIMENTS_AUDIT_2026-10-28.md.

## Resume

- Следующий этап: W10.
- Implementation branch создана от точного HEAD PR #721 `f76d2dd90e4298113c037278666532715974e4a8`; базовый `main` на старте — `9315046cf29c9e8c68da1cab027cb2568040f142`.
- W00 implementation HEAD: `4826a5fd887fa16c1730dbbd5f894874dfa68e2e`; W00 baseline: `UNIT_ECONOMICS_W00_BASELINE_2026-10-28.md`.
- W01 audited incoming HEAD: `4826a5fd887fa16c1730dbbd5f894874dfa68e2e`; evidence: `UNIT_ECONOMICS_W01_DATA_LINEAGE_AUDIT_2026-10-28.md`.
- W02 audited incoming HEAD: `886aa440b0076df90ff6d1ba23b070ad48a8dfaa`; evidence: `UNIT_ECONOMICS_W02_OZON_API_CONTRACT_AUDIT_2026-10-28.md`.
- W03 architecture incoming HEAD: `80395612`; evidence: `UNIT_ECONOMICS_W03_CONTRACTS_ARCHITECTURE_2026-10-28.md`, `DECISIONS_064.md`.
- Если spec PR открыт, старт разрешён от его проверенного HEAD с явно зависимым stacked PR; ожидание предварительного merge не является блокером.
- Production bot, Ozon API, .env и owner database не использовались.
- Новые режимы экономики/эксперимента пока не реализованы; описанные схемы и acceptance — требования.
- Прежние Q00–Q35 и исправления R1–R8 находятся в main; не переоткрывать их как новую реализацию.
- Decision 064 фиксирует W03 design; runtime/schema реализация pending, не считать этапы W04–W39 уже проверенными.

## Этапы

| Этап | Зависимости | Статус | Фактический результат / проверки |
|---|---|---|---|
| W00 | — | DONE | 28.10.2026: проверены PR #721 (open, exact head `f76d2dd9…`, base main `9315046c…`), локальный checkout чистый; создана отдельная implementation branch от exact spec HEAD. Составлен baseline manifest без чтения содержимого owner data; tracked `data/*.json`, ignored `data/tenants/`, `.env` и локальные базы не включались/не изменялись. Evidence: `UNIT_ECONOMICS_W00_BASELINE_2026-10-28.md`. Runtime tests не запускались: W00 не меняет код. |
| W01 | W00 | DONE | 28.10.2026, incoming HEAD `4826a5fd…`: read-only trace from public menu/callbacks through scenario source/calculator, finance/returns/performance/cross-docking/storage/COGS evidence and tenant planning repository. Added lineage matrix with dates, identity, denominator, completeness and exact consumer; documented multi-SKU `net_accrual` and finance `sales_count` semantics, price-history gap, separate allocation models and unimplemented experiment flow. Evidence: `UNIT_ECONOMICS_W01_DATA_LINEAGE_AUDIT_2026-10-28.md`. No runtime changes, tests not run (audit-only), owner data/API/bot untouched. |
| W02 | W01 | DONE | 28.10.2026, incoming HEAD `886aa440…`: сверены официальные Ozon developer/API публикации и текущие клиентские запросы. Зафиксированы новые finance endpoints/deprecation, Analytics no-Premium metric/лимиты, finance cursor пример, returns fields/has_next sample, supply v3, product prices v5 migration и Performance current/history distinction. Параметры/лимиты, которых официальные материалы не подтверждают, помечены UNVERIFIED/UNSUPPORTED; официальный docs SPA недоступен текстовому reader. Новых code/tests нет; реальные запросы/credentials/owner data не использовались. Evidence: `UNIT_ECONOMICS_W02_OZON_API_CONTRACT_AUDIT_2026-10-28.md`. |
| W03 | W01,W02 | DONE | 28.10.2026, incoming HEAD `80395612`: закреплены versioned ExpenseSnapshot/Component, QuantityEvidence, ExtendedScenario, experiment/phase/result contracts; exact scope, ownership, absent-vs-zero, dedup/correction, gate order and source limitations. Added explicit experiment transition table, atomic active-observation guard, CAS/idempotency, additive DB v5→v6 plan, 64KiB record/10-row page and finite 100/10/20 quotas, shared 120s/128-request ceiling, and 12 synthetic fixture seeds. Decision 064 records architecture while marking implementation pending. No runtime/schema/tests changed; no live API, bot or owner data used. Evidence: `UNIT_ECONOMICS_W03_CONTRACTS_ARCHITECTURE_2026-10-28.md`. |
| W04 | W03 | DONE | 28.10.2026, branch `codex/full-unit-economics-experiments-implementation-20261028`, incoming code HEAD `aae26f899458df3c2a86dfab6814b2915f0b4611`: independently recalculated numeric/behavioral oracles N01–N18 and checked legacy calculator/TaxService outputs. 22 existing baseline suites passed: **334 passed in 6.97s** on Python 3.12.10/pytest 8.4.2 in disposable checkout and synthetic storage. Initial local attempt lacked IANA tzdata in the venv; rerun used already-installed local zoneinfo via `PYTHONTZPATH`, with no project dependency/code change. `git diff --check` passed and `git diff -- data` was empty. New code/regressions are not claimed. Evidence: `UNIT_ECONOMICS_W04_NUMERIC_ORACLES_2026-10-28.md`. |
| W05 | W03,W04 | DONE | 28.10.2026, branch `codex/full-unit-economics-experiments-implementation-20261028`, incoming code HEAD `f3576fbc`: добавлен pure `UnitEconomicsExpenseNormalizer` для exact scope/window, signed Decimal money, source/component subparts, idempotent dedup/conflict, ownership ledger и page coverage gates; raw IDs/rows не выходят из функции. Regression profile с соседним existing observation normalizer: **29 passed in 0.52s**; `py_compile`, `git diff --check` PASS; owner data не менялись, live API не вызывался. Evidence: `UNIT_ECONOMICS_W05_NORMALIZER_2026-10-28.md`. |
| W06 | W05 | DONE | 28.10.2026, incoming code HEAD `ebe40128`: добавлен чистый `UnitEconomicsAdvertisingEvidenceService`, который принимает только нормализованные snapshot contracts. Явные финансовые CPC/CPO/OTHER — primary; Performance CPC — только сверка и не добавляется к финансовой сумме. Неизвестный/mismatched component key/category, partial page, account-level и window-allocation блокируют SKU total; account expenses остаются отдельно даже при нулевой сумме после corrections. RUB/unit требует complete exact SKU scope, recurring confirmed origin, positive compatible denominator и compatible date window; absolute spend не ограничен ценой. Добавлено `ADVERTISING_OTHER` в category contract. Адресный Windows/Python 3.12.10 профиль: **90 passed in 1.77s** на W06/W05/observation normalizer и трёх связанных legacy advertising suites. No Ozon API/owner data/bot; acceptance: `UNIT_ECONOMICS_W06_ADVERTISING_RECONCILIATION_2026-10-28.md`. |
| W07 | W05 | DONE | 28.10.2026, incoming code HEAD `db5bb230`: добавлен pure `UnitEconomicsReturnEvidenceService` для явных return/non-buyout finance components, exact delivered→returned→retained quantity, отдельного inventory disposition/COGS и non-overlapping compensation. Несовпадение числа, owner/store/SKU/cohort, неполные страницы, unknown/pending disposition, credits и отсутствующая комиссия блокируют strict RUB/unit; суммы по posting/средние и row count не используются. Optional opaque 256-bit `cohort_ref` добавлен обратно совместимо в нормализатор и W03 контракт; adapter обязан создавать случайный токен только после доказанной transient связи, сырой ID не сохраняется. W07 fixtures проходят через нормализатор. Связанный изолированный Windows/Python 3.12.10 профиль: **115 passed in 1.89s**; финальный прогон после исправления regression assertions/import. Acceptance: `UNIT_ECONOMICS_W07_RETURN_COHORTS_2026-10-28.md`. Реальные источники/коллектор не подключены; data/.env/DB, Ozon и бот не использовались. |
| W08 | W05 | DONE | 28.10.2026, incoming code HEAD `c59ab11a`: добавлен pure `UnitEconomicsAdditionalExpenseEvidenceService` с disjoint `STORAGE`/`PLACEMENT`/delegated cross-docking buckets и hashed immutable map только для явно разрешённых `OTHER_SERVICE`. Необработанные key/category conflicts, account/unattributed, partial source, base overlaps и one-off/credit не становятся применимой recurring суммой; exact SKU и window-allocation numerator раздельны, единичная ставка не вычисляется до W09. Missing отличается от confirmed zero. Combined isolated Windows/Python 3.12.10 profile W08/W07/W06/W05/observation normalizer: **89 passed in 1.23s**. `py_compile`, `git diff --check`, line-length scan PASS; `git diff -- data` пустой. Acceptance: `UNIT_ECONOMICS_W08_STORAGE_ADDITIONAL_EXPENSES_2026-10-28.md`. API adapters не добавлены, SKU storage source не подтверждён; user data, Ozon и бот не затронуты. |
| W09 | W06,W07,W08 | DONE | 29.10.2026, branch `codex/full-unit-economics-experiments-implementation-20261028`, incoming code HEAD `fb78bfa8`: добавлен bounded `UnitEconomicsWindowSnapshotService`: точные 56 завершённых локальных дат, отдельный phase window, observed bounds/coverage, safe fingerprints, weighted сумма подтверждённых расходов / сумма совместимых единиц по непересекающимся сегментам, zero-denominator/short-history/incomplete/mixed-denominator gates. Sequential normalized-evidence readers используют child `PeriodProfitOperationTrace` с ≤120 секунд и ≤128 HTTP попыток на всю операцию, включая ранее использованный parent count; attempts/лимиты не обнуляются, общий normalized evidence ограничен 64 KiB, retries автоматом нет, 429/time/request/evidence limit останавливают следующие readers. 16 regressions. Combined isolated W05–W09/trace profile: **116 passed in 1.80s**; `py_compile`, `git diff --check` PASS; `git diff -- data` пустой. Реальных Ozon/Telegram запросов, .env, owner DB/data и реального бота не было. W09 acceptance: `UNIT_ECONOMICS_W09_WINDOW_SNAPSHOTS_2026-10-28.md`; provider-specific adapters pending. |
| W10 | W09 | NOT_STARTED | — |
| W11 | W03,W10 | NOT_STARTED | — |
| W12 | W07,W11 | NOT_STARTED | — |
| W13 | W11,W12 | NOT_STARTED | — |
| W14 | W06,W11 | NOT_STARTED | — |
| W15 | W13,W14 | NOT_STARTED | — |
| W16 | W15 | NOT_STARTED | — |
| W17 | W03,W10 | NOT_STARTED | — |
| W18 | W16,W17 | NOT_STARTED | — |
| W19 | W18 | NOT_STARTED | — |
| W20 | W19 | NOT_STARTED | — |
| W21 | W17,W19 | NOT_STARTED | — |
| W22 | W16,W21 | NOT_STARTED | — |
| W23 | W22 | NOT_STARTED | — |
| W24 | W22,W23 | NOT_STARTED | — |
| W25 | W24 | NOT_STARTED | — |
| W26 | W24,W25 | NOT_STARTED | — |
| W27 | W26 | NOT_STARTED | — |
| W28 | W20,W27 | NOT_STARTED | — |
| W29 | W28 | NOT_STARTED | — |
| W30 | W10,W18 | NOT_STARTED | — |
| W31 | W24,W25,W30 | NOT_STARTED | — |
| W32 | W29,W31 | NOT_STARTED | — |
| W33 | W20,W32 | NOT_STARTED | — |
| W34 | W33 | NOT_STARTED | — |
| W35 | W34 | NOT_STARTED | — |
| W36 | W35 | NOT_STARTED | — |
| W37 | W36 | NOT_STARTED | — |
| W38 | W37 | NOT_STARTED | — |
| W39 | W38 | NOT_STARTED | — |

## Правила записи результата этапа

Статусы: NOT_STARTED, IN_PROGRESS, VERIFIED_EXISTING, DONE, BLOCKED. BLOCKED содержит конкретное внешнее условие и независимую работу, которую можно продолжить. VERIFIED_EXISTING допустим только при доказательстве, что существующая реализация полностью удовлетворяет приёмке.

Для каждой записи:

1. Дата, этап, branch/base/code SHA, входной контракт.
2. Реальные изменения и paths, результат/изменённое поведение.
3. Новые regressions, точные команды и exit/result; старое зелёное CI не переносится.
4. Окружение и изоляция, owner data status.
5. Непроверенные источники и ограничения.
6. Следующий этап и необходимость business decision, если есть.

## Регистр источников и решений

| Вопрос | Текущее состояние | Где разрешается |
|---|---|---|
| Retained cohort / exact return-to-sale quantity | Не подтверждён для нового режима | W01–W03,W07,W12 |
| Вся реклама и SKU allocation | CPC и account totals нельзя складывать; новый coverage contract ещё не реализован | W02,W05,W06 |
| Дополнительные услуги против base fees | Требуется disjoint ownership | W05,W08 |
| TaxService и extra gross profit | Сохранить существующую политику; numeric oracle обязателен | W11,W13 |
| Единый active SKU guard | Observation guard существует; experiment integration ещё не реализована | W17,W21 |
| Maturity/30 units/7 days | Операционные ограничения модели, не статистическая гарантия | W22,W27,W28 |

### W02 supported-source boundary

- Seller Analytics без Premium: официально подтверждены revenue/ordered_units и API cadence; `cancellations`, `returns`, `delivered_units` в no-Premium flow не считаются доступными.
- Ozon forum examples — evidence того, что поля встречались в опубликованных ответах, но не полная schema. `visual_status_change_moment`, return type/status enums и cursor completeness не повышать до официальной гарантии.
- Historical seller price per successful sale, universal SKU-level storage, full supply-act confirmation, and exact historical ad CSV mapping remain unsupported/unverified; continue using explicit unavailable/coverage statuses.

## Подготовка ТЗ

- Прочитаны существующие roadmap, реестр возможностей, архитектурные решения, scenario/tax/returns/planning/observation contracts.
- Подготовлены 40 этапов с dependency graph и 18 групп acceptance.
- Offline проверки подготовки прошли: 40 уникальных упорядоченных стадий, ациклический граф, exact match зависимостей task/journal и 40 NOT_STARTED, 18 acceptance groups, 58 существующих опорных путей. Устаревшая ссылка period_profit_service.py заменена на действующий period_profit_query_service.py до публикации.
- Numeric oracles через существующий pure canonical calculator: base profit 46.00; USN income 40.00; income с points20 — 41.20; income-minus-expenses — 39.10; candidate95/ads7 — 46.50. Дополнительные расходы в этих проверках арифметически сведены к сумме затрат только как oracle, это не будущая реализация подмены поля cost. Loss pool=350, extra/unit=5 и weighted200/110=1.82 проверены Decimal.
- git diff --check прошёл; git diff -- data пустой. Новых code/tests нет; branch подготовки содержит только документацию. CI этой документационной ветки будет привязан к опубликованному SHA.
- Полный pytest не выполнялся для новой реализации: она не начиналась. Проверки подготовки не закрывают этапы W00–W39.

## W02 проверки и ограничения

- W02 — read-only source audit, без runtime и тестовых изменений. Официальные Ozon links и уровень подтверждения сведены в `UNIT_ECONOMICS_W02_OZON_API_CONTRACT_AUDIT_2026-10-28.md`.
- Официальные материалы подтверждают выбор источников, но не все используемые кодом request/response детали; такие детали оставлены UNVERIFIED. Публичный docs SPA не извлекается через текстовый reader.
- Выполнены локальные `rg`-проверки API clients/services, официальный web search по `dev.ozon.ru`, `git diff --check` и проверка `git diff -- data`; API calls/tests: 0.
- Следующее после W03: W04 независимые numeric oracles и baseline связанных старых test suites.

# Changelog

Все значимые изменения проекта фиксируются в этом файле.

## 2026-08-29 — Product Task Freshness Evidence Contract v1

- product task drafts now preserve optional source-recorded freshness timestamps from product decisions;
- observation/retrieval timestamps are stored separately and never count as proof of source freshness;
- no source timestamp is generated, inferred, or substituted from request/cache/draft time;
- legacy decisions without freshness evidence remain compatible and evaluate unsupported source age as `UNKNOWN`;
- targeted freshness evidence and freshness guard validation: `15 passed`;
- full repository suite intentionally not rerun under the reduced full-suite cadence; previous full checkpoint remains `392 passed`;
- no Product Decision rule, execution permission, Action Executor connection, or Ozon mutation path changed.

## 2026-08-29 — Development Autopilot Vector Memory v1

- added `AssistantVectorMemoryService` for similarity-based development context lookup;
- default embeddings are deterministic and local with no network or paid API dependency;
- added cosine-similarity search with result limits and minimum-similarity filtering;
- supports constructor injection of a future richer embedding provider without changing the memory API;
- stored and returned payloads are deep-copy isolated;
- embedding dimension mismatches fail explicitly;
- targeted vector-memory tests passed;
- full repository suite intentionally not rerun for this isolated feature under the reduced full-suite cadence;
- previous full regression checkpoint remains `392 passed` from the preceding Self-improvement Cycle stage;
- no Product Decision execution, Action Executor connection, Ozon mutation, or business execution wiring was changed.

## 2026-08-29 — Self-improvement Cycle v1

- closed the production learning loop from execution feedback into shared memory and back into subsequent planning and action generation;
- production planning and action generation now use the same `AssistantMemoryService` instance as feedback;
- added integration coverage for `feedback → memory → next plan/action` and unrelated-action isolation;
- targeted self-improvement tests passed;
- full repository validation: `392 passed`;
- no recommendation/replanning algorithm or task execution semantics were changed;
- no Product Decision execution, legacy Action Executor connection, or mutating Ozon path was enabled.

## 2026-08-29 — Long-running Task Recovery validation

- validated restart recovery for persisted long-running tasks;
- in-progress pending actions remain recoverable after service restart;
- paused/resumed state and completed progress survive restart;
- recovery selects the next unfinished action without executing anything implicitly;
- added four restart/recovery regression tests;
- full repository validation: `388 passed`;
- no Product Decision execution, legacy Action Executor connection, or mutating Ozon path was enabled.

## 2026-08-29 — Product Task Draft Data Freshness Guards v1

- added a separate read-only `ProductTaskDraftFreshnessService`;
- freshness is reported as `FRESH`, `STALE`, or `UNKNOWN`;
- persisted `decision_recorded_at` is used as the real decision-snapshot timestamp;
- sales, stock, and unit-economics timestamps remain `UNKNOWN` when the current source contracts do not provide a reliable timestamp;
- review readiness now requires proven fresh source data when the freshness guard is wired;
- no timestamp is fabricated from request time, cache time, or draft update time;
- execution remains unavailable: `execution_ready=False`, `executed=False`, and no Action Executor or Ozon mutation path is connected.

## 2026-08-28 — Product Task Draft Readiness Checklist v1

- added proposal-specific factual checks for manual draft review;
- review readiness is separated from execution readiness;
- missing facts are reported without inferred replacement values;
- execution remains blocked by the disconnected workflow and explicit
  proposal-specific policy gaps;
- Telegram detail cards show missing data and execution blockers;
- review queue summary shows review-ready and refresh-required counts while
  executable count remains zero.

## 2026-08-28 — Product Task Draft Detail and Audit v1

- review queue items open a dedicated draft detail card;
- cards show source decision metrics, lifecycle state, timestamps, and the
  explicit non-executable boundary;
- new drafts keep append-only lifecycle events for real state transitions;
- idempotent repeated commands do not create duplicate audit events;
- legacy drafts remain readable and explicitly report unavailable old history;
- archived drafts expose no further lifecycle controls.

## 2026-08-28 — Product Draft Review Queue Prioritization v1

- added a separate deterministic prioritizer for reviewable product drafts;
- queue order considers draft freshness, source decision priority, and review
  type;
- closed and dismissed records are excluded from the review queue;
- equal scores use oldest-first ordering to prevent starvation;
- Telegram shows priority counts, Russian explanations, and priority icons;
- prioritization remains read-only and never changes decision or draft state.

## 2026-08-28 — Product Task Draft Review Lifecycle v1

- active drafts become stale when the current product decision snapshot or
  actionable proposal changes;
- legacy stored drafts receive compact review identifiers;
- active, stale, and dismissed drafts can be archived from Telegram;
- archived drafts are terminal and repeated confirmation does not reopen them;
- draft summaries distinguish active, stale, dismissed, and archived states;
- lifecycle operations remain non-executable and do not call Ozon.

## 2026-08-28 — Confirmed Product Task Drafts v1

- confirmed actionable proposals create persistent product task drafts;
- one draft is created per decision snapshot and repeated confirmation is
  idempotent;
- dismissing the proposal closes its matching draft;
- Telegram exposes a draft summary and the draft state on product card;
- task drafts always keep `execution_allowed=False` and `executed=False`;
- existing task executors and Ozon APIs are not connected.

## 2026-08-28 — Product Action Proposal Confirmation v1

- actionable product proposals can be confirmed or dismissed in Telegram;
- status is attached to the latest stored decision snapshot and repeated input is
  idempotent;
- stale proposals are rejected against the latest stored decision;
- every confirmation result explicitly keeps `executed=False` and
  `execution_allowed=False`;
- confirmation records intent only; no Action Executor or Ozon mutation is
  connected.

## 2026-08-28 — Product Decisions v3

- добавлен сводный обзор решений по ассортименту;
- товары сортируются по приоритету и дням запаса;
- Telegram показывает количество решений каждого типа;
- кнопки содержат артикул продавца и краткое действие;
- правила решений и автоматическое выполнение действий не изменены.

### Product Decisions v4 — cache and pagination

- successful product decisions are cached for 10 minutes;
- errors and insufficient-data decisions are never cached as fresh data;
- cached results are protected from mutation by callers;
- assortment overview is split into pages of eight products;
- Telegram navigation preserves existing product callbacks.

### Product Decision Memory v1

- added persistent history of successful product decisions;
- identical repeated decisions do not create duplicate records;
- decision type or priority changes create a new snapshot;
- history keeps up to 50 changes per seller article;
- Telegram cards explain transitions from the previous decision;
- decision history remains observational and does not execute actions.

### Product Decision Feedback v1

- decision cards offer manual `Useful` and `Not relevant` feedback;
- feedback is attached to the latest stored decision snapshot;
- repeated feedback is idempotent;
- invalid feedback and missing decision history are rejected safely;
- feedback is stored as a learning signal but does not alter recommendations.

### Product Decision Outcome Correlation v1

- the next changed decision is correlated with prior manual feedback;
- lower urgency, higher urgency, and same-priority changes are distinguished;
- no outcome is inferred when prior feedback is absent;
- Telegram presents the result as an observation, not proven causation;
- correlated outcomes remain read-only learning data.

### Product Decision Learning Summary v1

- added assortment-wide learning counts for snapshots, feedback, and outcomes;
- added a Telegram learning-summary entry from the product decision overview;
- added per-product access to the latest five decision changes;
- history displays translated decisions, priorities, feedback, and observations;
- summary deliberately avoids success-rate claims and causal conclusions.

### Safe Product Action Proposals v1

- added a separate proposal service for product decisions;
- replenishment, unit-economics, and margin reviews require confirmation;
- hold-stock decisions produce monitoring-only proposals;
- every proposal explicitly prohibits automatic execution;
- Telegram cards show the next manual step;
- assortment overview counts proposals requiring manual review.

---

# Версия 0.1.0-dev
Дата: 07.08.2026

## Экономика товара и магазина

### Добавлено

#### ProductCostService

- хранение себестоимости товара в SQLite;
- Product ID;
- SKU;
- Offer ID;
- стоимость единицы;
- валюта;
- дата обновления.

#### ProfitService

Рассчитывает:

- выручку;
- себестоимость проданных товаров;
- чистое начисление Ozon;
- валовую прибыль;
- прибыль на единицу;
- маржинальность.

Маржинальность рассчитывается относительно выручки.

#### ProfitDashboardService

Добавлен отдельный AI Profit Dashboard для товара.

#### StoreProfitService

Добавлена агрегированная экономика магазина:

- продажи;
- общая выручка;
- чистое начисление Ozon;
- общая себестоимость;
- валовая прибыль;
- маржинальность;
- количество прибыльных товаров;
- количество убыточных товаров.

#### StoreProfitDashboardService

Добавлен итоговый AI Store Profit Dashboard.

---

## Ozon API

Улучшена устойчивость API-клиента:

- обработка HTTP 429;
- повтор запросов;
- пауза между попытками;
- поддержка Retry-After;
- повтор при таймаутах и временных ошибках соединения.

---

## Отчёты

Summary Report теперь включает:

- финансовую аналитику Ozon;
- экономику товара;
- себестоимость;
- валовую прибыль;
- прибыль на единицу;
- маржинальность.

---

## Тестирование

Добавлены отдельные тесты:

- `test_profit.py`
- `test_store_profit.py`

Общее количество автотестов:

**20**

Все тесты проходят успешно.

---

# Версия 0.0.1
Дата: 06.08.2026

## Первый стабильный этап

### Реализовано

#### Ozon Seller API

- получение списка товаров;
- получение информации о товаре;
- получение реальных FBO-остатков;
- получение финансовых начислений;
- получение справочника типов начислений.

#### AI-аналитика

- Risk Analyzer;
- Health Score;
- Health History;
- Health Trend;
- Product Memory;
- Stock Forecast;
- Prediction Service;
- KPI Dashboard;
- Decision Engine;
- Action Service;
- Action Automation.

#### Финансы

- FinanceService;
- FinanceDashboardService;
- выручка;
- комиссия Ozon;
- логистика;
- эквайринг;
- чистое начисление Ozon;
- фильтрация по SKU;
- расшифровка типов начислений.

#### Отчёты

- TXT Summary Report;
- AI Report;
- KPI Dashboard;
- Finance Dashboard.

#### База данных

- products;
- metrics;
- risks;
- health_history;
- actions;
- product_memory.

#### Автотесты

На этапе 0.0.1:

**12 автоматических тестов**

---

# Следующий этап

Планируется:

## Налоги

- TaxService;
- поддержка разных налоговых режимов;
- расчёт налога отдельно от ProfitService.

## Прибыль бизнеса

- BusinessProfitService;
- налог;
- реклама;
- дополнительные расходы;
- итоговая прибыль бизнеса.

## Далее

- AdvertisingService;
- StoreAnalyticsService;
- ABC-анализ;
- XYZ-анализ;
- рейтинг товаров;
- история прибыли;
- графики;
- AI-рекомендации по экономике;
- прогноз денежных потоков.

---

Конец журнала изменений.

## 2026-08-30 — Business Planner Result Integrity v575-v581

- `AssistantBusinessPlannerService` now preserves downstream failures instead of
  rewriting them as successful plans;
- malformed recommendation/planning/execution/task-create results fail closed;
- valid plans and general-only presentation behavior remain compatible;
- no new business execution or Ozon mutation path was added.

# Changelog

Все значимые изменения проекта фиксируются в этом файле.

## 2026-08-28 — Confirmed Product Task Drafts v1

- confirmed actionable proposals create persistent product task drafts;
- one draft is created per decision snapshot and repeated confirmation is
  idempotent;
- dismissing the proposal closes its matching draft;
- Telegram exposes a draft summary and the draft state on product cards;
- task drafts always keep `execution_allowed=False` and `executed=False`;
- existing task executors and Ozon APIs are not connected.

## 2026-08-28 — Product Action Proposal Confirmation v1

- actionable product proposals can be confirmed or dismissed in Telegram;
- status is attached to the latest decision snapshot and repeated input is
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

# Ozon AI Assistant

# Архитектура проекта

---

## Общая схема

```text
                        Ozon Seller API
                               │
                               ▼
                          OzonClient
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
   ProductService        MetricsService       FinanceService
          │                    │                    │
          │                    │                    ▼
          │                    │          FinanceDashboardService
          │                    │
          └──────────────┬─────┴────────────────────┐
                         ▼                          │
                AIOrchestratorService              │
                         │                          │
     ┌───────────────────┼───────────────────┐      │
     ▼                   ▼                   ▼      │
 RiskAnalyzer        HealthScore       ProductMemory
     │                   │                   │
     ▼                   ▼                   ▼
 HealthTrend       PredictionService   StockForecastService
                         │
                         ▼
                    KPIService
                         │
                         ▼
                  DecisionEngine

Экономический контур:

FinanceService
      │
      ▼
ProductCostService
      │
      ▼
ProfitService
      │
      ▼
ProfitDashboardService
      │
      ▼
StoreProfitService
      │
      ▼
StoreProfitDashboardService

Формирование отчёта:

AI / Metrics / Finance / Profit
              │
              ▼
     SummaryReportService
              │
              ▼
       TXT Summary Report
```

---

# Главный модуль

```text
app/main.py
```

Отвечает за:

- запуск приложения;
- инициализацию сервисов;
- последовательный вызов модулей;
- вывод информации в консоль;
- формирование итогов;
- сохранение Summary Report.

Бизнес-логика должна оставаться внутри отдельных сервисов.

---

# Источник данных

Используется официальный Ozon Seller API.

Через API получаются:

- список товаров;
- информация о товаре;
- FBO остатки;
- финансовые начисления;
- справочник типов начислений.

Используются методы:

```text
/v3/product/list
/v3/product/info
/v4/product/info/stocks
/v1/finance/accrual/by-day
/v1/finance/accrual/types
```

---

# API-клиент

## OzonClient

Файл:

```text
app/api/ozon_client.py
```

Отвечает только за взаимодействие с Ozon Seller API.

Реализованы:

- общие HTTP POST-запросы;
- заголовки авторизации;
- обработка ошибок;
- таймауты;
- повтор запросов;
- обработка HTTP 429;
- поддержка Retry-After.

Бизнес-расчёты внутри `OzonClient` не выполняются.

---

# Основные сервисы

## ProductService

Назначение:

- получение списка товаров;
- сохранение товаров в SQLite;
- загрузка товаров из базы.

---

## MetricsService

Получает метрики товара.

Использует:

- статус товара;
- архив;
- наличие FBO;
- наличие FBS;
- FBO всего;
- резерв;
- доступный остаток.

---

# AI-контур

## AIOrchestratorService

Координирует основной AI-анализ товара.

Использует:

- Risk Analyzer;
- Health Score;
- Health Trend;
- Product Memory;
- Stock Forecast;
- Prediction Service;
- KPI Service;
- Decision Engine.

---

## Risk Analyzer

Оценивает уровень риска товара.

---

## Health Score

Рассчитывает здоровье товара.

---

## Health History

Сохраняет историю Health Score.

---

## Health Trend

Сравнивает текущее и предыдущее состояние здоровья.

---

## Product Memory

Сохраняет ежедневный снимок товара.

В память входят:

- Health Score;
- Risk Score;
- наличие FBO;
- наличие скидки;
- FBO всего;
- FBO резерв;
- FBO доступно.

---

## Stock Forecast Service

Использует историю Product Memory.

Рассчитывает:

- изменение остатков;
- средний расход;
- прогноз количества дней запаса;
- статус запаса.

---

## Prediction Service

Формирует прогноз состояния товара.

---

## KPI Service

Рассчитывает:

- AI Score;
- состояние FBO;
- процент резерва;
- изменение остатка;
- итоговую оценку товара.

---

## Decision Engine

Формирует рекомендации и действия для продавца.

---

# Финансовый контур

## FinanceService

Файл:

```text
app/services/finance_service.py
```

Работает с ежедневными начислениями Ozon.

Рассчитывает:

- выручку;
- комиссию Ozon;
- логистику;
- эквайринг;
- прочие начисления;
- чистое начисление Ozon.

Фильтрация выполняется по SKU.

---

## FinanceDashboardService

Отображает финансовую аналитику в консоли.

Показывает:

- дату;
- SKU;
- количество операций;
- товарные начисления POSTING;
- выручку;
- комиссию;
- логистику;
- эквайринг;
- чистое начисление;
- детализацию начислений.

---

# Экономический контур

## ProductCostService

Файл:

```text
app/services/cost_service.py
```

Отвечает за себестоимость товара.

Хранит:

- Product ID;
- SKU;
- Offer ID;
- себестоимость;
- валюту;
- дату обновления.

Себестоимость сохраняется в SQLite.

---

## ProfitService

Файл:

```text
app/services/profit_service.py
```

Рассчитывает экономику одного товара.

Использует:

```text
FinanceService
+
ProductCostService
```

Рассчитывает:

- выручку;
- количество продаж;
- себестоимость одной единицы;
- себестоимость проданных товаров;
- чистое начисление Ozon;
- валовую прибыль;
- прибыль на единицу;
- маржинальность.

Формула:

```text
Валовая прибыль =
Чистое начисление Ozon
− Себестоимость проданных товаров
```

Маржинальность:

```text
Маржинальность =
Валовая прибыль
/
Выручка
× 100%
```

Налоги, реклама и внешние бизнес-расходы пока не учитываются.

---

## ProfitDashboardService

Отображает экономику отдельного товара.

Показывает:

- количество продаж;
- себестоимость;
- чистое начисление;
- валовую прибыль;
- прибыль на единицу;
- маржинальность.

---

# Аналитика магазина

## StoreProfitService

Агрегирует результаты `ProfitService` по всем обработанным товарам.

Рассчитывает:

- количество продаж магазина;
- общую выручку;
- общее чистое начисление Ozon;
- общую себестоимость;
- валовую прибыль магазина;
- маржинальность;
- количество прибыльных товаров;
- количество убыточных товаров.

Ошибочные результаты отдельных товаров пропускаются и не ломают общий расчёт.

---

## StoreProfitDashboardService

Отображает итоговую экономику магазина после завершения обработки товаров.

Показывает:

- продажи;
- чистое начисление Ozon;
- себестоимость;
- валовую прибыль;
- маржинальность;
- прибыльные товары;
- убыточные товары.

---

# Actions

## ActionService

Создаёт действия на основе решений AI.

---

## ActionDashboardService

Показывает историю действий.

---

## ActionAutomationService

Выполняет автоматизируемые действия.

---

# Summary Report

## SummaryReportService

Создаёт TXT-отчёт по каждому товару.

В отчёт входят:

- здоровье;
- риск;
- KPI;
- FBO остатки;
- AI Memory;
- прогноз остатков;
- финансы Ozon;
- экономика товара;
- AI-прогноз;
- итоговое заключение.

---

# База данных

Используется SQLite.

Файл:

```text
ozon_assistant.db
```

Основные таблицы:

```text
products
metrics
risks
health_history
actions
product_memory
product_costs
```

---

# Основной поток данных

```text
Ozon Seller API
        │
        ▼
    OzonClient
        │
        ├──────────────► ProductService
        │
        ├──────────────► MetricsService
        │
        └──────────────► FinanceService
                              │
                              ▼
                       Финансовые данные
                              │
                  ┌───────────┴───────────┐
                  ▼                       ▼
          AIOrchestratorService     ProductCostService
                  │                       │
                  ▼                       ▼
              AI-анализ              ProfitService
                  │                       │
                  │                       ▼
                  │               Profit Dashboard
                  │                       │
                  └───────────┬───────────┘
                              ▼
                     SummaryReportService
                              │
                              ▼
                       TXT Summary Report
```

---

# Поток экономики магазина

```text
Profit товара 1
Profit товара 2
Profit товара 3
       │
       ▼
StoreProfitService
       │
       ▼
StoreProfitDashboardService
```

---

# Тестирование

Используется:

```text
unittest
```

Запуск всех тестов:

```text
python -m unittest discover -v
```

На текущий момент:

```text
20 автоматических тестов
```

Покрыты:

- Risk Analyzer;
- Health Score;
- Decision Engine;
- Prediction Service;
- KPI Service;
- FinanceService;
- ProfitService;
- StoreProfitService.

Тесты финансов и прибыли не используют реальные запросы Ozon API.

---

# Git

Используется Git.

Основная ветка:

```text
main
```

Настроен:

```text
.gitignore
```

Не отслеживаются:

- `.env`;
- SQLite базы;
- отчёты;
- логи;
- `__pycache__`;
- `*.pyc`.

---

# Принципы архитектуры

1. Один сервис — одна ответственность.
2. `OzonClient` отвечает только за API.
3. Бизнес-логика находится в сервисах.
4. `main.py` координирует работу модулей.
5. Экономика товара отделена от финансов Ozon.
6. Себестоимость хранится отдельно.
7. Налоги не должны встраиваться напрямую в ProfitService.
8. Ошибка одного товара не должна ломать аналитику магазина.
9. Новая функциональность должна сопровождаться тестами.
10. Завершённые этапы фиксируются в Git и документации.

---

# Следующее расширение архитектуры

Планируется добавить:

```text
TaxService
BusinessProfitService
AdvertisingService
StoreAnalyticsService
ABCAnalysisService
XYZAnalysisService
```

Планируемый экономический поток:

```text
FinanceService
      │
      ▼
ProfitService
      │
      ▼
TaxService
      │
      ▼
AdvertisingService
      │
      ▼
BusinessProfitService
      │
      ▼
StoreAnalyticsService
```

После этого система сможет перейти от валовой прибыли после Ozon и себестоимости к полноценной оценке прибыли бизнеса.

## Локальный lifecycle Telegram polling

Production startup remains `start_bot.ps1` → `.venv` Python →
`python -m telegram_api_bot` → `telegram_app_layer.telegram_api_bot.main()`.
`build_application()` remains a pure composition step: it registers handlers and
PTB lifecycle callbacks without starting network traffic or acquiring an instance
lock.

`BotInstanceLease` owns one OS kernel lock per SHA-256 fingerprint of the configured
Telegram token. The plaintext token is not used as a file name, stored in the
metadata, or shown by local status commands. Persistent lifecycle files live in the
current user's LocalAppData on Windows, or in XDG runtime/private user state on
POSIX. The lock handle stays open for the polling process lifetime, so two checkouts
using the same token contend for the same lock while distinct bots remain
independent.

Lifecycle metadata is an atomic, schema-versioned local projection with a random
process generation, validated build revision, UTC start time, launch mode, state,
and (while active) a random loopback control secret and ephemeral port. On POSIX,
the directory and files use owner-only permissions. On Windows, the state directory
is under the current user's LocalAppData ACL boundary. The secret is never printed.
The kernel lock decides whether the process owns the instance; PID is descriptive
metadata only and is never used to signal or terminate a process.

State moves through `STARTING` → `RUNNING` → `STOPPING` → `STOPPED`. `RUNNING` is
published only when both the PTB updater is polling and the application is
processing updates. `status_bot.ps1` performs local checks without contacting
Telegram or Ozon. `stop_bot.ps1` sends a generation- and secret-bound request to
127.0.0.1, then waits up to 15 seconds for the kernel lock to become free. PTB's
`Application.stop_running()` and shutdown callbacks close the control server and
release resources. Timeout and invalid metadata fail closed; no process-wide
`python.exe` search or forced termination exists.

## Saved planning workspace

`PlanningWorkspaceRepository` adds owner/store-scoped plan tables to the existing
tenant SQLite database. Its schema is additive and versioned; transaction writes
use `BEGIN IMMEDIATE`, expected revisions and idempotency keys. The repository
accepts only allowlisted identities, planning inputs, source provenance and
historical calculation projections. It does not depend on Ozon clients or factual
seller-cost/finance repositories.

`SavedPlanningPlanService` owns the application contract and revalidates tenant
scope. `TelegramSavedPlanningPlanRuntimeService` owns bounded, expiring callback
actions and title-entry tickets, while the single/batch calculator runtimes keep
their current scenarios ephemeral. Saved reads use the historical projection and
never refresh external sources. Explicit refresh creates a new transient scenario;
the user may then save a new copy or append a revision with compare-and-swap. A
revision conflict never overwrites the latest plan. Archived, malformed and
future-schema records fail closed without deleting other plans.

`UnitPriceAdvertisingCapService` performs a bounded, source-free calculation on
the canonical one-sale scenario calculator. It validates monotonicity at fixed
rate probes, searches integer 0.01 percentage-point ticks, and confirms the
chosen boundary and its next tick. Single and batch Telegram adapters bind an
apply callback to the exact transient scenario or batch revision and re-run the
canonical calculation before changing only the local advertising assumption.
Saved historical plans display read-only caps; they cannot directly apply a
historical value.

`SalesMixPlanningService` multiplies rounded one-sale monetary components from
the same scenario calculator by user-entered successful-sale quantities. It
keeps per-SKU pre-tax contributions separate from period-level fixed expenses,
then calls the existing `TaxService` once with aggregate revenue, profit and
discount points. Missing quantities remain unknown and suppress final group
profit/margin while retaining the confirmed subtotal. The saved-plan Telegram
runtime uses owner/store/revision-bound input tickets and requires a preview
and explicit confirmation before appending a revision with compare-and-swap.
It does not read Ozon sources or write factual seller records.

`PeriodProfitPlanFactComparisonService` is a pure projection over one finalized
selected-SKU result and an exact saved-plan revision. The SKU runtime resolves
only the current exact product/offer/SKU tuple, then calls the existing period
query once for the selected group. The result is stored in the existing
owner/store-scoped transient snapshot store. Details and exports read that
snapshot; they do not query Ozon again. Quantity and gross revenue remain
separate facts, and the revenue bridge is arithmetic only. Profit deltas are
suppressed when advertising, external expenses, or return COGS are not proven
to share the same selected-SKU scope.

`PlanningPlanReadinessService` projects calculation readiness, historical
assumptions, and fact-comparison state as separate dimensions. The saved-plan
Telegram runtime offers scoped links to one missing field or unknown sales
quantity. Quantity edits use a revision-bound ticket, preview, and explicit
compare-and-swap save; other plan input edits remain transient until the user
explicitly saves a plan. The readiness view does not refresh external sources or
write seller accounting facts.

`PlanningPlanComparisonService` compares two saved revisions in the same
owner/store scope. It reports input changes even when calculations cannot be
compared, while derived revenue/profit/margin deltas require a compatible
period, exact SKU set, tax policy and calculation version. Margin is compared
in percentage points. Historical comparison is source-free.

Planning report exports extend the existing `AnalyticsExportService`,
`AnalyticsExportSerializer` and Telegram document sender. Saved plan,
advertising cap, sales mix and plan-comparison files project the same bounded
snapshot as the visible view; plan/fact continues to use its canonical
finalized snapshot. User reports may contain the owner's business figures,
while support diagnostics remain a separate strict allowlist. Missing values
remain nullable with their status/reason, and historical inputs are never
presented as fresh Ozon data.

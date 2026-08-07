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
# Changelog

Все значимые изменения проекта фиксируются в этом файле.

---

# Версия 0.0.1
Дата: 06.08.2026

## Первый рабочий релиз

### Реализовано

#### Ozon Seller API

- Подключение к Ozon Seller API
- Получение списка товаров
- Получение информации о товаре
- Получение реальных FBO-остатков
- Получение ежедневных финансовых начислений
- Получение справочника типов начислений

---

#### Аналитика

Добавлены:

- Risk Analyzer
- Health Score
- Health History
- Product Memory
- Health Trend
- Stock Forecast
- Prediction Service
- KPI Dashboard
- Decision Engine
- Action Service
- Action Automation

---

#### Финансы

Добавлены:

- FinanceService
- FinanceDashboardService

Реализованы расчёты:

- выручки;
- комиссии Ozon;
- логистики;
- эквайринга;
- прочих начислений;
- чистого начисления Ozon.

Добавлены:

- фильтрация начислений по SKU;
- расшифровка типов начислений;
- отображение финансов в консоли;
- сохранение финансов в Summary Report.

---

#### Отчёты

Добавлены:

- TXT Summary Report
- KPI Dashboard
- AI Report
- Finance Dashboard

---

#### База данных

Созданы таблицы:

- products
- metrics
- risks
- health_history
- actions
- product_memory

---

#### Автотесты

Добавлены тесты:

- Risk Analyzer
- Health Score
- KPI
- Prediction Service
- FinanceService

Всего:

**12 автоматических тестов**

Все тесты проходят успешно.

---

# Следующая версия

Планируется реализовать:

## Экономика товара

- себестоимость;
- прибыль;
- маржинальность;
- прибыль по каждому товару.

## Аналитика магазина

- Dashboard магазина;
- ABC-анализ;
- XYZ-анализ;
- рейтинг товаров;
- анализ прибыли;
- рекомендации AI.

---

Конец журнала изменений.
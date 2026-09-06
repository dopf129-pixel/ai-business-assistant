# AI_HANDOFF.md

# Ozon AI Assistant

## Назначение

Этот документ предназначен для любого AI или разработчика,
который продолжит работу над проектом.

Перед внесением любых изменений необходимо полностью
прочитать PROJECT_STATUS.md.

Для текущей финансовой семантики Period Profit также обязательно прочитать
`docs/PERIOD_PROFIT_RECONCILIATION_2026-09-06.md`.

---

# Основные правила

Не изменять архитектуру без необходимости.

Вся новая логика должна добавляться отдельными сервисами.

main.py используется только как точка входа.

Основная бизнес-логика должна находиться внутри сервисов.

Ozon всегда READ-ONLY. Не менять цены, рекламу, остатки, карточки, поставки или иное состояние бизнеса.

Для seller-facing Period Profit денежным авторитетом является account-level Ozon finance. Каноническая формула:

```text
period_profit = account_net_accrual
              + exact_committed_return_cogs_if_valid
              - product_cost
              - configured_tax
```

`unknown != zero`. Return COGS нельзя восстанавливать без recognition / authorization / commit / no-double-counting gates. Отчёт должен оставаться `read_only=True`, `executed=False`.

---

# Перед началом работы

1. Прочитать PROJECT_STATUS.md.
2. Ознакомиться с ARCHITECTURE.md (если есть).
3. Прочитать актуальные reconciliation-документы для затрагиваемой финансовой логики.
4. Запустить полный Verify/тестовый контур для точного SHA.

Локальная вспомогательная команда проекта:

python run_tests.py

---

# После изменений

Обязательно:

1. пройти exact feature-head full Verify;
2. открыть PR и пройти full Verify на фактическом synthetic merge SHA;
3. squash merge;
4. пройти full Verify точного resulting main SHA;
5. синхронизировать документацию только с этим проверенным production main;
6. проверить docs branch;
7. проверить synthetic merge docs PR;
8. squash merge docs PR;
9. пройти Verify точного финального docs-main SHA.

Failed SHA остаётся failed навсегда; его verification evidence нельзя переносить на другой SHA.

Также убедиться, что проект запускается, и обновить PROJECT_STATUS.md / CHANGELOG или специализированный reconciliation-документ по затронутому контракту.

---

# Что нельзя ломать

Рабочие сервисы:

- ProductService
- MetricsService
- OzonClient
- AIOrchestratorService
- Risk Analyzer
- Health Score
- Product Memory
- KPI Dashboard
- Prediction Service
- Stock Forecast
- Decision Engine
- Summary Report
- FinanceService
- Period Profit read-only reporting

---

# Period Profit — актуальный доказанный контракт

Контрольная сверка `09.08.2026–31.08.2026` с официальным отчётом Ozon доказала:

- account net accrual = `141707.34 RUB`;
- signed `sale_amount` = `374328.93 RUB`;
- физических положительных sale events = `4072`;
- нулевые product-quantity начисления лояльности/партнёрских программ не являются отдельными проданными единицами;
- отрицательный возврат не является стандартной sale-Cogs единицей.

Базовая коррекция sale/unit semantics была выпущена в main `2eaaaa531f8e9be2e01d03aebafa0b9eadc3b203`: `sale_amount` сохраняется, а стандартный `sales_count` увеличивается только при `sale_amount > 0`.

Последующий live-регресс `Финансовые данные SKU недоступны` выявил отдельный контракт Ozon: в отдельных POSTING строках агрегат `sale_amount` может отсутствовать при наличии всех трёх явных компонент. Production main `32a740c6341feadf67979e43cba8fea47f2f75f5` разрешает восстановление только как `sale_price + bonus + coinvestment`. Явный `sale_amount` всегда имеет приоритет; `seller_price` никогда не используется как fallback; при отсутствии/невалидности любой компоненты расчёт по-прежнему fail-closed. Сырая диагностика сохраняет факт отсутствия исходного `sale_amount`.

Проверки текущего runtime-fix: exact feature head `0aa22d474de946fb184b6c4be443b84968a3801c` — Verify #1429 SUCCESS; PR #439 synthetic merge — Verify #1430 SUCCESS; production main `32a740c6341feadf67979e43cba8fea47f2f75f5` — Verify #1431 SUCCESS. SHA `c9a69b38c4adaf678e7a4765c8cea136dbe2f42b` с Verify #1428 остаётся FAILED навсегда и не является evidence.

Не возвращать старую подмену `sale_amount = seller_price` без новой строгой официальной сверки.

---

# Особенности проекта

Проект сейчас работает
в режиме FBO.

Логика FBS намеренно отключена.

Не возвращать рекомендации FBS
без отдельного решения.

---

# База данных

Используется SQLite.

Файл:

ozon_assistant.db

Все изменения структуры должны быть совместимы
с уже существующей БД.

Если требуется новая колонка —

использовать ALTER TABLE,
а не пересоздание таблицы.

---

# Стиль кода

Используется обычный Python.

Без сложных сокращений.

Каждый сервис отвечает только за одну задачу.

Методы небольшие.

Названия максимально понятные.

---

# Приоритет разработки

1. Не ломать существующее.
2. Не выдавать неизвестные финансовые значения за ноль.
3. Всегда писать regression-тесты на реальные классы операций.
4. Всегда завершать полный SHA-bound Verify lifecycle.
5. Всегда синхронизировать документацию с проверенным production main.

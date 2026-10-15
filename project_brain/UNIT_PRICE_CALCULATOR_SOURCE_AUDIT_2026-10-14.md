# U00 — аудит источников калькулятора цены

Дата: 2026-10-14  
Базовый код: `655b3a0` (`Complete P00-P08 milestones and resolve review findings (#694)`)  
Статус: **аудит завершён, источник U02 реализован и изолированно проверен**; live данные Ozon не запрашивались.

## Вывод для реализации

Калькулятор может использовать текущую карточку для цены продавца и FBO-процент комиссии как наблюдаемую оценку. Он не должен выдавать эту ставку за тарифную котировку для произвольной цены. Расходы доставки, последней мили и эквайринга пока вводятся вручную: действующая выборка делит агрегаты на счётчик строк финансовых товаров, а не подтверждённых единиц.

Историческая доля баллов потенциально вычислима по существующим daily accruals, но текущий агрегат не доказывает, что bonus явно присутствовал во всех подходящих строках. Поэтому U02 должен получить/добавить строгий source contract с completeness и exact SKU evidence. Если любой день неполный, есть неразрешённая identity, бонус отсутствует в eligible строке или имеется конфликт дубликатов, автооценка недоступна и пользователь вводит b вручную. Explicit zero отличается от unknown.

## Карта данных и семантика

| Поле | Текущий источник | Подтверждённое поведение / граница |
|---|---|---|
| SKU, offer id, product id, название | Каталог и существующий product lookup | Сохранять точную связку идентификаторов для выбранного товара и активного store; архивные/переименованные SKU не угадывать. |
| Цена продавца P0 | `CurrentProductEconomicsSource.get_product_prices` → `marketing_seller_price`, fallback `price` | Только начальное значение и сравнение. `price` также доступен как buyer-price; не подменять им seller price. |
| FBO комиссия | `commissions.sales_percent_fbo` / FBO entry из product prices | Текущий наблюдаемый процент; умножать на новую P как оценку, явно сообщать, что цена/тарифные интервалы могут изменить ставку. Не применять к FBS. |
| Валовая сумма G, баллы B | `FinanceService.get_daily_finance` → `_process_posting` | `commission.sale_amount` прибавляется к `gross_sales`; `commission.bonus` отдельно аккумулируется как `discount_points`. Не прибавлять bonus к `sale_amount` повторно. Это подтверждено parser и тестовыми fixtures. |
| Полнота bonus | Текущий агрегат | В aggregate `discount_points` инициализирован нулём; отсутствие `bonus` в posting не помечает результат как incomplete. Он не годится без усиления контракта для вычисления автоматического b. |
| Финансовый `sales_count` | `FinanceService._process_posting` | Увеличивается на один для каждой положительной product row. Это не штуки и не подтверждённый per-unit denominator. |
| L/M/E | `CurrentProductEconomicsSource._finance_averages` | Складывает найденные fee breakdown и делит на `sales_count`; scope зависит от строк, допускает отсутствующие дни/fees и не подтверждает единицы. Не переиспользовать в сценарии как ₽/шт. |
| Налоговый режим/ставки | `TaxConfigurationService.get_policy` активного store; `TaxService.calculate` | Поддерживаемые `NONE`, `USN_INCOME`, `USN_INCOME_MINUS_EXPENSES`; налоговая база доходов `max(0, G−B)`, доходы минус расходы используют действующие taxable profit и minimum-tax формулы. Незаданный режим недоступен, не подменяется 6%. |
| Tenant/cache | `get_current_tenant_user_id`, `make_store_tenant_scope`; `ProductUnitEconomicsQueryService._query_cache` | Существующий query cache не tenant-safe для повторного использования (offer/SKU key). Новый сценарий/snapshot cache обязан включать пользователя, store, SKU и версию сценария; ручные overrides изолировать. |
| Ozon HTTP | `OzonClient._post` + `PeriodProfitOperationTrace` через ContextVar | После PR #694 HTTP transport учитывает оставшийся budget и реальные попытки через `reserve_ozon_request`; для сценария открывать/передавать собственный operation trace 60 сек./64 попытки, в том числе повторы. Пересчёты не ходят в сеть. |
| Telegram | `unit_economics` меню → `AssistantButtonHandlerService` → `ProductUnitEconomicsQueryService`; каталожный выбор общий | Добавлять калькулятор в существующий раздел/селектор; handler оставлять делегирующим. Не менять factual query и его экран как сценарное значение. |

## Решения реализации, вытекающие из фактов

1. Для первого безопасного релиза L/M/E являются обязательными scenario inputs. Автоматически заполнить их можно будет только после появления проверенного quantity denominator и доказанного состава непересекающихся расходов.
2. Auto-b не строится из агрегата только потому, что у него есть число `discount_points`: U02 должен подтвердить полное чтение периода, exact SKU, пригодные положительные продажи, явные bonus и корректную идентичность/reversal semantics. Иначе b остаётся unknown до ввода пользователя.
3. Для неразрешённой комиссии, рекламы, себестоимости и баллов пользователь может ввести ручные значения. Пользовательский ноль — отдельное подтверждённое допущение.
4. Текущий factual unit economics query, buyer-price tax policy, returns impact и Performance advertising не входят в source truth планового сценария.
5. На дату аудита не выполнялись live запросы Ozon, не менялись данные продавца, API/карточка/цена и налоговая конфигурация.

## Проверки

- На `655b3a0`, Python 3.12, `PYTHONPATH=app`: семь тестовых модулей current product economics, production wiring и finance/tax regressions — **44 passed**.
- Это regression baseline, а не подтверждение полноты live Ozon данных.

## Реализованный U02 source contract

- `FinanceService.get_daily_discount_points_evidence(date, exact_sku)` добавляет evidence-ответ, не меняя прежний агрегат. Он различает missing bonus и явный 0, требует пагинацию до пустого `last_id`, валидирует конечные суммы и не включает отрицательные/нулевые продажи в когорту успешной продажи.
- Идентификатор дедупликации — точные `posting_number + finance_sku`. Полностью идентичные суммы повторной строки учитываются один раз; различающиеся суммы для ключа делают день incomplete.
- `UnitPriceScenarioSource` читает 28 полностью закрытых дат, валидирует активный tenant до любых reads, проверяет однозначную карточку и не принимает finance SKU aliases. Он выводит weighted `sum(bonus)/sum(sale_amount)` без unit denominator.
- Если день/пагинация/bonus/identity/сумма неполны либо нет положительной когорты, `suggested_inputs.discount_points_rate` остаётся `None`; ручной сценарий остаётся возможен. Никакое неизвестное значение не нормализуется к нулю.
- Snapshot cache: tenant scope + user + exact SKU, deep copies, 600-second TTL, 128-entry LRU, same-key in-flight deduplication. Refresh creates a new 60-second / 64-attempt operation trace; sources are read-only.
- Product current facts use current seller price and FBO rate only as labeled estimate. Cost is read from exact product-id RUB record. Missing current facts stay missing; plan fees L/M/E and advertising remain manual.
- Дата «вчера» определяется системным локальным календарём приложения (существующая проектная практика); внешняя IANA timezone database на Windows недоступна и новой зависимости не добавляли.

Проверки U02 на текущей ветке: scenario + finance/source + current-economics/tax regressions — **62 passed** (Python 3.12). Это fake-source verification; live Ozon data not requested.

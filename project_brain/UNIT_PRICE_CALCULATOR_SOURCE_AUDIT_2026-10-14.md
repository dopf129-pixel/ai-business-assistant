# U00 — аудит источников калькулятора цены

Дата: 2026-10-14  
Базовый код: `655b3a0` (`Complete P00-P08 milestones and resolve review findings (#694)`)  
Статус: **завершён**; live данные Ozon не запрашивались.

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

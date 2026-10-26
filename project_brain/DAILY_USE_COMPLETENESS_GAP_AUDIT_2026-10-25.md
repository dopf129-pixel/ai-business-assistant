# B00: аудит полноты и текущих действий — 25.10.2026

## Область проверки

Проверены существующие read-only projection и user paths на базе PR #712 head `698c9f8bb9c4b8f5acc6b4fdcb475c1062e658ea`: `PeriodProfitCompletenessViewService`, `PeriodProfitDiagnosticViewService`, support diagnostic snapshot/export, Return COGS blocker resolver, периодные callback snapshots и keyboard actions. Production services и расчётная формула в B00 не менялись.

## Что уже работает

| Область | Подтверждённый путь | Текущее поведение |
|---|---|---|
| Период и вход | `app/period_profit_completeness_view.py` | Принимается только готовый profit result с совпадающими датами запроса и summary; неправильная область возвращает unavailable. |
| Финансовая база | `_finance_status` | Проверяются выручка, нетто-начисления, налог и прибыль; полное подтверждение требует account-level начислений и сверки выручки товаров. |
| SKU/количество | `_quantity_status` | Количество строк проверяется на сумму с общим числом; unknown в SKU и несверенный revenue остаются partial/unknown/error. Ноль принимается как наблюдаемое значение. |
| Себестоимость и налог | `_cost_status`, `_tax_status` | Себестоимость проверяется отдельно; налоговая сумма, база, ставка, режим и признак применённой политики обязательны для статуса подтверждения. |
| Внешние расходы и реклама | `_external_status`, `_advertising_status` | Внешние расходы обязаны совпадать по периоду и coverage. Реклама остаётся отдельной сверкой и не пересчитывает net accrual. |
| Возвраты / Return COGS | `_return_status`, `_historical_cost_status`, `_application_confirmed`; `app/services/period_profit_return_cogs_blocker_stage_service.py` | Проверяются период, количества, уникальность/идентичность записей и цепочка inventory → attribution → recognition → authorization → explicit commit → final application. Без полной цепочки дополнение к прибыли не заявляется. |
| Причины и нагрузка | `app/services/period_profit_diagnostic_view_service.py` | Снимок причин связывает статусы источников, свежесть, identity, HTTP/time budget и bounded operation counts. Детализация использует сохранённый результат. |
| Snapshot и callback | `app/services/assistant_period_profit_runtime_service.py`, `app/services/assistant_keyboard_service.py` | Отчёт, полнота, диагностика и export используют один scoped, TTL-bounded report view; действия доступны для SKU, себестоимости, возвратов и внешних расходов. Открытие деталей не должно создавать новый источник фактов. |
| Support export | `app/services/period_profit_support_diagnostic_export_service.py` | Сохранённая диагностика строится по allowlist статусов/причин и ограниченной сериализации; raw provider payload не является форматом экспорта. |

## Gap-реестр

| Класс | Наблюдение | Этап | Критерий закрытия |
|---|---|---|---|
| Подтверждённый дефект | В проверенных сервисах и regression-модулях не найдено воспроизведённого нового нарушения; B00 не меняет production-код. | — | Новый defect исправлять только после актуального воспроизведения. |
| Ограничение источника | Analytics может не возвращать `cancellations`/`returns`; текущие данные Seller API имеют отдельную date/status семантику и pagination. Исторические отмены нельзя выводить из текущего статуса отправления. | B02 | Сохранить `unknown/partial`; получить официальный source contract и проверить полную пагинацию, если появится пригодное evidence. |
| Продуктовый пробел | Статусы полноты уже существуют, но основной view не даёт единую по каждому компоненту компактную запись `amount + source + date basis + coverage + reason`; часть provenance и budget видна только в диагностике/export. | B01, затем C01 | Расширить существующий projection совместимо; единый снимок, observed zero ≠ unknown, не добавлять вторую registry/pipeline. |
| Продуктовый пробел | Декомпозиция начислений требует ясного контрольного остатка и меток «в том числе»; подкатегории могут входить в net и друг в друга. | B03 | Разложение сверяется с итогом и расходы вычитаются ровно один раз. |
| Продуктовый пробел | Пользовательские действия доступны не для каждого статуса (например, tax policy и финансовый источник не могут быть исправлены кнопкой в отчёте). Диагностический текст должен объяснять невозможность исправить источник и предлагать только существующее безопасное действие. | B01/C02 | Не показывать действие, для которого нет реального handler; сохранить source reason. |
| Продуктовый пробел | Длинный основной отчёт и подробная диагностика конкурируют за лимит Telegram и внимание; содержимое уже сохранено в snapshot/export. | C00–C03 | Сократить главный экран, оставить полную детализацию в существующих views, проверить лимит транспортного сообщения. |
| Эксплуатационный пробел | В приложении есть lifecycle/status и storage contracts, но нет проверенного полного owner backup → restore в новый root → safe update readiness workflow. | D00–D06 | Инвентаризация до реализации; ограниченный архив, fail-safe restore и mocked updater; никакой операции с live storage/ботом в этой задаче. |

## B04 follow-up

- Повторная сверка выявила production defect вне первоначального B00 аудита: `PeriodProfitFinanceSkuScopeService` восстанавливал historical finance SKU по недатированной текущей записи стоимости после того, как date-scoped historical evidence сообщала `historical_cost_confirmed=False`.
- B04 удалил этот fallback и добавил regressions на период до даты записи. При отсутствии подтверждённой даты стоимость не применяется. См. `DAILY_USE_COGS_EFFECTIVE_DATE_AUDIT_2026-10-25.md`.

## Проверка B00

- Targeted profile: `tests/test_period_profit_completeness_view.py`, `tests/test_period_profit_diagnostic_view_service.py`, `tests/test_period_profit_support_diagnostic_export_service.py`, `app/tests/test_period_profit_return_cogs_blocker_stage_service.py` — **40 passed in 1.64s**.
- Среда: отдельный `AI_ASSISTANT_STORAGE_ROOT`, пустой тестовый master-key env, cache отключён. Полный `pytest` не запускался из-за задокументированного Windows ACL/shared-storage инцидента.
- Вывод: действующая projection и blocker resolver повторно используются; отдельный completeness registry не нужен. B01–B05 остаются ограниченными перечисленными gaps и источниковыми ограничениями.
- Не запускались Ozon, Telegram, real bot, repositories на пользовательской DB, backup или restore.

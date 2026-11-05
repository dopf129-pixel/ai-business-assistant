# W12 — строгая когорта возвратов в canonical расчёте

Дата: 29.10.2026.
ТЗ: `LUNA_FULL_UNIT_ECONOMICS_AND_PRICE_EXPERIMENTS_TASK_2026-10-28.md`.
Статус: завершён; W13–W39 остаются открыты.

## Изменение

`UnitPriceScenarioService.calculate`, `calculate_components_only` и `compare` теперь принимают необязательный результат `UnitEconomicsReturnEvidenceService` как `strict_return_evidence`. Режим `STRICT_RETAINED_COHORT` применяет строгое возвратное списание к forward-прибыли/шт. только когда W07 вернул `COMPLETE` и `AVAILABLE`.

Перед применением повторно проверяются точный owner/store/product/offer/SKU/sale-schema, статусы финансов/количества/инвентаря, cohort-match, delivered/returned/retained арифметика, число disposition units, retained-знаменатель, все денежные компоненты и равенство `fees + irrecoverable COGS − non-overlapping compensation = loss pool`. Также проверяется `loss_pool / retained_units` с тем же округлением до копейки, что использует W07. В расчёт поступает уже подтверждённая ставка на retained unit; общий пул не делится вторично.

Строгий режим не принимает window components. `WINDOW_COST_ALLOCATION` не принимает строгую когорту. Поэтому storage/рекламные/прочие оконные суммы и возвратный loss pool не могут случайно смешаться или получить чужой знаменатель. Оба режима используют тот же canonical `_calculate_components` и существующий TaxService.

## Fail-closed условия и privacy

- Нулевая/отрицательная retained quantity, лишние возвраты, неправильный SKU/store, разошедшийся знаменатель или формула дают unavailable.
- Incomplete pagination/cohort/fees, pending/unknown disposition, net credit requiring review и resolver errors не превращаются в ноль.
- Только `AVAILABLE` результат W07 может применяться; неизвестные статусы и поддельная/повреждённая арифметика блокируются.
- Результат не раскрывает cohort token, posting/return IDs или source rows; выводит только безопасную денежную сводку и количество.
- Режим остаётся read-only; никаких API вызовов или источников он сам не делает.

## Проверки

- W12 добавил 9 интеграционных тест-функций в `tests/test_unit_economics_return_evidence_service.py`; параметризованный gate покрывает 12 вариантов, включая N02 и Q0.
- Addressed W12 profile: **52 passed in 0.54s**.
- Combined isolated W05–W12 profile: **184 passed in 2.75s**.
- `compile(...)` для четырёх изменённых Python-файлов, line-length scan, `git diff --check` — PASS; `git diff -- data` пустой.
- Synthetic fixtures only; temporary storage/basetemp, dotenv отключён. Реальные Ozon API, owner DB и live bot не использовались.

## Следующий этап

W13 проверить налоговые режимы `NONE`, `USN_INCOME`, `USN_INCOME_MINUS_EXPENSES`, минимальный налог и баллы на extended gross profit. Для группового расчёта TaxService вызывается один раз, а расширенные расходы не вычитаются после налога.

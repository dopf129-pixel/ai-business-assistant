# W23 — candidate prices для unit economics experiment

Дата: 29.10.2026
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Зависимость: W22 plan/readiness, existing `UnitPriceTargetPlanningService`
Результат: DONE. Code commit: `cb4e5f77`; docs commit — см. progress journal.

## Контракт и реализация

Добавлен pure `UnitEconomicsExperimentCandidatePriceService`. На входе он получает canonical scenario inputs, обязательный владелецский диапазон в копейках, 2–10 желаемых точек, опциональный замороженный тарифный snapshot и уже нормализованные extended cost/strict-cohort contracts. Сервис не делает source I/O, не меняет цену и не сохраняет решение.

Сервис повторно использует существующие price-grid, frozen-tariff resolution, scenario forward-calculator и advertising-compensation solver. Candidate список сохраняет endpoints и тарифные граничные точки, если итог остаётся в лимите 10. Копейки и ставки берутся из одного frozen snapshot. Равные прибыли сохраняются все. Результат утверждает только максимум среди конкретно проверенных цен; спрос, глобальный оптимум и причинное влияние цены не моделируются.

Если tariff gap/commission/source или хотя бы одна цена не имеет подтверждённого расчёта, весь shortlist получает `INCOMPLETE` без лучшей цены. Если boundary insertions превышают лимит, точки не отбрасываются молча. Без frozen tariff calculator может сравнить явно помеченную ручную ставку; ответ предупреждает, что она не подтверждена для диапазона.

## Regression coverage

Новый `tests/test_unit_economics_experiment_candidate_price_service.py` проверяет диапазон/границы, копеечные tariff-boundary точки и ставки по обе стороны, overflow без truncation, unknown tariff gap, ties, invalid/too narrow bounds, invalid count, ручное тарифное допущение и наличие рекламных порогов существующего сравнения.

Профиль запущен на Windows, Python 3.12, pytest 8.4.2, с отключёнными dotenv/plugin autoload, отдельным временным `AI_ASSISTANT_DATA_DIR` и runtime dependency path. Provider credentials удалены из процесса; живые API и бот не запускались.

```text
python -m pytest -q --tb=short tests/test_unit_economics_experiment_candidate_price_service.py tests/test_unit_price_target_planning_service.py
87 passed in 1.59s
```

`py_compile` завершился без ошибок; `git diff --check` прошёл. `git diff -- data` пуст. Владелецская база/данные не читались и не изменялись.

## Границы

- `MAX_RUB_PER_UNIT` остаётся единственной целью.
- Без замороженного тарифа commission rate является предположением владельца, а не ставкой Ozon.
- Выбор ограничен ценами в заданной сетке; он не означает глобальный максимум рынка.
- Количество кандидатов специально ограничено 2–10; tariff boundaries сверх этого лимита требуют более узкого диапазона/ручной корректировки.
- История/сохранение кандидатов и owner-confirm фактической цены/времени реализуются на W24 и последующих этапах.

Следующий этап: W24 — preview и CAS/idempotent owner confirmation точной фактической цены/времени с exact experiment/observation links.

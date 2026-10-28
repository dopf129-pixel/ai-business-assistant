# Аудит подготовки: экономика SKU и ценовые эксперименты

Дата: 28.10.2026. Base main: 9315046cf29c9e8c68da1cab027cb2568040f142.
Назначение: основание для нового ТЗ; это read-only аудит кода, не приёмка источников живого магазина.

## Уже реализовано

1. UnitPriceScenarioService считает компоненты одной успешной продажи, условную рекламу, себестоимость и существующий TaxService. VERSION=2 на базе подготовки. Дополнительного структурированного expense pool в нём нет.
2. UnitPriceTariffResolver и UnitPriceTariffSnapshotAdapter сохраняют и разрешают price-specific commission с ручным fallback. Target/grid/compensation, batch/sensitivity и saved plans уже существуют.
3. PlanningWorkspaceRepository на этой базе имеет DATABASE_SCHEMA_VERSION=5: одна storage authority для planning docs, tariff profiles, observation/result и comparison history; CAS/idempotency, allowlists, quotas и backup уже есть.
4. UnitPriceObservationCollectionService собирает read-only evidence по явному действию; нормализатор сохраняет раздельные date/revenue bases и неполноту. Result service применяет CPC к подтверждённым входам как MODELLED_FROM_OBSERVED_INPUTS.
5. Quality/ranking, Telegram wizard наблюдения, сохранённая история, экспорт и safe retry уже реализованы. Повторное создание этих подсистем не требуется.
6. ReturnsFinanceAttributionFactsSource и analytics дают связанные категории возвратов/невыкупов и их денежные/fee totals, coverage и отдельные counts. Наличие этих полей не подтверждает новую модель потерь автоматически.
7. Основной финансовый отчёт, SKU attribution, effective cost, inventory recovery и Return COGS — самостоятельные существующие pipelines. Новый плановый инструмент не должен проводить через них операции по результату своего прогноза.

## Подтверждённые ограничения, а не новые баги

- Scenario excluded scope содержит returns/cancellations и storage; отдельные cross-docking inputs уже поддерживаются.
- Observation result явно предупреждает о CPC-only, разных основаниях дат CPC/FBO, snapshot delivered units и неучтённых return costs.
- Q15 contract предупреждает: имеющаяся finance sale posting projection не даёт доказанной per-sale historical price/quantity series.
- ReturnsFinanceAttributionFactsSource._category_facts суммирует total_amount и fees по связанным отправлениям; average относится к observed posting count. Это не loss per successfully sold unit. Возвратная операция может содержать revenue reversal и услуги, требующие отдельного разнесения.
- Existing observed buyout estimate delivered/(delivered + confirmed non-buyout) не подтверждает retained units после всех customer returns. Decision 062 сохраняется для старой модели.
- Исторические 56 дней кросс-докинга имеют знаменатель supplied units; он отличается от проданных/сохранённых единиц.
- Журнал ценовых наблюдений не является пошаговым experiment state machine с фазами baseline/candidate, control flags, maturity policy и следующим действием.

## Следствие для новой программы

Нужно расширить существующие calculation/evidence/result contracts, а не добавить ещё один экран с «чистой прибылью». Главные gates:

1. Cost ownership/dedup: отсутствие повторного учёта base fees и Performance/financial ads.
2. Quantity/lineage: строка, posting, delivered и retained различимы; разные clocks не склеиваются.
3. Tax compatibility: дополнительные расходы включаются до соответствующего вызова TaxService.
4. Legacy/version: новый режим включается явно, старый результат не пересчитывается.
5. Comparability: расход окна и расход точной когорты получают разные модели.
6. Product completion: неподтверждённый источник имеет понятный законченный unavailable UX и не блокирует всю автономную программу.

## Проверенные опорные пути

Implementation:

- app/services/unit_price_scenario_service.py
- app/services/tax_service.py
- app/services/unit_price_target_planning_service.py
- app/services/unit_price_tariff_snapshot_adapter.py
- app/services/unit_price_observation_collection_service.py
- app/services/unit_price_observation_normalizer.py
- app/services/unit_price_observation_result_service.py
- app/services/unit_price_observation_quality_service.py
- app/services/unit_price_observation_ranking_service.py
- app/services/returns_finance_attribution_facts_source.py
- app/services/returns_finance_attribution_analytics_service.py
- app/services/planning_workspace_repository.py
- app/services/telegram_unit_price_observation_runtime_service.py

Contracts/acceptance:

- project_brain/DECISIONS_061.md
- project_brain/DECISIONS_062.md
- project_brain/DECISIONS_063.md
- project_brain/UNIT_PRICE_OBSERVATION_CONTRACT_Q15_2026-10-27.md
- project_brain/UNIT_PRICE_REVIEW_HANDOFF_Q35_2026-10-27.md
- project_brain/UNIT_PRICE_PROFIT_PER_UNIT_USER_GUIDE_2026-10-27.md
- docs/telegram-user-guide.md

Официальные текущие API-контракты нового режима ещё не проверялись на этой стадии. W02 обязан проверить primary documentation/schema/fixtures; наличие capability не выводится из имени endpoint или поля.

Подготовка меняет документацию; runtime, data/ и реальный бот не изменяются.

## Проверка подготовленного пакета

- W00–W39: 40 уникальных стадий, зависимости существуют и направлены только на предыдущие стадии; таблица журнала совпадает.
- N01–N18: 18 групп содержательной приёмки; 58 existing source/document/test paths подтверждены на исходной базе.
- Pure numeric checks: 46.00 / 40.00 / 41.20 / 39.10 / 46.50 RUB/unit, loss pool350, extra5 и weighted1.82 — PASS. Это проверка задания, не реализация новой expense schema.
- Source/API capabilities новой программы ещё не подтверждены; W02 остаётся NOT_STARTED.
- diff whitespace check — PASS; data diff пустой. Новые runtime/tests не создавались.

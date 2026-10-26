# Q03 — contracts помощника максимизации прибыли с единицы

Дата: 27.10.2026. Исходные бизнес-решения — раздел 2 `LUNA_PRICE_PROFIT_PER_UNIT_TASK_2026-10-26.md`; архитектурное владение — Decision 061.

## Целевой результат

- Единственная цель ранжирования: `PROFIT_RUB_PER_SUCCESSFUL_UNIT` — прибыль в рублях за одну успешную продажу единицы выбранного SKU.
- Входная цена: `SELLER_PRICE_RUB`, Decimal в рублях с точностью до копейки. Цена покупателя и скидки Ozon не подменяют цену продавца.
- Формула остаётся `UnitPriceScenarioService` → текущий `TaxService`; тарифный resolver, сравнение, рекламные пороги и качество рекомендаций только подготавливают/интерпретируют входы.
- Маржа, выручка и дневная прибыль — вторичные показатели, не критерии выбора/tie-break. Равенство определяется после денежного округления.
- Денежные компоненты используют Decimal и такое же `ROUND_HALF_UP` до копейки, как canonical forward. Unknown/missing/stale/conflict не превращаются в 0.

## Outcome/evidence envelope

Все сценарии, сравнения и сохранённые observed results используют allowlisted envelope:

```text
schema_version, calculation_version, objective, status, evidence_basis,
identity{owner_id,store_id,product_id,offer_id,sku,sale_schema},
price_basis, seller_price, source_snapshot_id, source_as_of,
tariff_resolution, advertising{mode,revenue_basis,amount_per_unit,rate},
assumptions, calculation{canonical forward projection},
completeness{component:{status,origin,reason}}, generated_at
```

`evidence_basis` выбирается строго из `SCENARIO_ASSUMPTIONS`, `MODELLED_FROM_OBSERVED_INPUTS`, `CANONICAL_FACT_COMPARABLE`. `status` независим от основания: `AVAILABLE`, `INSUFFICIENT_DATA`, `SOURCE_UNAVAILABLE`, `STALE`, `INCOMPARABLE`, `CONFLICT`, `UNSUPPORTED_SCHEME`. Компонентная полнота различает `CONFIRMED`, `MANUAL_ASSUMPTION`, `UNKNOWN`, `STALE`, `NOT_APPLICABLE`; значения могут быть `None` с безопасным reason code.

Для рейтинга допустимы только строки `AVAILABLE` с конечным `calculated.profit`. Неизвестный вариант не показывается как нулевая прибыль. `best_checked_candidate` всегда означает лучший только среди реально проверенных кандидатов.

## Tariff resolver

Запрос включает owner/store/product/offer/SKU identity, `sale_schema`, seller-price integer cents, дату применимости и применимые версии профиля. Интервал имеет целочисленные `price_from_cents`/`price_to_cents` и включённые границы. Ставка — десятичная строка/Decimal `[0,100]`, ноль возможен только явно. Пересекающиеся интервалы отклоняются; дырки остаются неизвестными. Сопоставление требует точной identity, схемы, даты и диапазона.

Ответ содержит `status`, `commission_rate`, `price_basis=SELLER_PRICE_RUB`, matched bounds, `origin`, `source_ref`, `effective_from/to`, `observed_at/recorded_at`, `profile_id`, `profile_revision`, `profile_state_revision` и reason. Статусы: `CONFIRMED_RANGE`, `MANUAL_RANGE`, `CURRENT_PRICE_POINT_ONLY`, `UNKNOWN`, `EXPIRED`, `CONFLICT`, `UNSUPPORTED_SCHEME`, `SOURCE_UNAVAILABLE`. Точка текущего тарифа применима только к этой цене и поддержанной FBO-схеме. Нет implicit priority, заполнения дырки, распространения точечной/legacy ставки или fallback на старое значение.

## Advertising and computation

- `SAME_DRR`: одна явно выбранная ставка для всех цен («сценарий неизменной ДРР»).
- `PER_PRICE_DRR`: отдельная ДРР для каждой цены.
- `OBSERVED_COST_PER_UNIT`: подтверждённый расход / совместимое количество единиц; сохранять исходную сумму, знаменатель и базу. При переносе в canonical forward проверить, что денежный компонент совпадает до копейки; скрытое округление ставки запрещено.
- Для всех режимов обязателен `revenue_basis` (seller revenue или attributed revenue плюс источник); CPC-only не является полной рекламой.
- Компенсационный предел отдельно считает максимум расхода/ДРР при `candidate_profit >= baseline_profit` и при строгом `>` после округления. Для каждого результата проверяется соседний разрешённый шаг. Это не предел маржи/безубыточности.
- Один явный source refresh использует существующий `PeriodProfitOperationTrace` (60 секунд/64 HTTP reservations). Изменение цены/ДРР/таблицы использует frozen snapshot без сетевых запросов.
- Явный ввод 2–10 цен; сетка ограничена 200 ценами, не более 20 tariff bands и 1 024 canonical forward расчётов на одно действие, включая проверки границ.

## Observation/recommendation

- Журнал цены начинается явным действием владельца; бот цену не изменяет и не восстанавливает прошлую цену из текущей карточки. Сбор выполняется явно только за завершённые дневные интервалы с timezone/date basis.
- Плановая цена отдельна от подтверждённой/наблюдаемой; неизвестная история даёт `PRICE_HISTORY_UNCONFIRMED`, смешанная — `MIXED_PRICES`. Нельзя приписать весь период одному варианту.
- Сохраняются периоды, количество завершённых дней и совместимых единиц, цена/тарифные версии, рекламный denominator, source coverage, корректировки и ограничения.
- Наблюдения — append-only local analytical/planning records; повтор идемпотентен, metadata changes используют точный `state_revision` CAS, refresh добавляет новую immutable result revision. Пересекающиеся окна не объединяются с двойным счётом. Лимиты: 100 наблюдений на store, 20 result versions/observation, 64 KiB/normalized version.
- Выборка 3–56 завершённых дней и 1–10,000 единиц — предупреждающая граница, не confidence/causal proof. Recommendation ранжирует только сопоставимые варианты, показывает факторы различий и не заявляет глобальный optimum или причинность.

## Layer and persistence boundary

```text
TariffProfile application service ── PlanningWorkspaceRepository
                 │                         │
                 ▼                         └─ additive tenant SQLite schema
             pure resolver ── tariff per candidate
                                       │
source snapshot ───────────────────────┤
                                       ▼
                           existing UnitPriceScenarioService v2 / TaxService
                                       │
                         comparison / thresholds / bounded grid
                                       │
existing Telegram UPC route ─ saved plan frozen revisions / owner exports
                                       │
explicit observation collection ─ append-only result revisions ─ quality gate
```

Pure calculation components do not use DB/Telegram/Ozon. Callbacks carry short versioned tickets only. Exports project the same normalized snapshot; support exports do not receive SKU/business payloads.

Decision 061 keeps existing tenant `ozon_assistant.db` and `PlanningWorkspaceRepository` as the sole SQLite schema/migration/transaction owner for additive tariff/observation records. Saved plan v1/v2 remain readable and frozen without network reads. New tariff/comparison payloads use an explicit version and explicit new revision/copy upgrade. Tariff edits cannot mutate old plans/results; observations/results are append-only, while metadata edits are CAS/idempotent. Existing backup/restore includes the added tables and is verified only with a fresh synthetic root.

If implementation needs different field names, record the mapping in the execution journal with code/test references. Do not weaken scope, accounting, evidence, CAS, privacy or limits without an owner business decision.

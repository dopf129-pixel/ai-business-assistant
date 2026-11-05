# W05 — нормализация расходов и ledger ownership

Дата: 28.10.2026
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Входной code HEAD: `f3576fbc`
Статус: DONE. Новый сервис pure; API adapters, persistence и runtime integrations не входят в W05.

## Реализация

Добавлен `UnitEconomicsExpenseNormalizer` — единственная новая чистая граница, которая переводит уже адаптированные source rows в безопасные `ExpenseSnapshotV1`-совместимые компоненты. Она принимает ровно одну область owner/store/product/offer/SKU/schema и один source window; не делает I/O, API-запросы, чтение окружения или запись в `PlanningWorkspaceRepository`.

Вход ограничен версией схемы и allowlisted полями. Проверяются точная identity, календарные границы/основание даты/timezone, UTC timestamps, page coverage, source, category, attribution, ownership, origin, recurrence, correction state и лимиты размеров. Деньги принимаются как строка/int/Decimal, но не `bool`/float/NaN/Infinity; нормализуются до копеек `ROUND_HALF_UP`. `-0.00` канонизируется в `0.00`.

Dedup key — transient пара `(operation_id, component_id)` внутри одного точного owner/store/snapshot scope. Одинаковая часть игнорируется; изменённый duplicate или расхождение mapping в одном агрегируемом component key помечает компонент и snapshot как `CONFLICT`, оспариваемая сумма не выдаётся как применимая. Несколько component IDs одной операции суммируются раздельно по ключам; один ID операции в другом store не сталкивается.

Signed суммы сохраняются без смены знака; `normalized_expense_rub = -signed_source_amount_rub`. Поэтому начисление −300 и связанная коррекция +50 дают signed −250 и расход 250; чистый кредит остаётся отрицательным расходом. Отдельный ownership ledger разделяет `BASE_ALREADY_INCLUDED`, `ADDITIONAL`, `RECONCILIATION_ONLY`, `UNATTRIBUTED`, `UNKNOWN`; неточная attribution не может быть помечена как применимый `ADDITIONAL` SKU расход.

Coverage отличает `COMPLETE`, `CONFIRMED_ZERO`, `PARTIAL`, `UNAVAILABLE`, `UNKNOWN` и `CONFLICT`. Ноль отсутствующей компоненты выдаётся только при завершённом источнике и полном page coverage; неполные страницы, пропуск/несовпадение identity, invalid row и conflict не маскируются нулём. `timezone=UNKNOWN` сохраняется как неизвестность и не превращается в известную локальную зону.

В output нет operation IDs, component IDs, raw API rows или неизвестных полей. Возвращается только bounded aggregate, число неизвестных полей и SHA-256 fingerprint безопасного нормализованного результата; агрегаты ограничены 64 component groups.

## Regression coverage

Добавлен `tests/test_unit_economics_expense_normalizer.py`, 16 тестов/параметризованных случаев: multi-service operation, exact duplicate, conflicting duplicate, межмагазинное разделение одинакового provider ID, signed correction/credit, incomplete-vs-confirmed-zero coverage, identity mismatch, неизвестные поля/schema, malformed money, неизвестная timezone, negative zero и запрет unattributed additional expense.

Фактический профиль на Python 3.12.10 / pytest 8.4.2, изолированный `basetemp` и synthetic `AI_ASSISTANT_STORAGE_ROOT`:

```text
tests/test_unit_economics_expense_normalizer.py
tests/test_unit_price_observation_normalizer.py
29 passed in 0.52s
```

Дополнительно: `py_compile` двух новых файлов PASS; `git diff --check` PASS; новые файлы не имеют строк длиннее 120 символов. IANA timezone база подключена через локальный `PYTHONTZPATH` (описание Windows окружения в W04); проектные зависимости не изменялись.

## Ограничения / следующий шаг

Компонент ещё не питается данными ни одного Ozon endpoint. W06/W07/W08 добавили pure resolvers поверх normalized snapshots (реклама, возвраты/состояние товара, хранение и дополнительные услуги), но source adapters не реализованы. Optional `cohort_ref` в W07 передаёт только уже доказанную exact связь; его генерация остаётся ответственностью будущего adapter. До интеграции эти payloads являются только контрактом и тестовым инструментом. Raw source identifiers разрешены лишь на время join/dedup.

Пользовательские файлы/БД и `data/` не читались/изменялись; реальный Ozon API и бот не запускались. W06 может использовать этот нормализатор, но не должен обходить ownership или completeness gates.

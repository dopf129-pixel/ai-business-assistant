# История сравнения прибыли на единицу (Q23)

Дата: 27.10.2026  
Статус: VERIFIED  
Классификация: Architecture Review Required

## Поведение

- Сравнение сохраняется отдельным tenant/store-scoped снимком в planning database. В снимке хранится точный результат рейтинга после Q21 gate и версии источников: observation ID/result revision и source saved-plan ID/revision для каждого проверенного кандидата. Дополнительный manifest локальных результатов помогает определить появление более нового варианта.
- Снимок неизменяем. Новая редакция сравнения вставляется отдельной ревизией с CAS и idempotency; SQL guards запрещают UPDATE/DELETE старых ревизий. Идентичность товара/магазина должна совпадать с предыдущей ревизией сравнения.
- Повторное открытие, просмотр bounded истории и JSON export берут данные из уже сохранённого snapshot. Рейтинг не запускается заново, collectors и Ozon API не вызываются. Экспорт сохраняет ranking/quality basis и номера ревизий, но не содержит внутренних observation/document IDs.
- В карточке явно отображаются `CURRENT`, `STALE`, `SUPERSEDED` и `SUPERSEDED_AND_STALE`. Stale относится к появлению/обновлению/архивации observation или изменению source plan revision. Исторический payload и прежний победитель остаются прежними.
- Кнопка обновления использует только локальные последующие observation revisions. Если результат сравнения не изменился, новая revision не создаётся. Если пользователь сначала сохранил новые данные через observation flow, refresh добавляет новый comparison revision и сохраняет предыдущий результат. Refresh сам по себе не запрашивает Ozon и не собирает новый период.
- Runtime cache/user-state clearing не удаляет долговременные сравнения.

## Миграция и сохранность

- Planning database schema повышена с v4 до v5 атомарно и аддитивно. Добавлены таблицы comparison revisions и idempotency, индекс и immutable triggers.
- Payload schema сохранённых планов не менялась. Результаты наблюдений, plans и `data/*.json` не изменялись.
- Отдельные regressions покрывают migration v3→v5 и v4→v5, сохранность saved plan/result, tenant isolation, idempotency conflict/replay, CAS conflict, SQL immutability, bounded allowlist и rollback после синтетической ошибки вставки.

## Реализация

- `app/services/planning_workspace_repository.py` — additive schema v5, create/append/get/list, allowlist, fingerprint, CAS/idempotency и database guards.
- `app/services/unit_price_observation_ranking_service.py` — точные candidate source references и локальный manifest наблюдений, видимых при рейтинге.
- `app/services/unit_price_comparison_history_service.py` — создание, source-free read/export, stale check и append refresh из сохранённых evidence.
- `app/services/telegram_unit_price_observation_runtime_service.py` — сохранённая карточка, история с bounded pagination, refresh callback и статусы актуальности.
- Регрессии находятся в `tests/test_unit_price_comparison_history_repository.py`, `tests/test_unit_price_observation_repository.py`, `tests/test_planning_workspace_repository.py` и `tests/test_telegram_unit_price_observation_runtime.py`.

## Проверки

- Q23 адресный Windows/Python 3.12 набор: **33 passed in 2.08s**.
- Связанный Q16–Q23 профиль по 28 planning, observation, tariff, saved-plan и production-runtime test targets: **474 passed in 10.94s**; pytest plugin autoload was disabled and credential-like process variables were cleared.
- Python AST parsing изменённых application/test files и `git diff --check` выполнены перед commit; `git diff -- data` пустой.
- Тестовый процесс использовал существующую project Python 3.12 environment, temporary pytest storage/basetemp и локальный IANA timezone database. Сеть/API, `.env`, owner DB и реальный бот не запускались.
- Полный repository pytest, Linux/Windows exact-head CI и Docker checks остаются Q33–Q35.

## Архитектура и ограничения

- Архитектура расширена в текущем planning repository/application/Telegram слое; новая база данных, новый source adapter и изменение формулы прибыли не добавлялись.
- Внешний source evidence по-прежнему появляется только через уже существующий observation collection flow. Q23 refresh повторно использует сохранённый evidence и намеренно не скрывает сетевой сбор за кнопкой просмотра/обновления сравнения.
- `DECISIONS.md` не изменялся: additive repository migration, tenant isolation, immutable evidence и Q21 gate уже определены ранее.

Следующий этап: Q24 — связать полный пользовательский путь выбора SKU до следующей наблюдаемой цены и рекомендации.

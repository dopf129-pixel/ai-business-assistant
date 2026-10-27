# Q16 — долговременный журнал наблюдений цены

Дата: 27.10.2026
Статус: VERIFIED — repository/migration acceptance; Telegram collection flow remains for Q17–Q20.

## Реализация

- `PlanningWorkspaceRepository` остаётся единственным владельцем planning SQLite schema и транзакций. Добавлена атомарная additive migration DB v3→v4; сохранённые plan payloads остаются `SCHEMA_VERSION=3`.
- Добавлены tenant/store-scoped записи наблюдений, immutable result revisions и idempotency records. Результат не копирует saved-plan revision: он ссылается на точный документ/revision и хранит только ограниченную версионированную проекцию наблюдения.
- Start требует явного `owner_confirmed=True`, точную FBO identity и существующую identity в указанной revision сохранённого плана, положительную seller price в копейках, timezone IANA, bounded note и прошедший timezone-aware `effective_from`. Исходное UTC-смещение effective time сохраняется; `recorded_at` отделён от `effective_from`.
- Повтор с тем же idempotency key возвращает прежний результат только при совпадении SHA-256 fingerprint нормализованного запроса. Повторное использование ключа с другой операцией/ценой/заметкой возвращает conflict. Изменения состояния используют точный `state_revision` CAS; result append сверяет обе ревизии.
- Каждая result revision проверяет owner/store, product/offer/SKU/schema и seller-price против родительского наблюдения. Result JSON — schema v1 с top-level, source, metric и completeness allowlists; запрещены floats, сырые posting identifiers, секретные/raw-response поля, неизвестные metric/source поля, чрезмерная глубина/размер и окно длиннее 56 дней. Неизвестные временные поля могут оставаться `null`, без догадки о часах.
- SQL triggers запрещают UPDATE/DELETE result versions. Чтение latest/history повторно валидирует payload/version/identity и закрывается с безопасным кодом на повреждённой или будущей версии.
- Лимиты: 100 записей на store, не более одной активной записи на точную SKU identity, 20 revisions на наблюдение, 64 KiB на нормализованный результат, 500 символов заметки, bounded pagination. Пересекающиеся окна сохраняются отдельно с `INCOMPARABLE`; repository не объединяет и не удваивает их — ranking gate принадлежит Q21.

## Проверки

- Изолированный Windows/Python 3.12 профиль: `tests/test_unit_price_observation_repository.py`, `tests/test_planning_workspace_repository.py`, `tests/test_planning_workspace_tariff_profiles.py` — **38 passed in 1.58s**.
- Проверены: duplicate start/replay и конфликт idempotency, активное SKU ограничение, store isolation, restart/reopen, state/result CAS, note/finish/archive, append-only corrections, overlap retention, exact result identity, rollback атомарности, migration rollback, migration v3→v4 без потери старого плана, quotas, corrupt/future schema, попытки SQL update/delete result и неизвестные/опасные payload поля.
- Затронутые Python-файлы прошли `py_compile`; `git diff --check` прошёл. `git diff -- data` пустой. Тестовая БД/storage и pytest basetemp были временными; сеть, Ozon/Telegram API, `.env`, owner DB и реальный бот не использовались.

## Архитектура и границы

- Новая SQLite-владелец/БД не создавалась. Изменение расширяет существующий repository согласно Decision 061; canonical unit-price calculation и финансовая БД не менялись.
- Application/Telegram orchestration, чтение источников и публикация наблюдения не добавлялись — это Q17–Q20.
- Архитектурная классификация: **Architecture Review Required** — новая схема и публичный repository contract.

Следующий этап: Q17 — bounded read-only collection через существующие adapters и fake HTTP transport.

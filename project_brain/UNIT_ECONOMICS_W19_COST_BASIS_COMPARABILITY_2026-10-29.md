# W19 — cost basis в качестве observation и ranking

Дата: 29.10.2026
Branch: `codex/full-unit-economics-experiments-implementation-20261028`
Code commit: `d1e1fbac` (`Bind observation ranking to frozen cost basis`)
ТЗ: `LUNA_FULL_UNIT_ECONOMICS_AND_PRICE_EXPERIMENTS_TASK_2026-10-28.md`

## Результат

Расширенная себестоимость из замороженного планового контракта проходит через observation evaluator и участвует в подписи и проверке сравнимости результата.

- Оконная аллокация сохраняет режим, безопасную SHA-256 подпись scope и исходных ссылок, origin и сумму на единицу.
- Строгая когорта подписывается по нормализованному allowlist evidence и точной identity; сырые ответы, идентификаторы поставок/возвратов и credentials не включаются.
- `OWNER_COST` помечается как `MANUAL_ASSUMPTION`; полный подтверждённый snapshot без этого допущения — `CONFIRMED`; неполные данные не становятся подтверждёнными.
- Observation result сохраняет `extended_cost_mode`, `extended_cost_origin`, `extended_cost_signature`, `extended_cost_per_unit`.
- Quality исключает несовпадающие подписи, scope, режим, origin и сумму; incomplete/unconfirmed basis не допускается к ranking.
- Ranking включает frozen cost basis и связанные допущения в собственную подпись.
- Planning repository принимает новые поля и продолжает читать старые observation results и comparison history.
- Для strict-cohort canonical boundary нормализует существующий `scheme` в `sale_schema`; точная owner/store/SKU/schema проверка остаётся обязательной.

## Изменённые области

Изменены существующие adapter, observation result/quality/ranking services, Telegram observation runtime и allowlist Planning Workspace repository. Добавлены regressions в adapter/result/quality suites. Новых сервисов, таблиц, зависимостей и live-source вызовов нет.

## Проверки

Изолированный Windows/Python 3.12 профиль, без dotenv, секретов, реальных Ozon-запросов и бота:

- Linked W19 profile (12 suites): **136 passed in 9.48s**.
- Дополнительный direct profile (3 suites): **29 passed in 1.52s**.
- `py_compile` изменённых модулей: PASS.
- `git diff --check`: PASS.
- `git diff -- data`: пусто.

Strict-cohort regression сначала выявил несовпадение имён `scheme`/`sale_schema` на границе observation → canonical calculator. Узкая нормализация исправлена; повторные проверки зелёные.

## Ограничения и следующий шаг

Подпись гарантирует сопоставимость только сохранённых model assumptions/evidence; она не превращает смоделированную прибыль в фактическую и не подтверждает причинность. Полный repository `pytest` запланирован на заключительный W38–W39 профиль.

Следующий этап — W20: единая snapshot-проекция detail/export без повторного чтения источников и с одинаковыми суммами, статусами, revisions, privacy и size bounds.

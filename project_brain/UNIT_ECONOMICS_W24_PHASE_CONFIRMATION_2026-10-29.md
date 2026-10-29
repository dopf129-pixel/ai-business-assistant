# W24 — preview и подтверждение фактической цены и времени

Дата: 29.10.2026
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Зависимости: W22 plan/readiness, W23 candidate-price selection
Результат: DONE. Code commit: `e39bb48e`.

## Реализация

Добавлен pure `UnitEconomicsExperimentPhaseConfirmationService`. Он разрешает подтверждение только запланированной фазы в ожидаемом состоянии эксперимента и только для точной плановой цены. Для candidate-фазы выбранная цена дополнительно проверяется по frozen candidate list. Время должно включать timezone и не быть будущим. Для изменения цены в середине локального дня первый полный день — следующий календарный день; для изменения ровно в полночь им может быть текущий день. Плановое окно обязано включать этот первый полный день.

Preview не меняет состояние и возвращает revisions эксперимента и фазы для последующей CAS-проверки. Owner-confirm выполняется отдельной repository-операцией: одна `BEGIN IMMEDIATE` транзакция проверяет tenant, точные frozen references, статусы и обе expected revisions, соблюдает существующую квоту observations, захватывает общий active-SKU guard, создаёт связанное наблюдение, активирует фазу/эксперимент и сохраняет append-only revisions и idempotency results.

Наблюдение ссылается на ту же revision сохранённого плана и точную идентичность owner/store/product/offer/SKU/FBO. Повтор той же команды с тем же ключом идемпотентно возвращает исходный результат; изменённый запрос с этим ключом и новая команда с устаревшими revisions отклоняются. Тестовая ошибка посередине подтверждает полный rollback наблюдения, guard, фаз, revisions и idempotency.

Подтверждение владельца обозначено как `OWNER_DECLARED`, а наблюдение — как `OWNER_DECLARED_PRICE_CHANGE`. `price_history_verified` всегда `false`: введённое владельцем время не объявляется доказанной историей цены Ozon.

## Хранение и совместимость

Planning Workspace получил additive migration v8→v9: в записи фазы добавлены nullable `observation_id` и `confirmation_json` и partial index по связанному observation. Существующие фазы без этих значений остаются читаемыми и не получают фиктивного подтверждения. Тест миграции моделирует старую v8 таблицу без двух колонок и проверяет сохранение phase и её истории.

## Проверки

Связанный изолированный Windows/Python 3.12 профиль включает pure confirmation, planning workspace, схему/репозиторий, lifecycle наблюдений и state machine:

```text
96 passed in 2.84s
```

Проверены midday и midnight local boundaries, preview без записи, exact linked observation, retry/conflict/stale CAS, запрет второго активного наблюдения, quota fail-closed, rollback при искусственном SQLite trigger и v8→v9 migration. `py_compile`, `git diff --check` прошли; `git diff -- data` пуст.

Использовались синтетические fixtures и временная база. Не использовались credentials, `.env`, данные владельца, реальные Ozon/Telegram запросы и запущенный бот.

## Границы

- Owner-confirm не подтверждает цену через Ozon API и не доказывает прошлое состояние карточки.
- Preview может устареть; его revision tokens обязательны для подтверждения.
- Пользовательский Telegram wizard и lifecycle паузы/возобновления остаются на последующих этапах W25 и W31.

Следующий этап: W25 — фиксация control flags и pause/resume сегментов без переписывания evidence.

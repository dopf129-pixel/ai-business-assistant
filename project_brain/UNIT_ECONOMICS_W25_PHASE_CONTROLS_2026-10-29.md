# W25 — контрольные условия и пауза/возобновление фазы

**Дата:** 29.10.2026
**Ветка:** `codex/full-unit-economics-experiments-implementation-20261028`
**Входной HEAD:** `6640e58c`
**Кодовый commit:** `5c609de8` — `Add durable pause and resume for price experiments`
**Этап:** W25, зависит от W24.

## Изменения

- Добавлен `UnitEconomicsExperimentControlService`. Разрешены только owner-reported статусы для рекламы, карточки, себестоимости, остатка, акции и тарифа: `UNCHANGED`, `CHANGED`, `UNKNOWN`, `NOT_APPLICABLE`. Свободные заметки и утверждения об источнике Ozon не принимаются. Изменённые и неизвестные условия получают детерминированные reason codes.
- `PlanningWorkspaceRepository.record_price_experiment_control_update` добавляет проверенное событие с hash, CAS, idempotency и bounded quota; ни phase configuration, ни завершённые результаты не переписываются.
- `pause_price_experiment_phase` в одной транзакции сохраняет PAUSE, закрывает только связанное active observation, переводит phase/experiment в PAUSED и синхронно снимает SKU guard.
- `prepare_price_experiment_resume` сохраняет новый planned segment с тем же типом фазы, выбранной ценой и frozen expense snapshot; проверяются порядок сегментов, лимит фаз и отсутствие второго ожидающего сегмента. Активация снова требует exact owner confirmation цены и времени; target должен совпасть с baseline/candidate.
- Additive schema v9→v10 добавляет `resume_target`, bounded append-only event log с hash/integrity triggers и индекс первого baseline segment. Cancel/archive очищают target и сохраняют прежние revisions/events.
- Добавлены regressions на изменённые условия, candidate/baseline target, idempotency/stale CAS, pause/resume, старую evidence integrity, общий guard, события/их связь с фазой, quota rollback, cancel/archive после паузы и v8→v10 migration.

## Проверки

Изолированная команда запускала `pytest` для:

`tests/test_unit_economics_experiment_control_service.py`, `tests/test_unit_economics_experiment_phase_confirmation_service.py`, `tests/test_planning_workspace_unit_economics.py`, `tests/test_planning_workspace_repository.py`, `tests/test_unit_price_observation_repository.py`, `tests/test_price_experiment_state_machine.py`.

**Результат:** 106 passed in 3.38s. Проверены `py_compile` затронутых Python-модулей и тестов, `git diff --check`; оба прошли. `git diff -- data` пуст.

Промежуточные прогоны выявили устаревшие ожидания schema v9 и неверное предположение теста о ключе guard. Ожидания обновлены для v10, тесты проверяют общий guard по фактическому контракту; финальный связанный прогон зелёный.

## Ограничения и безопасность

- Использованы только synthetic fixtures и новый временный каталог тестов; `data/`, `.env`, ключи, owner DB не менялись.
- Реальные Ozon-запросы, Telegram и работающий бот не запускались.
- Интерфейс Telegram для ввода условий и pause/resume ещё не подключён; его реализация относится к W31. W25 предоставляет repository/service contracts.
- Изменение условий, сообщённое владельцем, остаётся owner-reported; результат не доказывает причинность изменения цены.

## Следующий этап

W26: bounded collection completed phase window через shared operation trace и существующие collectors; корректно представлять частичный результат, отмену, timeout и поздние ответы без фоновых retries.

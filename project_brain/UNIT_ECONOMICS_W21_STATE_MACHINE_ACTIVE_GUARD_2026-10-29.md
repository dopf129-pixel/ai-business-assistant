# W21 — experiment state machine и общий active-SKU guard

Дата: 29.10.2026
Branch: `codex/full-unit-economics-experiments-implementation-20261028`
Incoming code HEAD: `a3296171bafe` (после W20 snapshot/export).
Code commit: `788c6c8abcd9` (`Add experiment state machine and shared SKU guard`).
Task: `LUNA_FULL_UNIT_ECONOMICS_AND_PRICE_EXPERIMENTS_TASK_2026-10-28.md`.

## Результат

- Добавлен pure `UnitEconomicsExperimentStateMachine`: задаёт состояния и допустимые переходы, требует readiness, подтверждения фазы, frozen evidence, сопоставимой baseline, выбранного кандидата и записанного решения владельца. Запрещённые переходы возвращают стабильный безопасный код; state machine не выполняет storage/source I/O.
- Planning Workspace переведён на аддитивную DB schema v7. Новая таблица `planning_active_sku_guards` использует ключ owner/store/product/offer/SKU/sale schema и различает observation, experiment и legacy conflict.
- Migration backfill не переписывает и не удаляет историю. Она поднимает lock из уже активных observation/experiment; старое пересечение типов представляется явной `CONFLICT` записью и разрешается по мере завершения одной из операций.
- Начало observation и claim общего lock выполняются в одной транзакции. Завершение/архивирование observation пересчитывает lock по остающимся активным записям. Добавлена CAS/idempotency транзакция отмены draft/ready experiment; archival использует pure state-machine validation. Фактические phase-confirmation действия намеренно остаются следующими этапами W24–W27, где появятся точные контракты подтверждения, фаз и evidence.
- Внешние API, Telegram runtime, production database, `.env` и owner data не использовались.

## Regression coverage

- `tests/test_price_experiment_state_machine.py`: документированные разрешённые рёбра, обязательные gates, ошибочные действия и побочные эффекты активных переходов.
- `tests/test_planning_workspace_unit_economics.py`: migration v6→v7 с сохранением legacy plan, восстановление lock, conflict marker для исторического overlap, общий guard между observation/experiment, изоляция store, параллельный старт, CAS/idempotent cancel и release с сохранением оставшейся операции.
- `tests/test_planning_workspace_repository.py`, `tests/test_unit_price_observation_repository.py`: обновлён schema-version contract при сохранении прежних repository guarantees.

## Фактические проверки

Изолированный Windows/Python 3.12 профиль в desktop venv, disposable `AI_ASSISTANT_DATA_DIR`, dotenv/plugin autoload выключены, токены Ozon/Telegram удалены из процесса; в `PYTHONPATH` добавлена уже установленная runtime-копия `tzdata`:

```powershell
& 'C:\Users\gelashvilee\Desktop\Ai ассистент\.venv\Scripts\python.exe' -m pytest -q tests/test_price_experiment_state_machine.py tests/test_planning_workspace_unit_economics.py tests/test_planning_workspace_repository.py tests/test_unit_price_observation_repository.py tests/test_unit_price_observation_collection_service.py tests/test_unit_price_observation_result_service.py tests/test_unit_economics_experiment_snapshot_view_service.py tests/test_analytics_export_service.py tests/test_analytics_export_serializer.py
```

Результат: **130 passed in 5.74s**. Дополнительно `py_compile` для изменённых Python-файлов и `git diff --check` — PASS; `git diff -- data` пустой. Реальные Ozon-запросы и бот не запускались.

## Ограничения и следующий этап

State machine описывает полный ожидаемый граф переходов, но repository на W21 реализует только те атомарные mutation contracts, которые уже существуют или не требуют новых phase/confirmation contracts: отмену и архивирование. Подтверждённое начало/окончание baseline/candidate, pause/resume и выбор кандидата зависят от W22–W27. Это не заявляется как готовый пользовательский workflow.

W21 принят. Следующий этап — W22: сохраняемый план эксперимента, scope/metric, bounds, duration, maturity и fixed decision threshold; неполный draft не активируется.

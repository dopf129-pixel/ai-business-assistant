# W28 — сравнение baseline и candidate

Дата: 29.10.2026
Этап: W28 (зависимости W20, W27)
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Статус: завершён. Code commit: `0cda6ec1`; W29 следующий.

## Изменение

Добавлен `UnitEconomicsExperimentPhaseComparisonService` для сравнения двух подтверждённых ценовых фаз. Сервис использует только последнюю неизменяемую полную коллекцию и последнюю готовую оценку каждой фазы. Сравниваются только фазы режима `WINDOW_COST_ALLOCATION` с одинаковыми frozen cost/tax/plan assumptions, непересекающимися окнами одинаковой длительности и timezone, полным financial/returns/Performance coverage, как минимум 30 пригодными единицами на фазу и стабильными контрольными условиями.

Прибыль на единицу рассчитывается как `finance_net − saved COGS − canonical TaxService tax`. Финансовые начисления уже содержат относящиеся к ним удержания. Поэтому отдельные CPC, комиссия, эквайринг и логистика служат данными сверки и не уменьшают прибыль второй раз. Возвраты без подтверждённого распределения товарного остатка блокируют расчёт; строгая когортная модель пока явно несопоставима.

Результат schema v2 сохраняет snapshots/revisions, проценты только при положительной прибыли baseline, округлённую абсолютную дельту и исход по заранее зафиксированному threshold. Округлённая разница ниже порога даёт `NO_CLEAR_DIFFERENCE`; статистическая уверенность и причинный эффект не заявляются. Репозиторий повторно проверяет ссылки/revisions фаз и журналы изменений условий атомарно при записи результата. Старые schema-v1 результаты остаются читаемыми.

## Изменённые файлы

- `app/services/unit_economics_experiment_phase_comparison_service.py` — сравнение, проверки совместимости и арифметика на единицу.
- `app/services/planning_unit_economics_experiment_adapter.py` — schema-v2 allowlist, арифметическая cross-validation и обратная совместимость schema v1.
- `app/services/planning_workspace_repository.py` — атомарный comparison guard для baseline/candidate revisions и событий условий.
- `tests/test_unit_economics_experiment_phase_comparison_service.py` — девять синтетических регрессий.
- `CHANGELOG.md`, `project_brain/CURRENT_STATE.md`, `project_brain/TEST_MAP.md`, журнал W00–W39 — статус и evidence.

## Проверки

- Команда: `pytest -q --tb=short tests/test_unit_economics_experiment_phase_comparison_service.py tests/test_unit_economics_experiment_phase_readiness_service.py tests/test_unit_economics_experiment_phase_collection_service.py tests/test_planning_workspace_unit_economics.py` — **50 passed in 3.41s**.
- Тесты запущены с `PYTHON_DOTENV_DISABLED=1`, плагинами pytest отключёнными и новым временным каталогом хранилища. Все fixture synthetic; owner database, `.env`, credentials, live Ozon API и реальный Telegram bot не использовались.
- `py_compile` для comparison service, adapter и repository — PASS.
- `git diff --check` — PASS; `git diff -- data` — пустой.
- Полный `pytest`/CI нового HEAD планируется в W38–W39 и здесь не заявляется.

## Архитектурный эффект

Minor architectural extension в рамках ранее принятого Decision 064 и Planning Workspace append-only result contract. Добавлен comparison service и расширен versioned result contract; новый источник данных, фоновая задача и внешний вызов не добавлены. Новый архитектурный decision не требуется.

## Ограничения и следующий шаг

Сопоставление описывает наблюдённую прибыль в модели, а не доказывает, что цена вызвала изменение спроса или ДРР. Сохранённая себестоимость и подтверждённая владельцем цена — отдельные допущения, не исторические Ozon-факты. Результаты не меняют цену в Ozon.

Следующий этап W29 — объяснить причины исходов, выбрать лучший только среди реально оценённых кандидатов и append-only записать решение владельца без внешней мутации.

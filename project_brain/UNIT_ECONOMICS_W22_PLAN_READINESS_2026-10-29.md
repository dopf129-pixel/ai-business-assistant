# W22 — план эксперимента и gate готовности

Дата: 29.10.2026
Branch: `codex/full-unit-economics-experiments-implementation-20261028`
Incoming code HEAD: `7d27525c9e11` (W21 documentation commit).
Code commits: `247ad97c0854` (`Persist validated unit economics experiment plans`), `9993bad6b3d7` (`Preserve incomplete experiment draft history`).
Task: `LUNA_FULL_UNIT_ECONOMICS_AND_PRICE_EXPERIMENTS_TASK_2026-10-28.md`.

## Что реализовано

- Добавлен pure `UnitEconomicsExperimentPlanService`. Objective закреплён как `MAX_RUB_PER_UNIT`; новая метрика общей прибыли не допускается.
- Появились точные границы candidate seller price в integer kopecks. Bounds должны быть положительными, упорядоченными и в диапазоне представимой денежной модели. При наличии границ каждый кандидат должен попадать внутрь.
- Плановая длительность сохраняет контракт 3–28 полных локальных дней; default — 7 дней. Порог решения задаётся до сравнения, default `0.01 ₽`, минимальное значение `0.01 ₽`.
- Операционная зрелость записана явно и фиксирована: не меньше 7 полных дней и 30 пригодных единиц на фазу. Это gate достаточности наблюдения, а не статистическая гарантия.
- Exact identity и существующие snapshot/plan references остаются обязательными. Неполный draft можно сохранить без bounds и candidate list, но он получает `INCOMPLETE` и reason codes. Пустой candidate list допустим только в DRAFT; невозможные bounds, неизвестные поля, дубли и кандидаты вне bounds отклоняются.
- Draft конфигурация редактируется только при статусе DRAFT. Каждое изменение — CAS/idempotent state revision и append-only revision payload. Переход в READY сначала проверяет readiness и immutable source references. После READY config и exact identity заморожены; active SKU guard не берётся до подтверждения baseline в последующих этапах.
- Planning Workspace schema v8 — аддитивная trigger migration: прежние данные и записи не переписываются. Старые config без plan extension остаются читаемы; они не объявляются ready по новому плановому контракту, пока владелец не сохранит bounds, maturity и candidate options.

## Проверки

Изолированная Windows/Python 3.12 среда: disposable `AI_ASSISTANT_DATA_DIR`, dotenv и plugin autoload выключены, Ozon/Telegram credentials удалены, добавлена установленная runtime-копия `tzdata`. Внешние API и бот не запускались.

W22 focused profile: **71 passed in 3.93s** по четырём suites `test_unit_economics_experiment_plan_service`, `test_planning_workspace_unit_economics`, `test_planning_workspace_repository`, `test_unit_price_observation_repository`. Дополнительно проверены cancel/archive incomplete drafts и чтение всех сохранённых terminal revisions.

Финальный linked profile W21–W22 плюс frozen snapshot/export:

```powershell
python -m pytest -q tests/test_price_experiment_state_machine.py tests/test_unit_economics_experiment_plan_service.py tests/test_planning_workspace_unit_economics.py tests/test_planning_workspace_repository.py tests/test_unit_price_observation_repository.py tests/test_unit_price_observation_collection_service.py tests/test_unit_price_observation_result_service.py tests/test_unit_economics_experiment_snapshot_view_service.py tests/test_analytics_export_service.py tests/test_analytics_export_serializer.py
```

Результат: **156 passed in 6.76s**. `py_compile`, `git diff --check` PASS; `git diff -- data` пустой. Полный `pytest` остаётся этапом W38–W39.

## Границы этапа

W22 не генерирует цены по спросу и не оценивает эластичность. Владелец задаёт допустимый диапазон, а W23 должен использовать существующие tariff-aware solvers и bounds. Если диапазон или список кандидатов неполон, draft сохраняется и не переходит в READY. Следующий этап — W23: выбрать от 2 до 10 допустимых цен и проверить границы, тарифные разрывы и копеечные значения существующими forward calculations.

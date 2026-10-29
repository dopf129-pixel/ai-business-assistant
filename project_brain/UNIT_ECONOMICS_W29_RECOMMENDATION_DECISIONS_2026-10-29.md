# W29 — объяснимые рекомендации и решения владельца

Дата: 29.10.2026
Этап: W29 (зависимость W28)
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Code commit: `0466d04c`
Статус: завершён; следующий этап — W30.

## Реализация

`UnitEconomicsExperimentRecommendationService` строит безопасную проекцию из уже сохранённого/валидированного результата W28. Для шести исходов возвращаются понятное объяснение, следующий шаг, безопасные причины quality gates, текущие значения ₽/unit и допустимые действия владельца. Текст и reason codes allowlisted; неизвестные причины заменяются общим кодом.

Ранжирование исключает waiting/incomplete/incomparable и устаревшие result revisions. Текущую ревизию передаёт вызывающая сторона; результат включается только когда она совпадает с `latest_result_revision`. Несколько кандидатов ранжируются вместе, только если совпадают baseline collection/readiness revision, frozen economics/snapshot refs, threshold и profit basis. Все кандидаты с одинаковым максимальным PPU сохраняются как ties; несовместимые группы не получают winner.

Planning Workspace schema v11→v12 добавляет `planning_price_experiment_decisions`. Запись решения разрешена только в `CANDIDATE_REVIEW`, для latest результата завершённой candidate-фазы. `SELECT_EVALUATED_CANDIDATE` допускается только если точная ревизия содержит валидное сравнение. `KEEP_BASELINE_PRICE` должна ссылаться на первую baseline-фазу. Продолжение и остановка не имеют выбранной фазы. История append-only, tenant-scoped, связывает решение с state/result revisions, idempotent, CAS-protected, ограничена 100 записями на эксперимент и защищена от update/delete. Финальный выбор может завершить эксперимент, только если он по-прежнему связан с последним результатом; `CONTINUE_TEST` не завершает его.

Решение не запускает API, не меняет цену в Ozon и не хранит свободный текст. Рекомендация вычисляется из immutable результата, поэтому новый источник и вторая формула не добавлены.

## Изменённые файлы

- `app/services/unit_economics_experiment_recommendation_service.py` — объяснение исходов и latest-only compatible ranking.
- `app/services/planning_unit_economics_experiment_adapter.py` — строгий versioned owner-decision allowlist.
- `app/services/planning_workspace_repository.py` — schema v12, tenant-scoped immutable decision ledger, replay/list/complete gates.
- `tests/test_unit_economics_experiment_recommendation_service.py` — outcome, ranking, stale revision and privacy regressions.
- `tests/test_unit_economics_experiment_owner_decision_repository.py` — migration, exact binding, selection, idempotency, quota, isolation, immutability and completion regressions.
- `tests/test_planning_workspace_unit_economics.py` — ожидаемая версия при миграции v8/v9 теперь v12.
- `project_brain/DECISIONS_065.md` — архитектурное решение по журналу owner decisions.
- `CHANGELOG.md`, `project_brain/CURRENT_STATE.md`, `project_brain/TEST_MAP.md`, журнал W00–W39 — этап и evidence.

## Проверки

- Linked Windows/Python profile, временное synthetic хранилище:
  `pytest -q --tb=short tests/test_unit_economics_experiment_recommendation_service.py tests/test_unit_economics_experiment_owner_decision_repository.py tests/test_unit_economics_experiment_phase_comparison_service.py tests/test_unit_economics_experiment_phase_readiness_service.py tests/test_unit_economics_experiment_phase_collection_service.py tests/test_planning_workspace_unit_economics.py tests/test_price_experiment_state_machine.py` — **98 passed in 4.42s**.
- `py_compile` для новых/изменённых Python modules и tests — PASS.
- `git diff --check` — PASS; `git diff -- data` — пустой.
- Тесты отключили dotenv/plugin autoload и использовали новый временный каталог. `.env`, credentials, owner database, live Ozon API и Telegram bot не использовались.
- Полный `pytest`/CI запланирован в W38–W39; этим профилем его не заменяем.

## Архитектурный эффект

Minor-to-major architectural extension: новый recommendation application service и аддитивная DB schema v12 с immutable decision ledger. Расчётный движок, tenant repository и lifecycle authority сохраняются; новые внешние зависимости и контракты Ozon не добавлены. Подробное решение — Decision 065.

## Следующий этап

W30 — guided Telegram экран unit economics, выбор уровня детализации, missing-data actions и возврат к ручному тарифу в исходный draft.

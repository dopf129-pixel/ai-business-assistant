# Q31 — связанные регрессии, ошибки и ограниченный цикл использования

Дата: 27.10.2026
Статус: `VERIFIED_EXISTING` на текущей production-реализации. Q30 остаётся открытым по бизнес-решению.

## Проверки

- Связанный набор 122 тестовых модулей с шаблонами unit price / Telegram unit price / planning workspace / tax / cross-docking / period profit / backup-restore / help discovery: **1085 passed in 34.88s**.
- `tests/test_daily_use_bounded_soak.py` и `tests/test_unit_price_target_planning_service.py::test_search_stays_inside_forward_evaluation_budget`: **3 passed in 3.26s**.
- Тестовые storage/basetemp были изолированы в `.codex-tmp-q31-linked` и `.codex-tmp-q31-soak`; после сверки абсолютных путей и отсутствия reparse points эти созданные для проверки каталоги удалены.
- Учетные данные, owner database, tracked `data/*.json`, Ozon API и реальный бот не использовались.

## Ограничения

- Тестовый цикл ограничен bounded fake/in-process сценариями; это не длительный soak реального Telegram процесса.
- Полный `pytest`, compile/diff checks на итоговом дереве и exact-head CI Windows/Linux/Docker выполняются в Q33 после завершения пользовательской документации.
- Связанный regression profile не закрывает ручное допущение количества продаж; это вопрос Q30, а не ошибка существующего Q31 baseline.

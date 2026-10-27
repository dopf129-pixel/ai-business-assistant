# Q31 — связанные регрессии, ошибки и ограниченный цикл использования

Дата: 27.10.2026
Статус: `VERIFIED` на реализации Q30 с расчетом SKU buyout estimate.

## Проверки

- Связанный набор **175 тестовых модулей** с шаблонами unit price / Telegram unit price / planning workspace / tax / cross-docking / period profit / backup-restore / help discovery: **1374 passed in 39.94s**.
- `tests/test_daily_use_bounded_soak.py` и `tests/test_unit_price_target_planning_service.py::test_search_stays_inside_forward_evaluation_budget`: **3 passed in 3.12s** после Q30 изменений.
- Новый focused Q30 collection/normalizer/model/quality/public-handler profile: **49 passed in 2.37s**; включает full/partial buyout evidence, exact SKU, timezone/date basis, retry, returned-unit disclosure and model comparison.
- Все storage в pytest были временными (`tmp_path`). Credentials удалены из процесса; owner database, tracked `data/*.json`, Ozon API и реальный бот не использовались.
- Учетные данные, owner database, tracked `data/*.json`, Ozon API и реальный бот не использовались.

## Ограничения

- Тестовый цикл ограничен bounded fake/in-process сценариями; это не длительный soak реального Telegram процесса.
- Полный `pytest`, compile/diff checks на итоговом дереве и exact-head CI Windows/Linux/Docker выполняются в Q33.
- Связанный набор использует синтетические source adapters; он не подтверждает фактические показатели магазина и не тестирует live Ozon/Telegram.

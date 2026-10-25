# C04: измерение повторных запросов и пакетного расчёта — 25.10.2026

## Вывод

Измерен текущий путь на детерминированных fake sources. Подтверждённой лишней работы нет, поэтому production-оптимизация не потребовалась. Детали, аналитика, полнота и CSV/JSON используют один owner/store-scoped снимок; явное обновление запускает один новый расчёт сохранённого периода. Пакетный расчёт загружает каталог один раз и получает один source snapshot на выбранный SKU. Общие request/time budgets остаются в силе.

## Таблица измерений

| Сценарий | Логические чтения/каталог | Fake HTTP попытки | Fake финансовые страницы | Fake elapsed | Проверенное поведение |
|---|---:|---:|---:|---:|---|
| Первый отчёт периода | 1 query-service вызов | Не наблюдаются на UI seam | Не наблюдаются на UI seam | Нет стабильного wall-clock порога | Результат строится один раз |
| Тёплое открытие аналитики/деталей/полноты/диагностики | 0 дополнительных query | 0 дополнительных | 0 дополнительных | 0 дополнительных source work | Используется сохранённый snapshot |
| CSV и JSON export, включая support export | 0 дополнительных query | 0 дополнительных | 0 дополнительных | 0 дополнительных source work | Экспортируется сохранённый snapshot |
| Явное обновление отчёта | 1 новый query-service вызов | Внутреннее число зависит от source response | Внутреннее число зависит от source response | Не сравнивается wall clock | Исходный период сохранён, новый snapshot создаётся один раз |
| Batch из 3 SKU на synthetic source | 1 загрузка каталога + 3 snapshot | 6: 2 на SKU | 3: 1 полная fake finance page на SKU | 0,06 fake seconds (10 ms на fake request) | Все строки READY; нет повторного чтения каталога или страницы |

До/после: показатели одинаковы, поскольку C04 не нашёл подтверждённого повторного запроса, который можно безопасно удалить. Нулевое дополнительное чтение при details/export подтверждено тестами C01/B05; точное одно чтение при refresh — тестом C02; числа batch — новой regression C04.

## Ограничения измерений

- UI query fake считает вызов существующего query service, но не раскрывает внутренние HTTP attempts и финансовые страницы. Поэтому эти значения для первого/тёплого отчёта и refresh обозначены как ненаблюдаемые, а не придуманы.
- Batch profile намеренно синтетический: fake source резервирует две попытки и одну полную финансовую страницу на каждый SKU, а fake clock продвигается на 10 ms за запрос. Это воспроизводимый тест orchestration и пагинационных счётчиков, не прогноз latency настоящего Ozon API.
- В production batch по-прежнему выдаёт собственные `http_attempts`, `elapsed_seconds` и лимиты; реальные HTTP-попытки зависят от страниц, retry, cache и источников. Live Ozon не запрашивался.
- Абсолютные wall-clock thresholds в CI не добавлялись. Тест проверяет точные счётчики и fake-clock арифметику, а не скорость общего runner.

## Повторяемые проверки

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTHONPATH = Join-Path (Get-Location).Path 'app'
$env:AI_ASSISTANT_STORAGE_ROOT = Join-Path $env:TEMP 'ai-assistant-daily-readiness-c04'
$env:AI_ASSISTANT_MASTER_KEY=''
$env:AI_ASSISTANT_CACHE_ENABLED='false'
python -m pytest -p no:cacheprovider -q `
  tests/test_unit_price_batch_plan_service.py::test_three_sku_batch_performance_profile_counts_catalog_pages_and_http_attempts `
  tests/test_period_profit_analytics_runtime.py::test_period_comparison_and_owner_exports_reuse_finalized_query_snapshot `
  tests/test_period_profit_analytics_runtime.py::test_diagnostic_refresh_reuses_exact_period_and_owner_store_scope
```

Связанные существующие проверки: `test_period_profit_analytics_runtime.py` подтверждает details/analytics/completeness/diagnostic/CSV/JSON callbacks без нового query; `test_unit_price_batch_plan_service.py` проверяет общий HTTP budget, один catalog load, per-SKU snapshots и explicit refresh; `test_telegram_unit_price_batch_plan_runtime_service.py` проверяет parent budget и отсутствие source reads при локальных edit/export.

Фактический локальный прогон:

- Выбранные три ключевые проверки — **3 passed in 1.01s**.
- Связанный профиль `tests/test_unit_price_batch_plan_service.py tests/test_telegram_unit_price_batch_plan_runtime_service.py tests/test_period_profit_analytics_runtime.py -k 'not production_factory'` — **44 passed, 1 deselected in 1.93s**. Исключён один storage-backed `tmp_path` production factory test из-за ранее подтверждённого Windows ACL ограничения; exact-head CI обязан выполнить его.
- In-memory Python compile для изменённого test module и `git diff --check` фиксируются в заключительном C04/C05 journal check.

Статус C04: `DONE_LOCAL`. Полный CI нового SHA ещё предстоит. Merge, deploy, live API и настоящий бот не запускались.

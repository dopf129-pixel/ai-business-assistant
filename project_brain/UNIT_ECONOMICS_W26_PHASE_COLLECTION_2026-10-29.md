# W26 — сбор фактов завершённой фазы эксперимента

Дата: 29.10.2026  
Ветка: codex/full-unit-economics-experiments-implementation-20261028  
Входной HEAD: f054f641  
Code commit: 332b0c85 — Collect completed unit economics experiment phases

## Результат

- Добавлен UnitEconomicsExperimentPhaseCollectionService: он принимает только активную подтверждённую фазу, проверяет owner/store/SKU/sale schema/цену и точное совпадение owner-confirmed effective timestamp и timezone.
- Сбор допускается лишь после конца всего планового локального окна, не раньше первого полного дня после подтверждения и в разрешённой длине 3–28 дней. Исходное окно не расширяется.
- Переиспользуется UnitPriceObservationCollectionService. Нового retry/background loop нет. Оба уровня делят PeriodProfitOperationTrace; effective cap равен более строгому из бюджета фазы, reader и оставшегося бюджета родителя.
- Arbitrary source reason strings не сохраняются. Метрики, source statuses, причины и бюджет проходят через strict allowlist; raw API rows, SKU-идентификаторы, posting/supply identifiers, названия товаров и credentials не входят в projection.
- Добавлена аддитивная миграция Planning Workspace v10→v11: immutable phase collection snapshots, content hash, quota и atomic append совместно с WAITING_FOR_DATA result revision. Повторный idempotency key возвращает сохранённую ревизию без нового чтения источников. Ошибка результата откатывает snapshot.
- Любая прибыль за фазу остаётся null на W26. Сбор возвращает только факт-агрегаты и provisional gates; финальное сравнение, maturity, strict successful-unit gate и late corrections принадлежат следующим этапам.

## Проверки

Изолированный Windows/Python 3.12 профиль:

tests/test_unit_economics_experiment_phase_collection_service.py  
tests/test_planning_workspace_unit_economics.py  
tests/test_unit_price_observation_repository.py  
tests/test_unit_price_observation_collection_service.py  
64 passed in 3.21s

Профиль использовал только synthetic fixtures и временные SQLite/pytest каталоги. Для Windows Python был задан уже установленный локальный TZif-каталог через PYTHONTZPATH; проектные зависимости и файлы не менялись.

Также прошли py_compile изменённых Python modules, git diff --check и git diff -- data (пусто). Не выполнялись реальные Ozon/API-запросы, запуск Telegram-бота или production действия.

## Следующие ограничения

- Число единиц и возвраты пока сохраняются как source evidence. W27 должен применять минимальную семидневную задержку после окна и 30 подходящих единиц; это операционный gate, не статистическая гарантия.
- Финансовая и Performance-отчётность имеет разные date bases и может перекрываться. Это предупреждения, не доказательство причинного эффекта цены.
- Владелец подтвердил цену/время, но Ozon price history не подтверждена.
- Saved plan cost остаётся допущением, а не наблюдаемой себестоимостью периода.

Статус: W26 завершён; следующий этап W27.

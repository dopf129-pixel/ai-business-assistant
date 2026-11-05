# W40 — устранение замечаний review R1–R5

Дата: 30.10.2026
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Базовый code HEAD до исправлений: `762c5cd53359962a90fec6f8bdf512dc5dfdb246`
Исправляющий commit: `3dd56343ac29339e83d5fbcb4f8d563010876384` (опубликован в PR #722).
Статус: кодовые исправления включены в PR; exact-head Windows/full-verification CI успешен, повторное независимое review и owner acceptance pending.

## Исправления

| ID | Замечание | Исправление и защита от регрессии |
|---|---|---|
| R1 | Snapshot мог получить `COMPLETE`, если собраны даты, но не подтверждена полнота компонентов/сегментов. | `UnitEconomicsWindowSnapshotService` требует полные source evidence для каждого дня, сегмента и компонента. Тесты доказывают, что неполная сумма остаётся неготовой. |
| R2 | Сравнение фаз читало ограниченную первую страницу истории событий и могло пропустить часть интервала. | `UnitEconomicsExperimentPhaseComparisonService` читает страницы по 10 записей с пределом 100, проверяет монотонность offset и закрывается ошибкой при нарушении границ. Добавлены тесты пагинации и fail-closed. |
| R3 | Результат наблюдения терял абсолютный режим рекламных расходов на единицу. | `UnitPriceObservationResultService` сохраняет `advertising_cost_per_unit` и режим источника; поле не подменяется процентным значением. Добавлена регрессия. |
| R4 | На первом запуске не было способа получить требуемое 56-дневное reference окно. | Добавлен `UnitEconomicsReferenceSnapshotCollectionService`, подключён к существующему read-only finance/FBO collector и выведен в Telegram. Сохраняется только полный точный диапазон 56 завершённых локальных дней. Неполный returns coverage, неизвестные типы, нулевой знаменатель и net-credit/review-required данные остаются `PARTIAL` и не записываются как `COMPLETE`. |
| R5 | У владельца не было полного публичного жизненного цикла candidate-фазы. | Telegram runtime теперь поддерживает сбор, maturity evaluation, изменение контрольных условий, завершение фазы, сравнение и решение владельца для baseline/candidate. Завершение атомарно привязывается к последнему READY result и закрывает связанное наблюдение. Сквозной synthetic test проходит обе фазы и подтверждает отсутствие изменения цены Ozon. |

Основные затронутые области: planning repository, phase comparison, snapshot/observation services, Telegram experiment runtime и factory. Добавлен сервис сбора reference snapshot. Код зафиксирован и отправлен отдельным commit `3dd56343`; последующее изменение только документации потребует своей проверки на актуальной голове PR.

## Проверки

- Связанный regression profile (10 файлов): **127 passed in 6.60s**.
- Полный Windows `pytest` без `AI_ASSISTANT_STORAGE_ROOT`: **4,346 passed in 42.30s**.
- `git diff --check`: PASS (есть только стандартные предупреждения Git о LF/CRLF в рабочей копии).
- Проверка `git diff -- data`: пусто; пользовательские данные не изменены.
- Полный pytest временно создал `data/tasks.json.lock`; lock удалён. `data/tasks.json` был восстановлен байт-в-байт из копии до прогона.
- Один первоначальный full-suite запуск выполнялся с неподходящим `AI_ASSISTANT_STORAGE_ROOT` и получил 7 падений в тестах относительных tenant-путей. Этот запуск не считается успешной проверкой; штатный прогон без переменной завершился зелёным.
- Exact-head Windows и full-verification jobs успешны на исправляющем SHA в GitHub Actions runs [41051047996](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/41051047996) и [41051054590](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/41051054590). Полная проверка включает compile, full test suite, production Docker build/smoke и SHA-bound report.

## Границы проверки

- Локальные проверки выполнены на Windows; exact-head CI на исправляющем SHA прошёл Windows и full-verification jobs, включая Docker build/smoke.
- Новый commit/push выполнен, но повторное независимое review ещё не завершено. Если PR получил последующий docs-only commit, перед review следует проверить checks уже на нём.
- Реальные Ozon API, реальный Telegram bot, магазин и SKU не использовались; owner acceptance остаётся pending.
- Merge и deployment не выполнялись.

## Следующий шаг

После завершения документационного follow-up проверить exact-head CI актуального PR, затем повторно пройти R1–R5 в независимом review. Merge/deployment и live owner validation остаются отдельными действиями.

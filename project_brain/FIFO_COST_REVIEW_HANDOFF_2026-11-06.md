# FIFO cost history — независимый review handoff

Дата подготовки: 2026-11-06

## PR и точные ревизии

- Реализационный PR: [#726 — Implement FIFO SKU cost history and late corrections](https://github.com/dopf129-pixel/ai-business-assistant/pull/726), base `main`, ветка `codex/fifo-cost-implementation-20261106`. PR открыт как draft; не слит.
- Спецификация: [PR #725](https://github.com/dopf129-pixel/ai-business-assistant/pull/725).
- Последний code-bearing SHA, на котором локально прошёл полный тестовый набор: `327dcff491354f4a7fe54de33977bfa1e7b50a8f` (`Align seller cost menu test with history export`). После него `127682c8c827f93f92e03e52c52533a807cac950` записал только результаты локального FC34; текущий PR head после handoff-коммита смотреть в GitHub PR #726. Финальные CI должны быть зелёными именно на актуальном PR head, включая этот handoff.
- База PR #726 до начала реализации: `68aa6db09649bdbb4be406d423c6315a8961697b`.

## Состав реализации

До handoff-коммита diff относительно базы включал 122 файла, 30,243 добавления и 152 удаления. Область шире одной функции: нужна архитектурная проверка.

- FIFO-ядро и репозиторий: `app/services/fifo_cost_allocation_service.py`, `fifo_cost_replay_service.py`, `fifo_cost_repository.py`. Выделенная append-only история слоёв, ставок, источников, движений, продаж, возвратов и ревизий аллокации; атомарные preview/confirm, idempotency и compare-and-swap.
- Источники: read-only Ozon collection, нормализаторы запасов/поставок/актов/продаж/возвратов. Отсутствие, частичный ответ и подтверждённый ноль различаются; неполные данные не превращаются в ноль. Digest-ссылки редактированы и доменно разделены.
- Пользовательский ввод: Telegram-история, новая ставка, отложенная поставка и объяснение/экспорт периода. Черновики привязаны к владельцу, магазину, SKU, ревизии и сроку жизни.
- Расчёты и планы: единый current-unit-cost adapter; ограниченное распределение заданного планового количества по слоям; сохраняемая basis в Planning Workspace; read-only explanation для Period Profit. Существующие налоговый и финансовый расчёты остаются каноническими.
- Backup/migration: отдельная `fifo_cost_schema` (текущая версия 11) в tenant SQLite; FIFO-таблицы добавляются аддитивно. Legacy-себестоимость не импортируется в FIFO автоматически, `planning_schema` и `PRAGMA user_version` не подменяются FIFO-версией. Проверки покрывают upgrade/rollback/future-schema и round-trip через существующий backup/restore.

## Проверочная база

- Полный Windows прогон на Python 3.12.10 / pytest 8.4.2: `python -m pytest -q` — **4,792 passed in 50.14s**. Один устаревший тест ожидал меню до добавления кнопки экспорта FIFO-истории; актуализировано только ожидание теста.
- `python -m compileall -q app tests` и `git diff --check` — PASS.
- Независимая числовая матрица N01–N24; FC32 перебирает все 6 порядков трёх продаж через слои `2×10 ₽ + 3×20 ₽ + 4×30 ₽`: всегда 170.00 ₽ COGS, 8 единиц списано и 1 осталось. Повторные чтения разных периодов не меняют сумму или ревизию.
- Точный pre-test snapshot для всех 6 файлов `data/` восстановлен после побочного изменения тестом; повторная сверка длины/SHA-256: 6/6 совпадений, дополнительных файлов нет. В diff PR нет `data/`, `.env` или пользовательских выгрузок.
- Локальный Docker отсутствует. Workflow `.github/workflows/verify.yml` на Ubuntu выполняет полный набор, production Docker build и runtime/import smoke; Windows job также выполняет полный набор. Проверка, относящаяся к сдаче, — только результат этих job для актуального SHA в PR #726; старый workflow run не считать доказательством.
- Нет реального Ozon/Telegram-запроса, запуска бота, развёртывания или пользовательской приёмки.

## Известные ограничения и блокеры готовности

Эта реализация **не доказывает фактическую FIFO-прибыль магазина**. Упрощённая FIFO — правило распределения затрат по общему остатку SKU, а не прослеживание выбранной Ozon физической партии.

1. `FifoCostAnchorService` пока не подключён к Telegram: новый неинициализированный SKU владелец не может настроить в боте end-to-end.
2. Позднее сообщение сохраняет документальное evidence/draft, но не выполняет историческую реконструкцию и commit FIFO replay.
3. Физическая дата продажи и общий cutoff остатков/финансовых начислений не подтверждены. Фактический Period Profit COGS остаётся `SOURCE_BLOCKED`; нельзя включать его только потому, что синтетические тесты зелёные.
4. Коррекции с несколькими переходами стоимости и связанными возвратами/непродажными движениями закрыты fail-closed.
5. Реальная приёмка владельцем не выполнялась: `USER_VALIDATION_PENDING`.

Не ослаблять эти запреты ради прохождения CI или демонстрации прибыли. Дальнейшее решение по продуктовой готовности требует review, подключения Telegram начального якоря, подтверждённых источников/cutoff и отдельной безопасной приёмки владельцем.

## Проверки GitHub Actions

- Run `42278932818` (workflow Verify, run 3371) завершился `success` на точном PR SHA `cd39a679a92fdef70f89db8effc8534a6c2ef697`.
- Windows job: compile и полный pytest — PASS. Ubuntu job: compile, полный pytest, production Docker build, runtime health check и import smoke — PASS.
- PR #726 переведён в ready-for-review после всех успешных job. Точный SHA `18ee4e6e459d2aa6a324ae0ef7d5a40e6828baa5`, run `42279830501`, conclusion `success`. Финальный статусный commit этого handoff — docs-only и запускает тот же workflow; точная актуальная голова и результат проверяются по GitHub PR #726. Слияния не было.

## Приоритеты независимого review

- **P1 — `fifo_cost_repository.py` (около 6 тыс. строк):** сериализация на owner/store/SKU, транзакционные границы, CAS/idempotency, append-only и миграции v1–v11; отказ по версии/частичному DDL; взаимодействие с существующей tenant DB.
- **P1 — доверие к источникам:** границы даты продажи/остатков, reserved и transit overlap, допустимость «пусто» против zero, replay/correction refusal. Убедиться, что никакой projection не снимает factual cutoff block.
- **P1 — COGS/возвраты/движения:** ровно одно списание физической продажи, повторные финансовые строки, возврат/restock и запрет неверного fallback к текущей legacy стоимости после FIFO cutover.
- **P2 — Telegram state:** callback binding владельца/магазина/SKU/revision/TTL, stale confirmation, restart invalidation, длинные сообщения и совместимость старого меню.
- **P2 — планы и exports:** frozen FIFO basis без дополнительных source calls, ручная стоимость остаётся только сценарием, ограниченный экспорт не теряет строки и не утечёт ID/digest.
- Сверить handoff с актуальным PR head, GitHub checks и фактическим diff до рекомендации по слиянию. Слияние в рамках текущего задания запрещено.

## Воспроизведение

```powershell
$env:PYTHONPATH = 'app'
python -m pytest -q
python -m compileall -q app tests
git diff --check
```

Точный Windows/Linux/Docker результат привязан к текущему `head` PR #726. Основной CI workflow: `.github/workflows/verify.yml`.

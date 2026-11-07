# FIFO cost history — независимый review handoff

## Актуальный статус review — 2026-11-07

Этот раздел заменяет более ранние статусы и результаты ниже. Исторические строки оставлены для контекста, но не описывают текущую ревизию.

- На момент review PR [#726](https://github.com/dopf129-pixel/ai-business-assistant/pull/726) открыт и готов к review; ветка `codex/fifo-cost-implementation-20261106`, база `main`.
- Повторное review кода проверило SHA `26278ea4236f16a25d83d80b3405f6651811e7f9` (`Record FIFO navigation CI verification`). Предыдущий кодовый commit: `7896289a14a127eb097800225f28fbf0915a46da` (`Fix FIFO navigation after CSV and unit economics resume`). База PR: `68aa6db09649bdbb4be406d423c6315a8961697b`. В этой правке обновляется только review-документация; точную текущую голову и её CI следует сверять в PR.
- Последний review повторно проверил голову `26278ea4`: новых подтверждённых дефектов, блокирующих слияние, не найдено; техническая рекомендация — сливать. Размер PR — 132 файла, 35 075 добавлений и 169 удалений.
- Последние исправления закрывают активные FIFO-вводы после принятого CSV preview и действительного возврата из карточки юнит-экономики к другому SKU. Регрессии проверяют, что недействительный CSV и устаревшая кнопка сохраняют текущий ввод.
- Связанный профиль review: **532 passed in 15.23s**. Полный Windows `pytest -q`: **4,851 passed in 51.12s** на кодовой голове `7896289a`; точная PR-голова `26278ea4` прошла GitHub Actions run [42371081306](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/42371081306): Windows, Linux, production Docker build и runtime smoke — success.
- До/после проверки подтвердили, что 5 исходных файлов `data/` не изменились; рабочая копия чистая.
- Архитектурная классификация — **Architecture Review Required** из-за масштаба FIFO-функциональности; review завершён. Слияние требует сохранять продуктовые ограничения ниже: фактический FIFO COGS не подтверждён и остаётся заблокированным.
- Живые Ozon/Telegram вызовы, запуск бота и развёртывание не выполнялись.

Дата обновления: 2026-11-07

## PR и точные ревизии

- Реализационный PR: [#726 — Implement FIFO SKU cost history and late corrections](https://github.com/dopf129-pixel/ai-business-assistant/pull/726), base `main`, ветка `codex/fifo-cost-implementation-20261106`. Текущий статус и SHA указаны в разделе «Актуальный статус review» выше.
- Спецификация: [PR #725](https://github.com/dopf129-pixel/ai-business-assistant/pull/725).
- Последний проверенный code-bearing SHA: `7896289a14a127eb097800225f28fbf0915a46da`; повторное review кода и exact-head CI проверены на SHA `26278ea4236f16a25d83d80b3405f6651811e7f9`. После обновления handoff актуальную голову и её CI следует брать из PR.
- База PR #726 до начала реализации: `68aa6db09649bdbb4be406d423c6315a8961697b`.

## Состав реализации

Проверенный diff относительно базы включал 132 файла, 35 075 добавлений и 169 удалений до обновления этого handoff. Область шире одной функции и требует архитектурной классификации.

- FIFO-ядро и репозиторий: `app/services/fifo_cost_allocation_service.py`, `fifo_cost_replay_service.py`, `fifo_cost_repository.py`. Выделенная append-only история слоёв, ставок, источников, движений, продаж, возвратов и ревизий аллокации; атомарные preview/confirm, idempotency и compare-and-swap.
- Источники: read-only Ozon collection, нормализаторы запасов/поставок/актов/продаж/возвратов. Отсутствие, частичный ответ и подтверждённый ноль различаются; неполные данные не превращаются в ноль. Digest-ссылки редактированы и доменно разделены.
- Пользовательский ввод: Telegram-история, новая ставка, отложенная поставка и объяснение/экспорт периода. Черновики привязаны к владельцу, магазину, SKU, ревизии и сроку жизни.
- Расчёты и планы: единый current-unit-cost adapter; ограниченное распределение заданного планового количества по слоям; сохраняемая basis в Planning Workspace; read-only explanation для Period Profit. Существующие налоговый и финансовый расчёты остаются каноническими.
- Backup/migration: отдельная `fifo_cost_schema` (текущая версия 12) в tenant SQLite; FIFO-таблицы добавляются аддитивно. Legacy-себестоимость не импортируется в FIFO автоматически, `planning_schema` и `PRAGMA user_version` не подменяются FIFO-версией. Проверки покрывают upgrade/rollback/future-schema и round-trip через существующий backup/restore.

## Проверочная база

- Полный Windows прогон на Python 3.12.10 / pytest 8.4.2: `python -m pytest -q` — **4,851 passed in 51.12s** на кодовом SHA `7896289a14a127eb097800225f28fbf0915a46da`.
- `python -m compileall -q app tests` и `git diff --check` — PASS.
- Независимая числовая матрица N01–N24; FC32 перебирает все 6 порядков трёх продаж через слои `2×10 ₽ + 3×20 ₽ + 4×30 ₽`: всегда 170.00 ₽ COGS, 8 единиц списано и 1 осталось. Повторные чтения разных периодов не меняют сумму или ревизию.
- Точный pre-test snapshot пяти исходных файлов `data/` совпал до и после финальных проверок; новых тестовых файлов не осталось. В diff PR нет `data/`, `.env` или пользовательских выгрузок.
- Локальный Docker отсутствует. Workflow `.github/workflows/verify.yml` на Ubuntu выполняет полный набор, production Docker build и runtime/import smoke; Windows job также выполняет полный набор. Проверка, относящаяся к сдаче, — только результат этих job для актуального SHA в PR #726; старый workflow run не считать доказательством.
- Нет реального Ozon/Telegram-запроса, запуска бота, развёртывания или пользовательской приёмки.

## Известные ограничения и блокеры готовности

Эта реализация **не доказывает фактическую FIFO-прибыль магазина**. Упрощённая FIFO распределяет затраты по общему остатку SKU и не прослеживает конкретную физическую партию на Ozon.

1. Фактический Period Profit COGS остаётся `SOURCE_BLOCKED`, пока владелец не подтвердит общий cutoff остатков и продаж и пока соответствие источников продаж и движений не подтверждено.
2. Последующие ставки требуют полного сверенного остатка; переходы и поздние исправления, которые нельзя однозначно пересчитать, остаются fail-closed.
3. Реальная приёмка владельцем на магазине не выполнялась: `USER_VALIDATION_PENDING`.

Не снимать эти ограничения ради прохождения CI или демонстрации прибыли. Плановые оценки и фактическая прибыль должны оставаться явно различимыми.

## Проверки GitHub Actions

- На reviewed code SHA `26278ea4236f16a25d83d80b3405f6651811e7f9` GitHub Actions run [42371081306](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/42371081306) завершился `success`: Windows/Linux full verification, production Docker build и runtime smoke.
- Для обновлённого handoff точный актуальный SHA и результат нового CI проверяются в PR; более ранние run/SHA в первоначальной версии документа не являются доказательством проверки новой головы.

## Области повторного review

- **P1 — `fifo_cost_repository.py` (около 6 тыс. строк):** сериализация на owner/store/SKU, транзакционные границы, CAS/idempotency, append-only и миграции v1–v12; отказ по версии/частичному DDL; взаимодействие с существующей tenant DB.
- **P1 — доверие к источникам:** границы даты продажи/остатков, reserved и transit overlap, допустимость «пусто» против zero, replay/correction refusal. Убедиться, что никакой projection не снимает factual cutoff block.
- **P1 — COGS/возвраты/движения:** ровно одно списание физической продажи, повторные финансовые строки, возврат/restock и запрет неверного fallback к текущей legacy стоимости после FIFO cutover.
- **P2 — Telegram state:** callback binding владельца/магазина/SKU/revision/TTL, stale confirmation, restart invalidation, длинные сообщения и совместимость старого меню.
- **P2 — планы и экспорты:** frozen FIFO basis без дополнительных source calls, ручная стоимость остаётся только сценарием, ограниченный экспорт не теряет строки и не раскрывает ID/digest.
- Повторная сверка кода, diff и CI выполнена для SHA `26278ea4236f16a25d83d80b3405f6651811e7f9`; новых подтверждённых блокирующих замечаний нет. Рекомендация — слияние после обновления handoff и описания PR и проверки CI итоговой головы.

## Воспроизведение

```powershell
$env:PYTHONPATH = 'app'
python -m pytest -q
python -m compileall -q app tests
git diff --check
```

Точный Windows/Linux/Docker результат привязан к текущему `head` PR #726. Основной CI workflow: `.github/workflows/verify.yml`.

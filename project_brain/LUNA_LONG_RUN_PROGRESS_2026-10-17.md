# Журнал выполнения Luna A–G — 17.10.2026

Журнал продолжения для `LUNA_LONG_RUN_PRODUCT_TASK_2026-10-17.md`. После каждого этапа сверять состояние с деревом, обновлять этот журнал и документацию, затем двигаться к следующему доступному этапу. Слияние и развёртывание не входят в поручение.

## A00 — снимок исходной точки

- Статус: **VERIFIED**.
- Начало: 17.10.2026.
- Исходная ветка подготовки: `codex/luna-long-run-product-task-20261017`; рабочая ветка: `codex/product-workbench-20261017`.
- Исходный HEAD: `91aac988aa067082434704095cc61a2400b06159`, родитель `3f7923ced48ba9434fdf5930d1f55431e0eacedd`.
- База `main`: `c55434327f50134324a5ca58e2f084854b809832`.
- PR #697 перепроверен через GitHub 17.10.2026: открыт, не слит, mergeable; head `3f7923ced48ba9434fdf5930d1f55431e0eacedd`, base `main` на `c55434327f50134324a5ca58e2f084854b809832`.
- Рабочее дерево до продуктовых изменений: пользовательские `data/tasks.json`, `data/users.json` изменены; сохранены без редактирования и staging. SHA256 на старте: tasks `8F7FFF206A4748DE6EFB3E5DCABABD07E3341188A7326383A21D966B73710698`; users `0E8D6AE4BF9E2842F5055502B5B94C0E9244F0A5F002B3ED76092E9A73488BE2`.
- Обнаружены существующие тестовые временные каталоги с ограничением Windows ACL и `data/tasks.json.lock`. Сохранить; не менять ACL и не удалять каталоги. Эти пути не входят в git diff по tracked файлам.
- Перед изменениями прочитаны `AGENTS.md`, `CURRENT_STATE.md`, `DECISIONS.md`, `TEST_MAP.md`, `ROADMAP.md`, полное ТЗ и аудит основания. Архитектура PR #697 и числовые примеры сверены ранее и повторно проверены как актуальные по SHA.
- Изменения A00: переименование текущей ветки; создание этого журнала; фиксация исполняемого поручения. Production code и тесты не менялись.
- Проверки: GitHub PR metadata — успешно; локальные SHA/base/head сверены; хэши user JSON записаны; ACL каталоги определены; полный pytest на A00 не нужен, код не менялся.
- Следующий шаг: A01 — пройти текущие call paths и подтвердить публичные точки расширения/budget/snapshot, затем записать только конкретные риски и совместимость.

## A01 — повторный review архитектурных точек расширения

- Статус: **VERIFIED**.
- Проверена production-реализация на базе PR #697 head `3f7923ced48ba9434fdf5930d1f55431e0eacedd`.
- `ProductBusinessDecisionQueryService.query_all()` загружает весь каталог, оборачивает вычисление в history/proposal/task lifecycle и прекращает весь результат на первой ошибке. Внешнего публичного read-only selected-row API нет. Для обзора нужен публичный projection contract; существующие callers оставить на старом пути.
- `_query_product()` валидирует и собирает decision по существующим метрикам/economics/input provider/decision service; сама запись истории находится отдельно в `_with_decision_history()`. Это позволяет добавить узкий public method, переиспользующий вычислительное ядро, но исключающий history/proposal/draft decoration.
- `UnitPriceScenarioSource._load_snapshot()` всегда активирует новый `PeriodProfitOperationTrace` с 60 секундами/64 запросами и затем сбрасывает ContextVar. Унаследованный лимит может быть потерян. `load_snapshot()` follower ждёт `Event` фиксированно 61 секунду. При новом grouped вызове эти два пути должны принимать явный parent operation context; одиночный публичный flow сохранить.
- Ozon clients уже резервируют physical attempts через текущий trace: обычный Ozon client — каждую retry attempt, Performance client — запрос. Существующий trace ограничивает один trace, но не умеет делить time/request cap parent/child. Новое расширение должно сохранить standalone поведение.
- `UnitPriceScenarioService.calculate()` — pure forward calculation, `UnitPriceTargetPlanningService.solve()` перепроверяет цену через forward result и ограничен 128 вычислениями. Новые builders делегируют им.
- `telegram_api_bot._send_result()` фиксирует caption всех файлов как инструкцию для CSV себестоимости; `SellerCostTableService.import_csv()` требует точные четыре заголовка. Ввести отдельный outgoing document kind, сохранив существующий caption и import schema.
- Существующий operation trace содержит сырые SKU/posting identity, события и stack dump; его нельзя отдавать пользователю как безопасный diagnostic без отдельной whitelist projection.
- Решения 036–045 и текущие finance/TaxService/Return COGS contracts повторно просмотрены по ТЗ. Новый A–G контур остаётся read-only и transient; новый архитектурный decision сейчас не требуется.
- Findings: всё выше — `VERIFIED_BEHAVIOR` и prerequisites, новых подтверждённых production defects не заявлено.
- Проверки: чтение actual code paths, factory/Telegram routes, trace/API reservation, cost import и test modules — пройдено; code не менялся, отдельный pytest не запускался.
- Следующий шаг: A02 — добавить parent-aware bounded operation trace и cooperative cancel с regressions, сохранив standalone defaults.

## A02 — общий budget, deadline и отмена

- Статус: **VERIFIED**.
- Изменён `PeriodProfitOperationTrace`: дочерний trace наследует минимальный deadline и общий attempt cap по полной цепочке parent-ов; reservation для всех уровней атомарна под общим lock. Локальный cap дочернего source дополнительно действует. Отмена child изолирована от sibling/parent, отмена parent распространяется на потомков.
- `UnitPriceScenarioSource.load_snapshot(..., operation_trace=...)` принимает только trace contract. Для новых групповых вызовов source создаёт дочерний trace; старые standalone вызовы сохраняют собственные 60 секунд/64 запроса. `Event.wait` ограничен source ceiling и оставшимся parent time; checks стоят до строки источника, перед циклом discount days и после возврата источника. Поздний результат после отмены возвращает controlled error и не попадает в source cache.
- Ozon `base_ozon_client` получает активный дочерний trace через существующий ContextVar и продолжает резервировать каждую физическую retry attempt. Перенос родительского trace восстанавливается `finally`; endpoint/API структуры не менялись.
- Добавлены регрессии parent deadline, общего cap, конкурентной гонки двух child traces, локальной/root cancellation, физического запроса через `OzonClient`, in-flight wait clamp, explicit parent trace propagation/restoration и запрета кэшировать результат после отмены.
- Проверка: **21 passed, 1 deselected** (`test_long_running_trace_writes_secret_free_worker_snapshot`, существующий тест зависит от `tmp_path`; Windows ACL блокирует чтение/cleanup basetemp). `compileall` изменённых app/test файлов — успешно; `git diff --check` — успешно. Полный pytest ещё не запускался; он обязателен на A04 и CI.
- Первые две попытки pytest для baseline не использовали `PYTHONPATH=app`; они остановились при collection и не считаются кодовым дефектом. Повтор с корректным import path показал отдельную WinError 5 на pytest temp tree. Успешный focused запуск отключил только tmpdir fixture и выбрал все остальные тесты этого набора. Не меняли ACL и не удаляли temp data.
- Изменения A02: `app/services/period_profit_operation_diagnostics.py`, `app/services/unit_price_scenario_source.py`, соответствующие два test modules. CHANGELOG/CURRENT_STATE/TEST_MAP/ROADMAP обновлены. Никаких data/** файлов не изменяли намеренно.
- Проверяемый commit A02 будет оформлен после фиксации текущей документации. Следующий шаг: A03 — scoped in-memory snapshots для новых обзорного и batch consumers.

## Матрица этапов

Статусы: `NOT_STARTED`, `IN_PROGRESS`, `IMPLEMENTED`, `VERIFIED`, `BLOCKED`. `IMPLEMENTED` означает код есть, `VERIFIED` — проверки этапа успешны.

| Этап | Статус | Ветка/base/head | Результат и проверки | Документы | Следующий шаг / блокер |
|---|---|---|---|---|---|
| A00 | VERIFIED | `codex/product-workbench-20261017` / PR #697 head / `91aac98` | PR открыт; refs и data SHA сохранены | этот журнал; CURRENT_STATE; ROADMAP | A01 |
| A01 | VERIFIED | `codex/product-workbench-20261017` / production base `3f7923c` | подтверждены public-path, budget, snapshot и file boundaries | этот журнал; audit | A02 |
| A02 | VERIFIED | `codex/product-workbench-20261017` / base `91aac98` | parent/child deadline, shared atomic cap, cancel and source wait regressions; 21 passed, 1 ACL-bound deselected | code + two test modules; CHANGELOG; CURRENT_STATE; TEST_MAP; ROADMAP | A03 |
| A03 | IN_PROGRESS | `codex/product-workbench-20261017` / base `91aac98` | define scoped snapshot helper | этот журнал | implement owner/store/generation/copy/TTL/LRU |
| A04 | NOT_STARTED | — | — | — | тесты, docs, CI основания |
| B00 | NOT_STARTED | — | — | — | зависит от A04 |
| B01 | NOT_STARTED | — | — | — | зависит от B00 |
| B02 | NOT_STARTED | — | — | — | зависит от B01 |
| B03 | NOT_STARTED | — | — | — | зависит от B02 |
| B04 | NOT_STARTED | — | — | — | приёмка обзора |
| C00 | NOT_STARTED | — | — | — | зависит от A04 |
| C01 | NOT_STARTED | — | — | — | зависит от C00 |
| C02 | NOT_STARTED | — | — | — | зависит от C01 |
| C03 | NOT_STARTED | — | — | — | зависит от C02 |
| C04 | NOT_STARTED | — | — | — | зависит от C03 |
| C05 | NOT_STARTED | — | — | — | приёмка пакета |
| D00 | NOT_STARTED | — | — | — | зависит от C05 |
| D01 | NOT_STARTED | — | — | — | зависит от D00 |
| D02 | NOT_STARTED | — | — | — | зависит от D01 |
| D03 | NOT_STARTED | — | — | — | приёмка чувствительности |
| E00 | NOT_STARTED | — | — | — | зависит от A04 |
| E01 | NOT_STARTED | — | — | — | зависит от E00 |
| E02 | NOT_STARTED | — | — | — | зависит от E01 |
| E03 | NOT_STARTED | — | — | — | зависит от B04/C05/D03 |
| E04 | NOT_STARTED | — | — | — | приёмка выгрузок |
| F00 | NOT_STARTED | — | — | — | зависит от A02/E00 |
| F01 | NOT_STARTED | — | — | — | зависит от F00 |
| F02 | NOT_STARTED | — | — | — | зависит от F01 |
| F03 | NOT_STARTED | — | — | — | приёмка диагностики |
| G00 | NOT_STARTED | — | — | — | зависит от B04/C05/D03/E04/F03 |
| G01 | NOT_STARTED | — | — | — | полный pytest/CI/Docker |
| G02 | NOT_STARTED | — | — | — | review handoff и итог |

## Архитектурные выводы

- A02 реализует trace hierarchy без нового job framework: один root owns deadline/request reservation; child сохраняет меньший локальный cap и локальный counter. Отмена cooperative и scope-safe.
- Новые bounded snapshots (A03) будут самостоятельным helper только для overview/batch consumers с одинаковыми owner/store/generation/TTL invariants.
- Для B отдельный read-only projection method должен повторно использовать decision core и не проходить через history/proposal/draft side effects.

## Коммиты и PR

| Артефакт | Статус |
|---|---|
| PR #697 | Открыт, не слит; внешний dependency и base новых веток |
| PR модулей A–G | Ещё нет |

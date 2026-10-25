# Основание ТЗ на ежедневную эксплуатацию — 25.10.2026

## Что поручил владелец

Разбить четыре направления на конкретные этапы для GPT Luna: реальные сверки, полнота расчётов, удобство ежедневной работы и эксплуатация. Результат подготовки — `LUNA_DAILY_USE_READINESS_TASK_2026-10-25.md`, 30 этапов. Реализация этой подготовкой не запущена.

Прежняя оценка готовности около 80% была субъективной. Фиксированного полного product backlog и измеренного процента завершения нет; завершение нового ТЗ не должно автоматически считаться «100% готовности».

## Проверенная база

- Основной checkout: `C:/Users/gelashvilee/Desktop/Ai ассистент`; локальный main `7e6eabdeba34a822434e5ef417a135995628cc41`.
- Код нового кросс-докинга прочитан в `C:/Users/gelashvilee/.codex/worktrees/cross-docking-x00-x01/Ai ассистент`, ветка `codex/cross-docking-x00-x01`, head `698c9f8bb9c4b8f5acc6b4fdcb475c1062e658ea`; рабочее дерево этого worktree чистое.
- GitHub PR [#712](https://github.com/dopf129-pixel/ai-business-assistant/pull/712) при подготовке открыт, не слит, base main `7e6eabde...`, head совпадает. Повторный review в текущем диалоге не оставил блокирующих замечаний.
- Verify [40168559070](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/40168559070) проверен в предыдущем review: Windows/Linux по 3 647 passed, compile и Linux Docker build/runtime smoke successful. Во время подготовки markdown новый тестовый прогон не запускался.
- Основной checkout содержит ранее изменённые `data/tasks.json`, `data/users.json`, lock, untracked review-документы и множество scratch directories с Windows ACL restrictions. Они не являются новым diff этого поручения и не должны быть очищены/добавлены в commit.

## Чтение и подтверждённые наблюдения

Прочитаны актуальные части CURRENT_STATE, DECISIONS, TEST_MAP, ROADMAP, README, существующие задания/журналы planning workspace и cross-docking; сопоставлены текущие public service/lifecycle/storage contracts. Это аудит постановки задач, а не новый полный архитектурный review продукта.

| Наблюдение | Проверенные точки | Следствие для ТЗ |
|---|---|---|
| Уже есть финансовые расчёты, диагностика полноты, короткие/подробные views и source snapshots | `assistant_period_profit_runtime_service.py`, `period_profit_completeness_view.py`, diagnostics/export services | Дорабатывать существующие проекции и UX; не заказывать новый financial engine или competing completeness registry |
| Есть single/batch калькулятор, сохранённые планы, revisions, plan/fact и exports | planning services, README, task H–O | Новые сценарии должны сохранить v1/v2, historical snapshots, CAS и tenant isolation |
| PR #712 добавляет сложный 56-дневный источник | cross-docking services и decisions 052–054 | Базу перепроверять; один акт не доказывает полный знаменатель, продажи не являются supplied units |
| Есть start/status/stop и kernel-backed singleton | `start_bot.ps1`, `status_bot.ps1`, `stop_bot.ps1`, `telegram_bot_control.py`, `bot_instance_lifecycle_service.py` | Не создавать второй lifecycle; updater переиспользует эти функции |
| Launcher при существующем venv проверяет только несколько импортов | `start_bot.ps1` | Проверить обновление зависимостей при изменённом requirements; это основание для сценария, не заявление о случившемся production failure |
| Разрешение storage paths зависит от env и tenant; legacy paths сохраняются | `tenant_storage.py`, SQLite repositories | Backup нельзя ограничить предположением «всё в .runtime-data» без D00 inventory |
| Как минимум один repository создаёт schema при конструировании | `expense_repository.py` | Для чтения/тестов нельзя случайно строить factory на реальной storage |
| Есть local side-effect-free healthcheck и build/support metadata | `runtime_healthcheck.py`, `app_build_metadata_service.py`, support exporter | Доработать существующую диагностику; не делать сетевой Ozon healthcheck по умолчанию |
| Есть исторические backup-файлы, но это не доказательство поддерживаемого restore workflow | инвентаризация имён и документов, без чтения содержимого backup/секретов | Заказать согласованный backup/restore drill и явный manifest contract |
| Верхние legacy документы содержат старые «PR открыт» и будущие статусы уже реализованных модулей | ROADMAP, старые task progress | Вести свежий указатель и сохранить историю; не повторять работу по старой пометке |

Новых подтверждённых code defects этим аудитом не объявлено. Предложения A–D — приёмка, развитие и воспроизводимая проверка возможных gaps. Любой bug fix в исполнении требует доказательства актуального нарушения.

## Реальные источники и границы доказательств

Проверено наличие только ранее названных владельцем файлов в Downloads. Доступны оба августовских отчёта начислений, месячная реализация, returns `16_03_30`, orders CSV, однодневная оборотная ведомость и акт supply `2000070135564`. Returns `14_57_11` не найден. Файлы заново не анализировались, не копировались и не менялись; финансовые цифры в ТЗ — явно помеченные результаты прошлой пользовательской сверки.

Существующие наблюдения по Analytics/Returns/supply API полезны для fixtures, но не подменяют актуальную проверку полного фильтра/пагинации. Отчёт возвратов и текущее состояние отправлений могут иметь разные основы дат. Число строк реализации и число финансовых операций имеют разное зерно. Эти различия требуется сохранить в acceptance matrix.

## Выбранные границы исполнения

- A проверяет реальные отчёты локально без загрузки их в учётные базы; новое средство сверки остаётся narrow offline tool.
- B улучшает существующие completeness/source contracts, не вводя новые цепочки гейтов или автоматические учётные действия.
- C сохраняет полную информацию в деталях/выгрузках, сокращая основной экран и лишние HTTP reads.
- D добавляет локальные эксплуатационные функции; destructive restore/production launch в разработке не выполняются. Backup по умолчанию без секретов; для credential recovery требуется исходный master key.
- E отдельно сдаёт проверенный код и описывает ещё не выполненную внешнюю приёмку владельца. Длительная настоящая эксплуатация не подменяется fake-only tests.

Рутинные решения по коду/оформлению Luna принимает самостоятельно. Изменение финансового правила, разрешение новых Ozon mutations или учётного commit требует отдельного решения владельца.

## Проверки подготовки

Подготовка меняет только новые markdown-документы и актуальные указатели. Проверены **30 уникальных stage IDs**, совпадающие 30 строк журнала, **36 существующих code/document paths** на базе PR #712, UTF-8, парность markdown fences и отсутствие trailing whitespace новых файлов. `git diff --check` изменённых tracked документов прошёл. Зависимости проверены по порядку: B/C/D используют подготовку A, финальная сверка A04 получает их результаты, D updater зависит от backup/restore, E объединяет приёмку.

Unit/full tests для markdown-подготовки не запускались: implementation не менялась. Запуск настоящего бота, Ozon/Telegram, backup/restore пользовательских данных, merge/deploy не выполнялся.

## Отчёт подготовки по AGENTS.md

1. **Изменение:** локальная ветка `main`, HEAD `7e6eabdeba34a822434e5ef417a135995628cc41`; новых commits/PR не создавалось. Подготовлены этапы для отдельной будущей реализации, а не новый функционал.
2. **Файлы:** добавлены task, audit и progress от 25.10.2026; изменены только указатели в CHANGELOG, CURRENT_STATE и ROADMAP. Удалённых файлов нет.
3. **Архитектура:** No architectural impact для подготовки; будущие backup/update границы требуют отдельного architecture review реализации.
4. **Сохранено:** production code, data/tasks.json, data/users.json, credential files, SQLite, существующие lock/temp/untracked review files; diff прежних пользовательских изменений не включён в подготовку.
5. **Проверки:** структурная проверка 30 этапов/журнала/36 путей, markdown/UTF-8/whitespace и diff-check успешны. Тесты приложения не нужны для docs-only изменения.
6. **Документация:** CHANGELOG/CURRENT_STATE/ROADMAP ссылаются на новые документы. TEST_MAP и DECISIONS не менялись: новых tests/реализованных архитектурных решений нет.
7. **Классификация:** Normal Change — подготовка документации.
8. **Следующее действие:** запуск Luna с новым ТЗ, начиная S00; реализацию автоматически этой подготовкой не начинать.

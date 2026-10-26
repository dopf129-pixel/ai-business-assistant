# Журнал: завершение существующих функций бота

Дата подготовки: 26.10.2026.
Статус исполнения: IN_PROGRESS.
ТЗ: LUNA_EXISTING_FUNCTIONALITY_COMPLETION_TASK_2026-10-26.md.
Основание: EXISTING_FUNCTIONALITY_COMPLETION_AUDIT_2026-10-26.md.

## Точка продолжения

Z20 проверен: отдельная чистая проверочная копия, synthetic storage/temp/profile и локальный pytest-профиль. Следующий этап — Z03.

Проверенная удалённая база: main после PR #712–#717, merge SHA 89eb9224c3e9ec2126f58dc4d38794b33c2a2cc0. Локальная основная папка осталась на 7e6eabde и содержит прежние изменения/данные; не выполнять её автоматическое обновление или очистку.

Z20 выполнен до файловых тестов. Далее выбирать доступные этапы по таблице зависимостей, не ожидая внешнего evidence.

## Матрица

| ID | Область | Технический статус | Evidence / PR | Внешнее evidence |
|---|---|---|---|---|
| Z00 | Исходная точка и сохранность | VERIFIED | Ветка codex/existing-functionality-completion, база e879e6d7; GitHub подтвердил main merge 89eb9224 | — |
| Z01 | Реестр доступных функций | VERIFIED | EXISTING_FUNCTIONALITY_REGISTRY_2026-10-26.md; 16 callbacks; 84 test paths verified | — |
| Z02 | Конечная очередь и текущие документы | VERIFIED | CURRENT_STATE, ROADMAP, CHANGELOG, TEST_MAP, telegram-user-guide; F-01–F-03 finite backlog | — |
| Z03 | Суммы и категории начислений | NOT_STARTED | — | Текущий runtime export может потребоваться |
| Z04 | Себестоимость и внешние расходы | NOT_STARTED | — | — |
| Z05 | Заказы, отмены и возвраты | NOT_STARTED | — | Ограничения источников проверять отдельно |
| Z06 | Финансовые снимки и проекции | NOT_STARTED | — | Текущий runtime export может потребоваться |
| Z07 | Прозрачное 56-дневное evidence | NOT_STARTED | — | Полное владельческое окно не получено |
| Z08 | Multi-SKU, корректировки и поставки | NOT_STARTED | — | Реальная multi-SKU приёмка отдельно |
| Z09 | Однократное включение и версия | NOT_STARTED | — | — |
| Z10 | Числа и текст калькулятора | NOT_STARTED | — | Найдена кодовая несогласованность подписи |
| Z11 | Цели цены/маржи/рекламы | NOT_STARTED | — | — |
| Z12 | Сохранённый план и revisions | NOT_STARTED | — | — |
| Z13 | Batch/mix/readiness/plan-fact/export | NOT_STARTED | — | — |
| Z14 | Навигация и существующие действия | NOT_STARTED | — | — |
| Z15 | Scope, concurrency и budgets | NOT_STARTED | — | — |
| Z16 | Отчёты и доставка | NOT_STARTED | — | — |
| Z17 | Обновление и инструкции | NOT_STARTED | — | Рабочую установку не трогать |
| Z18 | Synthetic backup/restore | NOT_STARTED | — | Пользовательские данные не использовать |
| Z19 | Synthetic lifecycle/update | NOT_STARTED | — | Рабочий процесс не трогать |
| Z20 | Изолированное окружение проверок | NOT_STARTED | — | Выполнить до файловых тестов |
| Z21 | Сквозная приёмка и CI | NOT_STARTED | — | Не заменяет owner acceptance |
| Z22 | PR и независимый review handoff | NOT_STARTED | — | Independent review выполняется отдельно |
| Z23 | Пакет владельца и итог | NOT_STARTED | — | OWNER_EVIDENCE_PENDING |

## Реестр findings

| ID | Класс | Наблюдение | Этап | Статус |
|---|---|---|---|---|
| F-01 | CONFIRMED_DEFECT | Target/price comparison screen безусловно сообщает, что кросс-докинг исключён; solver передаёт его в forward calculation | Z10 | Статически установлено; воспроизвести public flow |
| F-02 | WORKFLOW_GAP | Старые roadmap/current pointers называли #712–#717 открытыми; обновлены current pointers, исторические детали сохранены | Z02 | RESOLVED |
| F-03 | DOCUMENTATION_GAP | Краткое руководство пропускало девять главных menu actions; добавлено описание всех 16 | Z02 | RESOLVED |
| E-01 | OWNER_EVIDENCE_PENDING | Нет текущего JSON работающего обновлённого бота для августовской сверки | Z23 | Не подменять историческим сообщением |
| E-02 | OWNER_EVIDENCE_PENDING | Нет полного владельческого 56-дневного снимка начислений/поставок | Z07, Z23 | Один акт не заменяет окно |
| E-03 | OWNER_EVIDENCE_PENDING | Нет 24–72 часов подтверждённого наблюдения финальной версии | Z23 | Synthetic soak не заменяет |

Новые findings добавлять только с текущим воспроизведением/источником. Не переносить все исторические warnings как новые дефекты.

## Шаблон записи

~~~text
Stage / дата / status:
Branch / base SHA / head SHA / PR:
Что уже было готово:
Подтверждённая проблема и воспроизведение:
Изменение и влияние на contracts:
Проверки: команда / окружение / passed-failed-errors / длительность:
CI: SHA / run URL / Windows / Linux / Docker:
Данные и совместимость:
Ограничения источника / внешнее evidence:
Следующий доступный этап:
~~~

После compaction продолжать по task, последней записи и реальному Git diff. Не считать PREPARED/IMPLEMENTED равным VERIFIED, а VERIFIED — фактической приёмке владельцем.

## Выполнение

### Z00 — безопасная исходная точка

Статус: VERIFIED.
Дата: 26.10.2026.
Рабочая ветка: codex/existing-functionality-completion.
База и merge-base: e879e6d7881a097f040e56d9962223525840917c.
PR: пока не создан.
Проверенный удалённый main: PR #717 сообщает merge SHA 89eb9224c3e9ec2126f58dc4d38794b33c2a2cc0; PR #712–#717 подтверждены через GitHub как merged. Сравнение e879e6d7 → main: main ahead на 6 merge-коммитов, behind 0, изменённых файлов 0. Следовательно, выбранная ветка имеет то же дерево, что текущий main, без переноса пользовательских изменений.
Исходный пользовательский checkout: C:\Users\gelashvilee\Desktop\Ai ассистент, ветка main, HEAD 7e6eabde. Сохранены ранее существовавшие изменения: tracked CHANGELOG.md, data/tasks.json, data/users.json, project_brain/CURRENT_STATE.md, project_brain/ROADMAP.md; существующие untracked документы, временные каталоги, locks и ACL-ограниченные test paths не очищались. В исходный checkout во время Z00 не вносились изменения.
Managed worktree: C:\Users\gelashvilee\.codex\worktrees\daily-readiness-foundation\Ai ассистент; до копирования задания был чистым на e879e6d7. Скопированы только три уже подготовленных файла: task, progress, audit. Исторические и не связанные ветки не изменялись.
Чувствительные данные: содержимое .env, Ozon/Telegram credentials, JSON/SQLite storage и пользовательских backups не открывались и не включались в Git. .env игнорируется Git; data JSON не читались для инвентаризации кроме статуса изменений. Тестовый процесс пока не запускался; изоляцию временного хранилища и synthetic credentials установить в Z20 до файловых тестов. Live Ozon/Telegram запросов не было.
Рабочий бот: не запускался, не останавливался и не обновлялся; его фактический runtime status не проверялся.
Проверки: git status --short --untracked-files=no в исходном checkout показал пять ранее изменённых tracked файлов; git status в чистом worktree до копирования был пустым; git worktree list --porcelain зафиксировал отдельные worktrees; GitHub PR metadata #712–#717 подтверждают merged; GitHub compare e879e6d7 → main: ahead 6 / behind 0 / files 0.
Ошибки команд или блокеры: не осталось. Обычная запись в managed worktree была запрещена песочницей; разрешённое однократное подтверждение доступа использовано только для создания этой ветки и копирования трёх task-docs. Никаких операций с исходными данными не проводилось.
Следующий доступный этап: Z01, затем Z02; после них выполнить Z20 до любых file-based тестов.


### Z01 — реестр доступных функций

Статус: VERIFIED.
Вход: актуальная keyboard, callback/text/command dispatch, Composition Root, руководство пользователя и существующие тесты на e879e6d7.
Результат: добавлен EXISTING_FUNCTIONALITY_REGISTRY_2026-10-26.md. В нём перечислены все 16 действий главного меню, ключевые дочерние пользовательские сценарии, Telegram команды и шесть локальных эксплуатационных entrypoints. Для каждого указаны handler/service, источники/хранилища, доступные проверки и этап дальнейшей приёмки.
Проверка callback routing: каждый из 16 callback главного меню найден в соответствующем command/assistant/onboarding handler; нет кнопки, которую этот реестр объявляет несуществующей или внутренний прототип — публичной.
Подтверждённый новый finding F-03: docs/telegram-user-guide.md описывает только часть главного меню, хотя все 16 кнопок собраны runtime. Справочные callbacks дают более широкие ссылки; руководство неполно как карта пользовательских функций. Исправление направлено в Z02 без изменения runtime.
Проверки: read-only сопоставление AssistantKeyboardService, AssistantButtonHandlerService, AssistantTelegramAdapter, TelegramCommandService, telegram_api_bot, telegram_assistant_factory, docs/telegram-user-guide.md и существующих tests; поиск по callbacks и test files. Тесты не запускались: этап инвентаризационный, код не менялся, изолированная среда перед file tests ещё не настроена (Z20).
Не проверено: реальные API ответы, credentials, данные живого магазина, runtime/Telegram доставка, production process. Эти пункты нельзя закрыть статической картой.
Следующий доступный этап: Z02; затем Z03–Z06, Z20 выполнить до файловых тестов.


### Z02 — конечная очередь и актуальные указатели

Статус: VERIFIED.
Закрытые пакеты сверены по GitHub PR metadata: A–G — #702–#704; H–O — #705–#708; read-only supply/act — #709–#711; X00–X06 — #712; daily readiness/reconciliation — #713–#717. Старые #698–#701 закрыты без отдельного merge, но их reviewed product-workbench stack включён в merged #702; отдельно не переисполнять. Эти пакеты и исторические локальные acceptance ограничения не переносятся как новые unfinished tasks.
Конечный новый backlog: F-01 подтверждённая неверная подпись cross-docking в публичном compare/target result — Z10; F-02 stale current/roadmap references к уже merged PR stack — устранён; F-03 неполное перечисление main menu в docs/telegram-user-guide.md — устранён. E-01–E-03 остаются только owner acceptance pending и не блокируют независимую работу.
Документы обновлены: CURRENT_STATE.md и ROADMAP.md получили актуальный статус/ссылки, исторические тексты оставлены и обозначены историческими; CHANGELOG.md содержит сводку; TEST_MAP.md связывает task/registry/progress и фиксирует отсутствие тестовых изменений; docs/telegram-user-guide.md теперь описывает все 16 действий.
Проверки: GitHub PR metadata #698–#717 прочитана для состояний и зависимостей; точные ветки/merge points зарегистрированы выше. Реестр содержит 84 существующих test files из 84; статически подтверждены все 16 main callbacks. Документированные markdown пути существуют, UTF-8 и пробелы будут повторно валидированы до коммита. Код/данные не менялись. Pytest сознательно не запускался до Z20.
Следующий доступный этап: Z03–Z06 и другие независимые пункты графа; полная приёмка останется в Z21.


### Z20 — воспроизводимая изолированная проверка

Статус: VERIFIED для подготовки и smoke-профиля; финальный полный набор ещё требует exact-head CI в Z21.
Проверка выполнена в чистом detached worktree `existing-functionality-verify`, созданном из commit `ee1df3c2`; worktree с прежними локальными ignored/runtime-файлами не использовался. Для теста создано отдельное окружение `.z20-isolated-env` на Python 3.12.10 с `requirements-dev.txt` (pytest 8.4.2), а также `.z20-storage`, `.z20-temp`, `.z20-userprofile`. `PYTHON_DOTENV_DISABLED=1`; `OZON_CLIENT_ID`, `OZON_API_KEY`, `TELEGRAM_BOT_TOKEN`, `OZON_CREDENTIAL_MASTER_KEY` заданы пустыми; `.env` в проверочной копии отсутствует.
Команда: `python -m pytest -q tests/test_unit_price_target_planning_service.py` из окружения `.z20-isolated-env` — **37 passed in 0.42s**, 0 failed, 0 deselected. На первой попытке стандартное sandbox исполнение не смогло открыть временный файл до старта коллекции; тот же тестовый профиль повторён с разрешённой записью, ограниченной чистой проверочной копией. Это была ошибка прав доступа среды, не pytest regression.
До и после теста сравнивались SHA-256 пяти tracked JSON-файлов в проверочной копии: `history.json`, `profiles.json`, `tasks.json`, `tax_configuration.json`, `users.json`; все значения совпали. Проверочный каталог хранения был направлен в `.z20-storage`; основной пользовательский checkout не открывался для теста и не менялся. Код/приложение/реальный бот/внешние API не запускались.
Следующий доступный этап: Z03; перед каждым новым file-backed профилем сохранять то же отключение dotenv/credentials и явное synthetic storage/temp.

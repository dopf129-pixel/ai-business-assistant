# Журнал: завершение существующих функций бота

Дата подготовки: 26.10.2026.
Статус исполнения: IN_PROGRESS (Z00–Z13 и Z20 VERIFIED; далее Z14).
ТЗ: LUNA_EXISTING_FUNCTIONALITY_COMPLETION_TASK_2026-10-26.md.
Основание: EXISTING_FUNCTIONALITY_COMPLETION_AUDIT_2026-10-26.md.

## Точка продолжения

Z20 проверен: отдельная чистая проверочная копия, synthetic storage/temp/profile и локальный pytest-профиль. Z00–Z13 завершены для заявленного технического объёма; следующий этап — Z14.

Проверенная удалённая база: main после PR #712–#717, merge SHA 89eb9224c3e9ec2126f58dc4d38794b33c2a2cc0. Локальная основная папка осталась на 7e6eabde и содержит прежние изменения/данные; не выполнять её автоматическое обновление или очистку.

Z20 выполнен до файловых тестов. Далее выбирать доступные этапы по таблице зависимостей, не ожидая внешнего evidence.

## Матрица

| ID | Область | Технический статус | Evidence / PR | Внешнее evidence |
|---|---|---|---|---|
| Z00 | Исходная точка и сохранность | VERIFIED | Ветка codex/existing-functionality-completion, база e879e6d7; GitHub подтвердил main merge 89eb9224 | — |
| Z01 | Реестр доступных функций | VERIFIED | EXISTING_FUNCTIONALITY_REGISTRY_2026-10-26.md; 16 callbacks; 84 test paths verified | — |
| Z02 | Конечная очередь и текущие документы | VERIFIED | CURRENT_STATE, ROADMAP, CHANGELOG, TEST_MAP, telegram-user-guide; F-01–F-03 finite backlog | — |
| Z03 | Суммы и категории начислений | VERIFIED | Официальный августовский XLSX сверён локально через offline comparator: 38 864 строк; категории и общий агрегат совпали с исторической сводкой; 62 relevant tests passed | Coverage UNVERIFIED без owner assertion; текущий runtime JSON не получен |
| Z04 | Себестоимость и внешние расходы | VERIFIED | Cost confirmation/timeline/storage, external expense UI/coverage and multi-store stale callbacks: 54 passed | Только synthetic storage; production records/process не использовались |
| Z05 | Заказы, отмены и возвраты | VERIFIED | 103 адресные regressions passed; missing Analytics metrics не восстанавливаются, ClientReturn отделён от Cancellation, несовпадающие когорты не получают долю | API diagnostic подтверждает FBO/FBS структуру; историческая причина события не выводится из текущего статуса |
| Z06 | Финансовые снимки и проекции | VERIFIED | Cached snapshot screen/details/completeness/comparison/bridge/SKU/export profiles: 104 passed; view reads do not query Ozon, explicit refresh creates a new query | Current live snapshot/export remains owner evidence |
| Z07 | Прозрачное 56-дневное evidence | VERIFIED | Синтетический сквозной профиль: 194 passed; signed accrual, отдельная полнота finance/supply и snapshot прошли source → runtime → saved plan → reopen/capture | Полный владельческий 56-дневный снимок всё ещё ожидается |
| Z08 | Multi-SKU, корректировки и поставки | VERIFIED_EXISTING | 64 адресные проверки начислений/акт-данных/поставок passed; duplicate/conflict, signed corrections, SKU mapping, partial receipts and conservative date basis covered | Реальная multi-SKU приёмка отдельно |
| Z09 | Однократное включение и версия | VERIFIED_EXISTING | 238 адресных проверок расчёта, v1/v2, замороженных планов, целей, batch/mix, readiness, plan/fact, сравнения и экспорта passed | Только synthetic data; live source не вызывался |
| Z10 | Числа и текст калькулятора | VERIFIED | Public-flow regressions target/comparison/ad-cap/sensitivity: 48 passed | — |
| Z11 | Цели цены/маржи/рекламы | VERIFIED_EXISTING | Связанный profile: 110 passed; forward, границы, налог, ad-cap и refresh | — |
| Z12 | Сохранённый план и revisions | VERIFIED_EXISTING | SQLite repository + Telegram lifecycle: 44 passed | — |
| Z13 | Batch/mix/readiness/plan-fact/export | VERIFIED_EXISTING | Связанный synthetic profile: 108 passed; three-SKU mix, readiness, compatible comparisons and full exports | — |
| Z14 | Навигация и существующие действия | NOT_STARTED | — | — |
| Z15 | Scope, concurrency и budgets | NOT_STARTED | — | — |
| Z16 | Отчёты и доставка | NOT_STARTED | — | — |
| Z17 | Обновление и инструкции | NOT_STARTED | — | Рабочую установку не трогать |
| Z18 | Synthetic backup/restore | NOT_STARTED | — | Пользовательские данные не использовать |
| Z19 | Synthetic lifecycle/update | NOT_STARTED | — | Рабочий процесс не трогать |
| Z20 | Изолированное окружение проверок | VERIFIED | Чистый verification worktree, Python 3.12.10, isolated venv/storage/temp, dotenv и credentials выключены; baseline 37 passed | Перед file-backed профилями соблюдать Z20 fencing |
| Z21 | Сквозная приёмка и CI | NOT_STARTED | — | Не заменяет owner acceptance |
| Z22 | PR и независимый review handoff | NOT_STARTED | — | Independent review выполняется отдельно |
| Z23 | Пакет владельца и итог | NOT_STARTED | — | OWNER_EVIDENCE_PENDING |

## Реестр findings

| ID | Класс | Наблюдение | Этап | Статус |
|---|---|---|---|---|
| F-01 | CONFIRMED_DEFECT | Target/price comparison screen безусловно сообщает, что кросс-докинг исключён; solver передаёт его в forward calculation | Z10 | RESOLVED; public flow проверен, формулы не менялись |
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
Следующий доступный этап после исходной изоляции: Z03; перед каждым новым file-backed профилем сохранять то же отключение dotenv/credentials и явное synthetic storage/temp.

### Z03 — суммы и классификация начислений

Статус: VERIFIED для исторического периода 2026-08-01—2026-08-31; код и финансовая формула не менялись. Приложенный официальный файл прочитан только для анализа. Существующий `daily_use_reconcile.py reference` в clean verification worktree обработал 38 864 строки с валидной датой в диапазоне; invalid dates 0. Coverage осталось `UNVERIFIED`, поскольку в offline comparator не передавалось явное подтверждение полноты периода. Файл не копировался в репозиторий/хранилище; денежные суммы и значения ячеек не записывались в Git.
Типы XLSX сверены по знаку, категории и итогу: комиссия продажи/возврата, размещение, эквайринг, кросс-докинг, CPC/CPO, основная логистика и доставка до места выдачи. Категории и их нетто-сумма совпадают с предоставленной исторической сводкой; доставка до места выдачи является подкатегорией общей логистики и не учитывается повторно. Детальные типы не меняют net total.
Комиссия полного месяца берётся из месячного отчёта реализации; код и тесты показывают число строк отчёта отдельно и явно предупреждают, что это не число продаж/единиц. Адресный regression-профиль в изолированном clean worktree: `tests/test_experimental_store_economics.py`, factory, accrual breakdown, period summary и postings client — **62 passed in 4.12s**, 0 failed/deselected.
Ошибки: sandbox-only tempfile failure при первой попытке Z20 был повторён с разрешённой записью внутри изолированного worktree; financial profile ошибок не дал. Подтверждённых ошибок разнесения в проверенных категориях не осталось; текущий runtime export/полнота его данных не проверены.
Следующий этап: Z04 — себестоимость и внешние расходы.

### Z04 — себестоимость и внешние расходы

Статус: VERIFIED в synthetic сценариях; бизнес-политика аллокации не менялась. Cost confirmation flow проверяет предложение effective date, отдельное подтверждение применения ко всей истории, старые кнопки после нового draft/смены товара и магазина, повтор callback, отмену и запись ровно один раз. Effective-cost timeline fail-closed до/после подтверждённого интервала и не переносит новую текущую стоимость на прошлые даты. Storage regression проверен отдельно: `app/tests/test_tenant_seller_cost_switch_storage.py` — 1 passed.
Внешние расходы прошли preview → confirm → explicit coverage → возврат к прибыли → explicit refresh и multi-store callback scope. Описание от пользователя доходит до preview; повторная/конкурентная отправка, старый view callback и uncertain write не дублируют запись. Неполное покрытие имеет явные gaps и не превращается в нулевой расход. Текущие правила подтверждения покрытия и учёта наблюдаемой прибыли сохранены без изменения.
Общий адресный профиль: cost confirmation flow, effective timeline, confirmation runtime, coverage, historical-cost input и Telegram expenses — **53 passed in 1.49s**; отдельный storage reopen profile — **1 passed in 0.21s**. Итого **54 passed**, 0 failed/deselected. Git tracked data в verification worktree не изменились; код не менялся.
Не выполнялись реальные Telegram/API обращения или перезапуск реального бота. Следующий этап: Z05.

### Z05 — заказанные, отменённые и возвращённые единицы

Статус: VERIFIED по источникам и имеющимся runtime/test контрактам; код не менялся. В Analytics запрошенные метрики индексируются по собственным именам, отсутствующие `cancellations`/`returns` остаются отсутствующими; нельзя брать значение соседнего индекса. При неполной пагинации заказанное количество не выдаётся как полное.
Проверены FBO/FBS вызовы, `product.quantity`, лимиты/страницы, дедупликация ID и conflicting duplicates. Предоставленный обезличенный API diagnostic показал 272 уникальные FBO записи: 270 `Cancellation` и 2 `ClientReturn`; FBS вернул 0. Это диагностическая выборка, не доказательство полноты всей истории. `Cancellation` не попадает в клиентские возвраты. Денежный возврат выручки, факт складского восстановления и запись типа `ClientReturn` остаются разными понятиями; восстановление товара этим источником не доказано.
Fallback отмен Seller API фильтрует отправления по окну даты создания и текущему статусу `cancelled`; он не является когортой исторических отмен. Поэтому знаменатель/процент отмен не показывается. Возвраты `ClientReturn` фильтруются по изменению статуса в периоде, но источник и заказанная база не имеют подтверждённой одинаковой когорты; их доля также скрыта. Текущий status не описывается как точная дата события отмены.
Адресный regression-профиль experimental economics, Analytics runtime, return evidence response/timestamp/service, quantity authority/diagnostics, Seller API attempts и FBO-v3 economics — **103 passed in 2.71s**, 0 failed/deselected. Реальный API повторно не вызывался; применены ранее полученные обезличенные API summaries. Не найдено подтверждённого дефекта для исправления.
Следующий этап: Z06 — проверить совместимость финансового снимка и его проекций.

### Z06 — единый финансовый снимок и его проекции

Статус: VERIFIED на уровне существующих runtime/test контрактов; код не менялся. Один scoped report view сохраняет immutable analytics snapshot, основные и detail/completeness/diagnostics/comparison/bridge/SKU экраны читают его из tenant-scoped TTL cache. Просмотр и JSON/CSV export используют cached snapshot и не запускают повторный Ozon read; явная кнопка refresh запускает query для тех же дат и строит новую view/snapshot.
В snapshot отображаются scope, current/previous periods, generation time, comparison basis/status, units/status каждого показателя, completeness/reasons, bridge и SKU contribution с необъяснённым остатком. Несовместимая прибыль не объявляется comparable, отсутствующие значения не становятся нулём, расходы не распределяются по SKU без доказательной базы. Experimental report остаётся отдельным и не переносится в основной расчёт.
Адресный regression-профиль по serializer/service/runtime exports, completeness, comparison contracts/metrics/bridge, SKU contribution, period query и support diagnostics — **104 passed in 3.18s**, 0 failed/deselected; повторный профиль runtime/export после исправления `PYTHONPATH=app` — все тесты прошли. Первый запуск не собрал тесты из-за отсутствующего пути импорта; дефектом приложения это не являлось. Не найдено подтверждённой рассогласованности; live API и внешний JSON не использовались.
Следующий этап: Z07 — проверить путь 56-дневного cross-docking evidence до пользовательского результата.

### Z07 — проверяемое 56-дневное cross-docking evidence

Статус: VERIFIED в synthetic источнике и пользовательских путях; реальный полный 56-дневный снимок остаётся owner evidence (E-02). Источник публикует один снимок только после завершения финансового и поставочного окон; даты, timezone Europe/Moscow, метод, SKU/store знаменатель, signed начисления с корректировками и покрытие выводятся вместе. `as_of` фиксируется при завершении сбора и не обновляется на cache hit. При неполном сборе показываются отдельные признаки завершённости финансов и поставок, без числовой ставки.

Signed общая сумма берётся из финансового evidence; SKU-сумма выводится со знаком из уже неттированных SKU расходов, поэтому корректировки учитываются один раз. Telegram экран допущений показывает signed начисления, поставочный статус и timestamp снимка; сохранённый owner plan сохраняет эти сведения при записи, повторном открытии и повторном захвате. Optional additive поля не меняют обязательную схему прежних v2 документов; идентификаторы/сырые ответы не добавляются.

Профиль в чистом `existing-functionality-verify` с отключёнными credentials/dotenv и отдельными storage/temp: cross-docking finance/rate/evidence/supply, текущая unit economics source/runtime, adapter, target planning, saved-plan flow и analytics export — **194 passed in 4.15s**, 0 failed/deselected; `git diff --check` чистый. Перед этим профиль выявил реальную несовместимость: строгий allowlist отклонял новые поля saved-plan payload (23 ошибки в первой расширенной попытке). Схема расширена с optional полями, существующая v2-схема осталась допустимой; после исправления сохранённый сценарий подтвердил reopen/recapture новых данных. Код в пользовательский checkout и production не запускался.

Следующий этап: Z08 — проверить multi-SKU, signed корректировки и консервативный знаменатель поставок на пограничных/конфликтных synthetic случаях.

### Z08 — multi-SKU, корректировки и частичные поставки

Статус: VERIFIED_EXISTING для поддерживаемой и fail-closed семантики; код не менялся. Финансовые начисления объединяют повтор exact row только один раз, конфликтующий ID/строка не публикует сумму; положительные signed корректировки вычитаются из накопленного расхода. SKU-attributed начисления дают индивидуальную SKU-ставку, а unattributed сумма переходит в явно помеченную store estimate с общим знаменателем. Заказы/акты дедуплицируются, конфликтные копии блокируют totals; фактический `fact_quantity` сверяется с принятым summary и не подменяется `declared` или `approved`. Отмена direct FBO исключена; unknown crossdock flag, неполная страница/деталь, неидентифицированный товар, несогласованный акт, multi-SKU акт и неоднозначная дата нескольких вложенных поставок fail-closed.

Устаревшая `arrival_date` и `created_date` акта не используются как дата приёмки. Сохраняется текущая консервативная дата завершённого parent order с одной подходящей nested supply; несколько вложенных поставок с общей родительской датой в окне не распределяются произвольно. Финансовые corrections берутся по дате начисления и не меняют supply denominator. Реальная проверка отдельной многотоварной/разделённой поставки владельцем остаётся полезным evidence, но не блокирует synthetic техническую приёмку.

Профиль в изолированной verification-копии: `tests/test_cross_docking_financial_evidence_service.py`, `tests/test_cross_docking_supply_evidence_service.py`, `tests/test_cross_docking_supply_source.py`, `tests/test_cross_docking_unit_rate_source.py` — **64 passed in 1.15s**, 0 failed/deselected; реальный API не вызывался. Existing fixtures cover SKU A/B, same-SKU line aggregation, unknown/multi-SKU acts, partial received quantities, duplicated/conflicting accrual and supply records, positive corrections/net refunds, no relevant supplies, and completed/incomplete window boundaries.

Следующий этап: Z09 — проверить единичное включение ставки и замороженное evidence по путям калькулятора и сохранённого плана.

### Z09 — однократное включение и сохранённая версия

Статус: VERIFIED_EXISTING для существующих формул и путей. Кросс-докинг вычитается один раз в single/current unit economics и target/ad-cap forward result; налоговая база USN income остаётся прежней, а USN income-minus-expenses учитывает расход по действующей политике. В batch/mix ставка умножается на указанный успешный Q; для отсутствующего подтверждённого источника положительный Q делает mix итог неполным, а не нулевым. Плановая сторона использует замороженную ставку/evidence; plan/fact не переносит её на фактическую прибыль.

Сохранённый v1 сохраняет старую формулу без автоматического cross-docking deduction. v2 сохраняет evidence, открытие использует snapshot без Ozon read; отдельное explicit refresh создаёт новую revision и сохраняет старую. Полное окно без units и неполная выборка различаются; отсутствие ставки не переименовывается в нулевой тариф. Export/comparison/readiness используют frozen evidence и видимые scope/period.

Изолированный linked profile в verification worktree: current/product economics, scenario source/service/runtime, target planning, ad cap, batch planning/runtime, sales mix, readiness, plan/fact comparison, saved-plan lifecycle, plan comparison, analytics export/service serializer — **238 passed in 5.52s**, 0 failed/deselected; `git diff --check` чистый. Подтверждённого нарушения однократности или версии не обнаружено, код не менялся, Ozon/Telegram live requests не выполнялись.

Результат Z10 и фактическая проверка зафиксированы далее.

### Z10 — числовая и текстовая согласованность калькулятора

Статус: VERIFIED. Через публичные Telegram runtime flows подтверждено, что начальный результат и экран допущений показывают кросс-докинг по ставке SKU, а целевой расчёт, сравнение нескольких цен, рекламный лимит и sensitivity используют и раскрывают тот же компонент. Устранено безусловное старое предупреждение, утверждавшее, что кросс-докинг исключён, хотя solver включал его в forward calculation.

Добавлены conservative подписи для отсутствующей/неподтверждённой ставки, неодинакового статуса forward-вариантов и сохранённого legacy v1 плана без этого поля. Публичные регрессии подтверждают соответствие сообщения фактическому `forward_result`; сумма, налоговая база и прибыльные формулы не менялись. Saved plan view продолжает показывать замороженное evidence существующим контрактом.

Изолированный профиль `tests/test_unit_price_scenario_telegram_runtime.py tests/test_telegram_unit_price_sensitivity_runtime_service.py`: **48 passed in 1.31s**, 0 failed/deselected. Первый прогон выявил устаревший callback в новом тестовом сценарии после смены версии; тест разделён на независимые актуальные сессии, повторный прогон прошёл. Реальный API, бот и пользовательские данные не использовались.

Результат Z11 и фактическая проверка зафиксированы далее.

### Z11 — целевая маржа, цены и допустимая реклама

Статус: VERIFIED_EXISTING; подтверждённой ошибки или причины менять политику не найдено. Target/break-even используют существующий forward calculator, завершают поиск независимой прямой проверкой и не меняют цену продавца в источнике. Цена проверяется в копейках; target parser отвергает неоднозначные/неконечные/вне диапазона значения; сравнение сохраняет порядок введённых цен и весь перебор ограничен фиксированным бюджетом.

Рекламный предел работает по сетке 0,01 процентного пункта; предельная точка и следующий шаг проверяются повторным прямым расчётом. Недостижимая цель, верхняя граница, неполный вход и немонотонная forward-функция имеют разные fail-closed результаты. Проверены NONE, USN income, income-minus-expenses и переключение минимального налога. Кросс-докинг не меняется в сценариях цены; обновление источника сохраняет ручные допущения лишь для той же identity. FBS/будущий тариф и будущие скидки не объявляются известными.

Связанный изолированный profile: target planning, advertising cap, forward scenario service, налоговые сценарии, Telegram calculator public flows и sensitivity — **110 passed in 2.31s**, 0 failed/deselected. Тесты временно не использовали dotenv, credentials или внешние API; файлы данных остались в synthetic storage.

Результат Z12 и фактическая проверка зафиксированы далее.

### Z12 — жизненный цикл сохранённого плана

Статус: VERIFIED_EXISTING; подтверждённых дефектов не обнаружено. Публичный путь create → list/open → локальное продолжение → preview → save revision/copy → reopen сохраняет идентичность, assumptions, версию модели и frozen snapshot; открытие и продолжение не делают source/Ozon refresh. Старые схемы продолжают читаться без автоматического пересчёта или миграции чисел.

Репозиторный слой проверен на owner/store isolation, revision history, idempotency, stale revision/state conflict, параллельный compare-and-swap (один победитель), legacy schema reopen, неизвестные/некорректные схемы и атомарное открытие нескольких подключений. Telegram flow покрывает устаревший save callback, два открытых состояния/версии, update preview и подтверждение, explicit copy/archive/restore/delete, повторный запуск runtime, changed product/offer/SKU/store identity и неизменность исходной revision.

Изолированный profile `tests/test_planning_workspace_repository.py tests/test_saved_planning_plan_telegram_flow.py`: **44 passed in 1.89s**, 0 failed/deselected. Тестовые SQLite-файлы размещались в pytest temporary area; real storage, Ozon, Telegram и бот-процесс не использовались. Код не менялся.

Результат Z13 и фактическая проверка зафиксированы далее.

### Z13 — batch, mix, готовность, сравнения и экспорт

Статус: VERIFIED_EXISTING; подтверждённой ошибки не найдено. Одиночные и пакетные планы связываются через точную identity товара; пакет ограничен заданным числом SKU, сохраняет строки/порядок и позволяет редактировать строку локально. Для sales mix проверен трёх-SKU случай с отдельными cost/commission/ads, явным нулём и отсутствующей себестоимостью; округлённые unit components агрегируются, налог вызывается один раз на общий mix. Missing Q и неподтверждённый cross-docking не превращаются в нулевой расход, а неполное покрытие фиксированных расходов не выдается за полный итог.

Readiness указывает конкретный недостающий ввод и отделяет качество математики от свежести источника/фактического статуса. Plan/fact требует одинаковый период, tenant/store и exact SKU; неизвестное количество и несовместимые expense/Return COGS scopes не производят ложное сравнение прибыли. Сравнение сохранённых планов не делает внешний запрос и не пересчитывает неподдерживаемую историческую модель. JSON/CSV экспортируют все строки/ячейки и model/assumption/completeness metadata, а не только видимую страницу; `null`, ноль, unknown, текстовая безопасность и лимит документа различаются.

Изолированный связанный profile batch service/runtime, sales mix, readiness, plan/fact, plan comparison, export serializers/services/runtime и saved plan integration — **108 passed in 3.58s**, 0 failed/deselected. Внешние источники не вызывались для исторического чтения/сравнения; код не менялся.

Следующий этап: Z14 — пройти все существующие пользовательские действия и их возвратные переходы.

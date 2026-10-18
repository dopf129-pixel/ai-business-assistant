# Архитектурный review A–G, 18.10.2026

Решение первоначального review: **пакет требовал исправлений перед слиянием**. Тогда были подтверждены восемь проблем: одна P1 и семь P2; исправления не входили в проверенный head. Последующее выполнение R1–R8 отражено в заключении ниже. Этот файл не является approval для слияния.

## Объём и исходные версии

Проверена цепочка PR #698–#703 относительно исходной зависимости #697. Локальный head: `e0ffeaabf939c52507bfe0de58bc74524ace6c0c`.

| PR | Проверенный head | Verify |
|---|---|---|
| #698 | `127914d1d6efbb579b07d896157d7b6f9fcd3f97` | `39062235998` success |
| #699 | `292c4cb83d4499045ae200862c2b3132905e409e` | `39064066060` success |
| #700 | `1e19493e1671db4f46f3d8530c0d5d46143fc9ce` | `39065255165` success |
| #701 | `f598d300164916434de27a5180bb033d8a9f4293` | `39066774774` success |
| #702 | `55db3e60fda3c3080051da2fbea1902091a4bfff` | `39069168434` success |
| #703 | `e0ffeaabf939c52507bfe0de58bc74524ace6c0c` | `39069728139` success |

Все перечисленные PR открыты и не слиты. Зелёный CI подтверждён для указанных SHA; воспроизведения ниже выявляют дополнительные сценарии, которых существующий suite не проверяет.

## R1 — P1: Telegram удаляет одиночный сценарий перед открытием чувствительности

Модуль D, PR #700. Новый dispatch: `app/services/assistant_button_handler_service.py:772–774`. Существующий navigation guard: `app/telegram_app_layer/assistant_telegram_adapter.py:354–357`; он наследуется production `ReturnInventoryTelegramAdapter`.

Кнопка одиночного калькулятора передаёт `ups:s:<scenario_id>:<version>`. До входа в новый handler адаптер вызывает очистку одиночного калькулятора для любого callback, кроме `upc:*`. Поэтому источник уже удалён, когда `begin_from_single` пытается прочитать его. Действие всегда возвращает `UNIT_PRICE_SENSITIVITY_ACTION_STALE`; пользователь также теряет открытый сценарий. Прямые тесты `AssistantButtonHandlerService` обходят эту границу и поэтому проходят.

Фактическое воспроизведение через production-класс адаптера с настоящими single/sensitivity runtimes:

- до нажатия активный сценарий существует;
- после нажатия статус `UNIT_PRICE_SENSITIVITY_ACTION_STALE`;
- активный сценарий отсутствует; дополнительных source calls нет.

Исправление: согласовать navigation/lifecycle политику адаптеров с переходами `ups:*`, сохраняя исходный single scenario для просмотра, возврата и переноса ячейки. Регрессия должна пройти через `ReturnInventoryTelegramAdapter`, а не только через внутренний handler.

## R2 — P2: завершившийся refresh восстанавливает отменённый batch и затирает более новую правку

Модуль C, PR #699. `app/services/telegram_unit_price_batch_plan_runtime_service.py:352–357` и `_save_batch` около строки 673.

Refresh читает копию batch, выполняет запросы, затем без проверки generation/current batch/version сохраняет результат. `clear_pending` и новая правка не могут отозвать этот worker. Это проявляется при параллельной обработке runtime, которая входит в требования A/G.

Два воспроизведения с блокирующим fake refresh и Event:

1. Запустить refresh, выполнить публичный `upb:c`, затем завершить refresh. Сначала возвращается `UNIT_PRICE_BATCH_CANCELLED`, затем старый worker возвращает `UNIT_PRICE_BATCH_PLAN_READY` и восстанавливает `_batches`.
2. Запустить refresh V1, изменить себестоимость на 250 и получить V2, затем завершить refresh V1. Поздний результат тоже имеет V2, но себестоимость снова 100. Кнопки V2 не отличают перезаписанное состояние.

Исправление: generation/ticket для source refresh и атомарная условная публикация, проверяющая текущий batch id/version/ticket. Cancel, новый запуск и правка должны отзывать старый worker. Добавить обе регрессии и проверку переключения магазина во время HTTP.

## R3 — P2: команды сброса и смены магазина не очищают новые runtime

Модули C/D, PR #699/#700. `app/services/assistant_button_handler_service.py:579–583`; вызовы hook находятся в `TelegramCommandService` и адаптерах.

Hook `clear_unit_price_calculator_state` очищает только одиночный калькулятор. Новые batch/sensitivity состояния и связанные кнопки не инвалидируются через `/start`, `/ozon_connect`, `/ozon_disconnect`, `/stores` и `ozon_store:*`. Обычная очистка внутри `handler.handle` не помогает: команды обрабатываются раньше него.

Последовательные воспроизведения, не требующие конкурентной обработки:

- начать ввод целевой маржи batch → выполнить `/start` → отправить `20`: вместо нового состояния запускается старый batch и возвращается `UNIT_PRICE_BATCH_PLAN_READY`;
- начать ввод в магазине A → через настоящую command-service границу выбрать B и затем A → отправить `20`: старый pending снова принимается.

Исправление: общий явный reset для всех новых transient состояний/поколений при командах и смене аккаунта. Согласовать его с R1, чтобы внутренние переходы не уничтожали собственный источник. Проверить `/start`, A→B→A, disconnect/reconnect и незавершённые HTTP workers.

## R4 — P2: обзор не устанавливает лимит 120 секунд / 128 попыток

Модуль B, PR #698. `app/services/product_overview_service.py:193–197`; аналогичный запуск есть в `create_snapshot`.

Обзор напрямую вызывает decision query без собственного bounded operation trace. В production callback он наследует только общий Telegram trace с defaults 600 секунд / 300 попыток. По ТЗ для обзора требуется 120 секунд / 128 фактических попыток; меньший parent должен дополнительно ограничивать операцию. Ограничение до 20 строк не ограничивает количество запросов внутри каждой строки.

Воспроизведение: публичный `AssistantButtonHandlerService.handle('product_overview')`, настоящий overview/query и источник с 20 строками по восемь зарезервированных HTTP-попыток. Запрос успешно завершает все 20 строк: **160 попыток, cap 300**, вместо остановки на 128.

Исправление: создать и активировать дочерний trace на каждом live запуске обзора/refresh/следующей группы с cap 120/128 и текущим parent; сохранить обработку остаточных строк как BUDGET_EXHAUSTED. Проверить границы HTTP и времени через публичный маршрут.

## R5 — P2: Telegram batch не передаёт текущий parent budget

Модуль C, PR #699. `app/services/telegram_unit_price_batch_plan_runtime_service.py:186–190` и `353`.

Сам batch service поддерживает `parent_trace`, но runtime вызывает `build` и `refresh` без него. В результате создаётся независимый budget 120/128, а source активирует его вместо текущего Telegram trace. Меньший общий лимит и его cancellation не достигают партии; внешний счётчик также не отражает эти HTTP-попытки.

Воспроизведение: активный parent имеет cap 1; настоящий batch service через Telegram runtime загружает два SKU. Получено **2 source HTTP reservations**, при этом parent остаётся **0/1**. Это проверка реальных budget объектов и runtime, fake source выполняет только reservation вместо сети.

Исправление: передавать `current_period_profit_trace()` во все source build/refresh entrypoints. Регрессии: меньший HTTP cap, меньший deadline, уже отменённый parent и parent cancellation во время источника.

## R6 — P2: число sensitivity snapshots не ограничено объявленными 64

Модуль D, PR #700. `app/services/telegram_unit_price_sensitivity_runtime_service.py:452–454`.

`MAX_SESSIONS=64` применяется только к `_pending`. `_store_session` добавляет результаты в обычный `_sessions` dict без вытеснения, а истёкший результат в `_render` возвращает stale без удаления. Завершённые пользователем сессии остаются в памяти после ухода пользователя; каждая может хранить 49 полных сценариев.

Воспроизведение через публичные методы: 65 разных owner/store scopes последовательно строят готовые sweeps. Итог: **sessions=65**, declared limit=64, pending=0. Никаких production/network источников не использовалось.

Исправление: bounded LRU/TTL cache для `_sessions` с атомарным чтением/вытеснением и очисткой зависимых actions. Проверить 64/65 сессий, TTL, eviction во время чтения и безопасный stale ответ после вытеснения.

## R7 — P2: выгрузка теряет уже показанную отметку устаревшего источника

Модуль E, PR #701. `app/services/telegram_unit_price_batch_plan_runtime_service.py:274–279`; `_render` вычисляет staleness в отдельной копии.

Экран учитывает текущий возраст source и показывает `SOURCE_STALE`. Export передаёт первоначальный batch, поэтому файл сохраняет `READY`/FOUND и не содержит age-at-export, срока свежести или явной отметки, что готовность относится к историческому снимку. `exported_at_utc` при этом новый. Один и тот же пользовательский результат получает противоречащие статусы на экране и в файле.

Воспроизведение: source из кэша имеет возраст 590 секунд, через 20 секунд открыть текущий план и JSON. Экран сообщает «снимок устарел»; JSON по тем же строкам содержит `INCOMPLETE_INPUTS` и `READY`, а metadata не имеет freshness/age полей.

Исправление: общий безопасный export/view projection, сохраняющий исходные значения, но явно передающий текущую staleness и время/возраст оценки. Проверить cached source near TTL → screen stale → CSV/JSON с тем же ограничением. Аналогично проверить sensitivity historical export.

## R8 — P2: устранённый пробел ввода остаётся в READY строке

Модуль C, PR #699. `app/services/unit_price_batch_plan_service.py:485–520`.

При неполном результате `_recalculate_row` устанавливает `missing_inputs`/`invalid_inputs`. После успешной правки и нахождения цели он меняет status/reason, но не очищает прежние списки. Экран и выгрузка продолжают требовать уже введённое значение.

Воспроизведение настоящими batch/scenario/target services: первый SKU без cost → локально задать cost=200 → строка **READY**, но **missing_inputs=['cost']**. Сумма сценария рассчитана, однако сообщение «Нужно указать» и exported completeness не соответствуют текущим inputs.

Исправление: на каждом пересчёте синхронизировать missing/invalid списки с актуальным scenario до выбора итогового status. Проверить INCOMPLETE→READY, несколько пробелов с поочерёдным заполнением и исправление invalid source assumption.

## Выполненные проверки и границы review

- Просмотрены изменения A–G, production factory/Telegram adapter/command цепочка, operation budgets и bounded snapshots, scenario/target/sensitivity runtime, serializers/exports и support diagnostics.
- Все восемь замечаний подтверждены изолированными исполняемыми probes с реальными сервисами и fake source/transport; ни live Ozon, ни пользовательские credentials не использовались.
- Отдельно воспроизведены обе ошибки refresh (отмена и потеря новой себестоимости), `/start` и A→B→A для reset hook.
- Проверены актуальные PR SHA и зелёные Verify runs. Полный pytest повторно не запускался: production code и tests не менялись, а review проверял дополнительные конкретные сценарии. Для исправлений нужны новые регрессии и полный CI на новых heads.
- На момент первоначального review пользовательские tracked изменения `data/tasks.json` и `data/users.json` оставались вне review-кода; реализация не изменялась и Git mutations не выполнялись.

## Следующий шаг на момент первоначального review

Исправить R1–R8 небольшими изменениями в соответствующих ветках с учётом stacked зависимостей. Для R1/R3 определить общую navigation/reset политику, для R2 — атомарную публикацию source результата. После этого запустить новые регрессии, получить зелёные проверки актуальных PR heads и пройти повторный review. Слияние и deploy в рамках этого review не выполняются.

## Последующее выполнение исправлений (2026-10-18)

- R1–R8 реализованы на рабочей ветке PR #703: переходы `ups:*` сохранены адаптером; reset очищает transient-состояния single/batch/sensitivity/overview; refresh batch защищён ticket, batch identity/version, active tenant и TTL; overview использует дочерний trace 120s/128 attempts; batch build/refresh наследует текущий parent trace; sensitivity sessions ограничены LRU/TTL с атомарным read и удалением зависимых actions; экран и экспорт используют общий freshness projection; пересчёт строки заново формирует missing/invalid input lists.
- Добавлены регрессии на production adapter/command seams, конкурентную отмену/правку, меньшие parent budgets, stale export, LRU/TTL и incomplete→ready.
- Локально: связанный профиль **86 passed**, `compileall -q app tests` прошёл, `git diff --check` прошёл. Эти результаты подтверждают новые сценарии, но не заменяют полный CI.
- Локальный полный pytest ограничен Windows ACL на временные каталоги; точные результаты и CI приведены ниже. Повторный review выполнен на code SHA `664a370a117251a88297e57668a8ba721a80555c`; слияние и deployment не выполнялись.

## Результат повторного review

- Для каждого R1–R8 проверены соответствующие изменения и регрессия. Не обнаружено оставшихся случаев потери калькуляторного контекста, публикации позднего refresh, протекания transient state между магазинами, обхода operation budget, неограниченного sensitivity cache, расхождения свежести экрана/выгрузки или неактуальных input warnings.
- Целевой профиль: **86 passed**; `compileall -q app tests` и `git diff --check` прошли.
- На code SHA `664a370a117251a88297e57668a8ba721a80555c` успешны Windows и full-verification jobs в runs `39161924581` и `39161920417`.
- Полный локальный Windows pytest: **3 030 passed, 21 failed, 369 errors**; известный ACL `PermissionError [WinError 5]` блокирует временные каталоги. Повторный запуск с локальным `--basetemp` тоже не смог выполнить pytest cleanup. CI на code SHA прошёл полностью.
- Повторный review: **исправления приняты для передачи на следующий этап**, дополнительных блокирующих замечаний нет. PR #703 остаётся неслитым; deploy не выполнялся.

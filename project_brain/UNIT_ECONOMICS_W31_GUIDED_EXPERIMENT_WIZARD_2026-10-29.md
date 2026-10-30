# W31 — мастер ценового эксперимента в Telegram

Дата исходного этапа: 29.10.2026
Ветка: codex/full-unit-economics-experiments-implementation-20261028
Входной code HEAD: fd2aee75
Стадия исходного этапа: условный flow. Инженерные блокеры первого сбора и candidate lifecycle закрыты в W40; см. addendum в конце этого документа и `UNIT_ECONOMICS_W40_REVIEW_REMEDIATION_2026-10-30.md`.

## Что добавлено

- В базовом меню юнит-экономики появилась кнопка «Эксперименты цен».
- Мастер выбирает только активные сохранённые FBO-планы текущего owner/store и фиксирует точный document revision и SKU identity.
- Для продолжения требуется точный завершённый 56-дневный снимок с тем же SKU, часовым поясом, полным покрытием и итоговым статусом COMPLETE. Несовпадающий, неполный или неизвестный снимок не подходит.
- Пользователь вводит 2–10 уникальных цен простым списком через ;, затем подтверждает фактическую цену продавца и локальное время её установки. JSON/API-ответ не требуется.
- Эксперимент проходит repository draft → baseline phase → READY → отдельный owner confirmation. Плановая baseline-фаза начинается со следующего полного локального дня на 7 дней.
- Все шесть контрольных условий начинаются как UNKNOWN; это не утверждение о неизменности условий.
- Отмена до подтверждения переводит незапущенный эксперимент в CANCELLED, снимает confirm callback и сохраняет запись в истории.
- Callback и pending state ограничены TTL/quota, привязаны к owner/store. Смена магазина удаляет прежние transient selections; revisions проверяются заново перед созданием.
- Цена и её effective time описываются как подтверждение владельца, не как история цены Ozon. Мастер не меняет данные Ozon и не выполняет запросы API.

## Ограничение, блокирующее полный W31

В приложении нет Telegram/runtime caller для create_unit_economics_expense_snapshot. Проверка вызовов показывает, что источник 56-дневного снимка ещё не подключён: W09 добавил нормализатор/агрегатор, но оставил provider-specific adapters pending. Поэтому обычный первый запуск в Telegram остановится с понятным сообщением REFERENCE_SNAPSHOT_REQUIRED; это намеренная fail-closed защита, а не работающий путь подготовки снимка.

Перед включением полноценного пользовательского эксперимента нужно подключить и подтвердить источники для завершённого 56-дневного окна, знаменателя единиц и включённых расходов на SKU, сохраняя UNKNOWN как UNKNOWN. Нельзя маркировать неполный снимок как COMPLETE или запускать READY/active phase поверх неизвестных расходов.

Пока этот блокер открыт, тесты доказывают условный Telegram lifecycle на полностью подготовленных синтетических данных; они не доказывают, что пользователь сможет получить такой snapshot из production UI. Следующий этап W32 может независимо покрыть чтение уже сохранённых experiment records.

## Проверки

Изолированный профиль, Python 3.14 Windows, отдельный временный data root, dotenv и сторонняя pytest plugin autoload выключены:

- pytest -q tests/test_telegram_unit_economics_experiment_runtime.py tests/test_product_unit_economics_telegram_ui.py tests/test_unit_price_scenario_telegram_runtime.py tests/test_telegram_unit_price_observation_runtime.py tests/test_planning_workspace_unit_economics.py
- 96 passed in 3.72s.
- py_compile нового runtime, handler, keyboard и factory: PASS.
- git diff --check: PASS.
- git diff -- data: пустой.
- Реальные Ozon API и бот не запускались; пользовательская БД и данные не читались.

Проверено: positive flow от сохранённого плана и complete snapshot до BASELINE_ACTIVE; точные цены в копейках; staged user input; отказ от дубликатов/невалидных цен; блокировка при отсутствии полного снимка; смена магазина инвалидирует selection; отмена инвалидирует confirmation callback и сохраняет статус CANCELLED; публичный callback/text dispatch; кнопка в меню; callback в лимите 64 байта.

## Архитектурное влияние

Minor architectural extension: новый tenant-scoped Telegram runtime использует существующие PlanningWorkspaceRepository, callback router, tenant context и transient-state limits. Схема базы, расчётная математика, Ozon clients и существующий observation collector не менялись. Новый продуктовый слой источника 56-дневных данных не создавался и остаётся незакрытой зависимостью.

## Addendum — remediation R4/R5 (30.10.2026)

Статус выше описывает состояние 29.10.2026. В W40 review-remediation добавлено подключение `UnitEconomicsReferenceSnapshotCollectionService` к существующему read-only finance + FBO denominator collector; в Telegram мастер получил кнопку первого сбора. Сохраняется только полный exact 56-day snapshot. Неполный Returns, unsupported finance types, нулевой знаменатель и net-credit категории дают PARTIAL/review reason без записи COMPLETE.

Также теперь доступен owner path candidate-phase и операции по обеим фазам: collect, evaluate maturity, update control flags, finish; для завершённого candidate — compare и owner decision. Сквозной synthetic Telegram test проверяет обе фазы от baseline activation до решения. W40 linked profile: 127 passed in 6.60s; full pytest: 4,346 passed in 42.30s. Реальные API/бот/магазин не использовались. Новый exact-head CI и повторное независимое review остаются pending.

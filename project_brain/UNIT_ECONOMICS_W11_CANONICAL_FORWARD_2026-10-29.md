# W11 — единый расширенный расчёт экономики SKU

Дата: 29.10.2026.
ТЗ: `LUNA_FULL_UNIT_ECONOMICS_AND_PRICE_EXPERIMENTS_TASK_2026-10-28.md`.
Статус: завершён; этапы W12–W39 остаются открыты.

## Изменение

`UnitPriceScenarioService` получил необязательный версионированный `extended_scenario`. Если его нет, существующий forward-расчёт сохраняет старый контракт и результат. При наличии полного поддержанного сценария `WINDOW_COST_ALLOCATION` подтверждённые дополнительные расходы суммируются, распределяются на заявленное совместимое количество и вычитаются из прибыли до вызова существующего `TaxService`. Сумма/единица округляется один раз через действующее правило денег; налог вызывается один раз на canonical путь.

`calculate_components_only` и `compare` принимают тот же сценарий и используют тот же расчёт. Scenario comparison не запускает дополнительный источник или отдельную формулу. Extended provenance ограничена схемой allowlist, версией политики, fingerprint-ссылками, окном, знаменателем и ключами компонент; произвольные исходные данные не возвращаются.

## Валидация и безопасные границы

- Проверяются schema/mode, component ownership и уникальные ключи, allowlist assumptions, fingerprint references, policy revision, source completeness, границы сумм/количества, scope дат и IANA timezone.
- Неполный/неизвестный/конфликтный источник возвращает `UNAVAILABLE`; он не становится нулевым расходом.
- Компонент, уже учтённый в базовых расходах, нельзя повторно передать как `ADDITIONAL`; исключённые/неизвестные компоненты не могут одновременно быть включены.
- Некорректные типы вложенных значений отказывают безопасно, без исключения и эха входного текста.
- Переданный legacy `cross_docking_per_unit` блокирует расширенное распределение: его знаменатель поставленных единиц нельзя смешивать со знаменателем продаж.
- `STRICT_RETAINED_COHORT` пока возвращает `UNAVAILABLE / STRICT_RETAINED_COHORT_NOT_IMPLEMENTED`; не показывается как готовая прибыль после возвратов. Реализация запланирована в W12.

## Проверки

- `tests/test_unit_price_scenario_extended_contract.py`: **19 tests** included in the passing combined profile.
- Изолированный объединённый профиль W05–W11: **175 passed in 2.71s**; включает normalizer, advertising, returns, additional expenses, window snapshots, readiness, operation trace и canonical scenario suites.
- Дополнительно до фиксации запускаются `py_compile`, проверка длины строк, `git diff --check` и проверка отсутствия изменений в `data/`.
- Использованы synthetic inputs, временная изолированная storage root и установленная проектная среда Python. Реальные Ozon-запросы, пользовательские базы и бот не запускались.

## Следующая работа

W12 реализует strict retained cohort и независимое window allocation с loss/unfinished outcome gates. Не ослаблять W11 явный отказ strict cohort до появления точной cohort evidence.

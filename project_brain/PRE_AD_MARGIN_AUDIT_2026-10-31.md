# Аудит подготовки ТЗ: маржа SKU до рекламы

Дата: 31.10.2026. Входной HEAD: `aad70b572b7f3bc37aaf79df302abe2eaa8b87d8`. Это аудит локального кода и связанных PR, не проверка данных живого магазина.

## Запрос владельца

Понимать реальную структуру маржи товара до рекламы. Владелец подтвердил: основной показатель после себестоимости, налога и прочих учитываемых расходов; процент от выручки продавца до вычета баллов. Запрошено ТЗ для другой модели.

## Что уже есть и что надо завершить

| Участок | Фактическое поведение на базе | Нужное расширение |
|---|---|---|
| ProductUnitEconomicsProvider.build_current | Себестоимость, комиссия, доставка/последняя миля, эквайринг, опциональный кросс-докинг и налог; реклама не вычитается | Явное название before-ad, состав и неполнота; не объявлять базовый результат полной экономикой |
| ProductUnitEconomicsQueryService | current и historical fallback; current_finance_days по умолчанию 2; отдельный returns-impact projection | Различать текущую модель/исторический scope и налог; показывать основную маржу и происхождение |
| CurrentProductEconomicsSource | Текущая цена/комиссия, усреднения по выбранным дням, отдельный 56-day crossdock | Сохранять периоды и supplied-unit denominator, не выдавать их за фактическое окно каждой продажи |
| UnitPriceScenarioService | margin_percent после рекламы и TaxService; absolute/percent ad, optional extended evidence | Самостоятельная canonical no-ad ветка, доступная при неизвестной рекламе; не менять legacy profit/margin |
| Expense evidence | Ownership и SKU attribution, отдельная CPC сверка, return/loss scope и source coverage | Использовать их для полного/неполного состава и исторического add-back, без перераспределения account costs |
| Сохранение/сетка/экспорт | Frozen inputs, schemas, bounded search, существующие serializers | Аддитивная проекция до/после, exact snapshot и parity consumers |
| Эксперименты W42–W44 | Проверяются current phase/control/collection revisions; stale candidates не ранжируются | Сохранить guards и действующую after-ad objective; не смешивать новые режимы в старом рейтинге |

## Подтверждённые границы

- Canonical прибыль до налога сегодня уже вычитает рекламу, а итоговая маржа делится на seller price. Простая новая подпись не создаст независимый before-ad показатель при неизвестной рекламе.
- Текущая юнит-экономика уже близка к before-ad базе, однако не доказывает полноту хранения/возвратных потерь. В одном из путей missing metadata перечисляет рекламу, хранение и возвраты; это не доказательство их фактического нуля.
- TaxService поддерживает NONE, USN_INCOME и USN_INCOME_MINUS_EXPENSES. В последнем no-ad налог может отличаться от налога after-ad. Задание не изменяет политику этого сервиса.
- Историческое `net_profit + financial_ads` корректно только при доказанном включении этих ads в исходный net и при одном SKU/периоде/COGS/tax scope. CPC из Performance не доказывает всю финансовую рекламу.
- В canonical extended режиме любой legacy `cross_docking_per_unit` блокируется `CROSS_DOCKING_DENOMINATOR_INCOMPATIBLE`. Нельзя снять это ограничение ради единого числа без доказательства совместимости; N01 использует отдельный совместимый expense3, а N17 отдельно проверяет crossdock rate2.
- Нет live проверки полноты источников, импорта новых XLSX или предположения, что магазин навсегда содержит один SKU. Фактическая историческая проекция при недостаточных источниках остаётся недоступной.

## Результат подготовки

ТЗ `LUNA_PRE_AD_MARGIN_TASK_2026-10-31.md`: 30 этапов MA00–MA29, 6 модулей, 20 групп numerical/behavioral acceptance, независимые current/model/historical основания, сохранность legacy и end-on-PR workflow. Журнал подготовлен со статусами NOT_STARTED.

Runtime, схемы и пользовательские данные в подготовке не меняются. Числовые примеры проверяются на текущем canonical calculator и Decimal; результаты подготовки записываются в журнал. Проверки подготовки документации не закрывают реализацию и не заменяют её CI.

Проверки подготовки: граф из 30 этапов ацикличен и полностью совпадает с журналом; 20 групп приёмки; 17 точных repo-relative code/docs paths существуют. Canonical numerical oracles N01/N03/N04/N05, отдельный crossdock case/сохранность guard и Decimal historical/weighted примеры прошли. Полные результаты и исправление локального timezone окружения записаны в журнале.

## Реализационный аудит MA01–MA04

Проверена фактическая ветка PR #722, от которой зависит PR #723. Локальный профиль исходного кода до реализации прошёл: **89 passed in 1.74s** — `test_product_unit_economics.py`, `test_product_unit_economics_query.py`, `test_current_unit_economics_integration.py`, `test_current_unit_economics_finance_sku.py`, `test_unit_price_scenario_service.py`, `test_unit_price_scenario_extended_contract.py`, `test_unit_economics_advertising_evidence_service.py`. SHA `data/tasks.json` остался `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; lock отсутствовал.

### MA01 — текущая и историческая карточка

- `CurrentProductEconomicsSource` берёт цену/тариф из `get_product_prices`, средние комиссию/логистику/последнюю милю/эквайринг/баллы из ограниченного финансового окна (по умолчанию 2 дня), кросс-докинг — отдельно из 56 завершённых дней на фактически принятые единицы.
- `ProductUnitEconomicsProvider.build_current` вычитает цену комиссии, логистику, последнюю милю, эквайринг, себестоимость и применимый crossdock, затем считает налог через `TaxService`. Ветвь рекламы отсутствует; текущий `margin_percent` уже является маржой модели без рекламного расхода, но существующий public response не называет её так и не доказывает полный expense scope.
- `ProductUnitEconomicsQueryService._attach_returns_impact` присоединяет возвраты отдельно и может показать risk-adjusted/estimated profit. Базовая прибыль провайдера при этом не включает возвратный компонент. Хранение и дополнительные расходы в current source не подтверждены; отсутствие строки не равно нулю.
- Исторический fallback использует выбранный Analytics период и агрегат `PeriodProfitService`; возвращает налог, COGS, accrual-derived profit/fees и количество, но устанавливает missing `advertising`, `storage`, `returns`. `ProductUnitEconomicsQueryService` не подключён к exact-SKU financial advertising evidence. Поэтому нынешний исторический after-tax profit нельзя безопасно подписать как «до рекламы» или восстановить add-back.

### MA02 — плановый калькулятор и потребители

- `UnitPriceScenarioService.calculate` — canonical one-successful-sale путь: `price`, `cost`, подтверждённая ставка комиссии, logistics/last mile/acquiring, points, advertising mode, tax mode/rates; суммы налогов передаются существующему `TaxService`.
- В текущем v2 результате `calculated.profit`/`margin_percent` — после рекламы. Даже если обязательные остальные поля заполнены, `advertising_rate` либо `advertising_cost_per_unit` требуется для `available=True`.
- Расширенные расходы применяются только с complete evidence. Legacy crossdock input в extended scenario намеренно возвращает `CROSS_DOCKING_DENOMINATOR_INCOMPATIBLE`; этот guard должен сохраниться.
- Результат потребляется Telegram calculator, target/grid/sensitivity, batch, advertising cap, sales mix, saved plans, observation/experiment и serializers. Сеточные consumers оптимизируют существующую after-ad цель. Новый показатель должен быть дополнительным и не менять её.

### MA03 — граница исторического факта

- `UnitEconomicsAdvertisingEvidenceService.resolve` допускает финансовые затраты по exact SKU/cohort только при подтверждённом типе, ownership, attribution и полном coverage; Performance CPC остаётся reconciliation-only.
- Это resolver не подключён к historical query provider, не выдаёт исторический налоговый basis, и в production factory нет collaborator, который может подтвердить одновременную область SKU/периода/COGS/количества/налога. Существующий `net_profit + financial_ads` можно вычислить только в offline pure case, где inclusion финансовой рекламы в base net явно подтверждён.
- Исторический public projection при обычном query остаётся `UNAVAILABLE` с точной причиной; не переводить Performance CPC, account-level ads, `other_fees` или неизвестную рекламу в add-back. Это не блокирует current/model before-ad projection.

### MA04 — аддитивный versioned projection

Зафиксирован контракт `pre_ad_margin` v1 (см. Decision 051): доступность денежного значения отдельно от полноты расходов; denominator — seller revenue before discount points; режим и tax basis явные; неизвестные expense keys не заполняются нулём; реклама для before-ad явно `EXCLUDED_BY_DEFINITION`, actual ad status при необходимости отдельно unknown/confirmed. Результат содержит nullable RUB/unit, nullable margin %, tax, known disjoint component summary, `included`/`unknown`/`excluded` scopes, provenance/source period and reason codes. Отдельные bases: `CURRENT_MODEL`, `PRICE_SCENARIO_NO_AD`, `HISTORICAL_RECONCILIATION`; tax basis соответственно текущая политика модели, canonical `NO_ADVERTISING_SCENARIO` или только `AS_RECORDED_IN_PERIOD_RESULT`.

Текущие старые `calculated.profit`, `calculated.margin_percent`, текущие provider поля, сохранённые старые plans/exports и experiment results не меняют значение и не мигрируются автоматически. Никакие read path не создают revision. Проверка MA01–MA04 опирается на перечисленные точные точки кода и исходный профиль 89 тестов; тесты/контракты реализации добавляются с MA05 и далее.

### MA05 — canonical no-ad branch

- В `UnitPriceScenarioService.calculate` добавлена отдельная versioned `pre_ad_margin` v1 проекция. Текущие `calculated.profit`, `calculated.margin_percent`, `available`, `scenario_version` и `inputs` продолжают представлять прежний after-ad contract; no-ad branch не редактирует owner input и сохраняет advertising as missing/null, не как нулевое допущение.
- Внутренний ноль применяется только в canonical components с `include_advertising=False`; поле `advertising_status=EXCLUDED_BY_DEFINITION` объясняет смысл. Существующий `TaxService` вызывается отдельно по no-ad gross profit; T0/T1 далее проверяются MA06.
- Для aggregate callers `calculate_components_only` добавлено derived `pre_ad_profit_before_tax`, пока без tax. Legacy `profit_before_tax` после рекламы не меняет значение.
- Неизвестный non-ad scope остаётся partial: storage, returns/cancellations, fixed overhead, unmapped expenses и отсутствующий crossdock явно перечислены. Extended expense unavailable может показать только partial core subtotal с unknown `EXTENDED_EXPENSE_EVIDENCE`. При несовместимых знаменателях проекция исключает crossdock; `CROSS_DOCKING_DENOMINATOR_INCOMPATIBLE` остаётся для extended after-ad результата.
- Новые regression cases проверяют неизвестную рекламу, immutability inputs, T0/T1, абсолютную рекламу выше цены, `NONE`, missing non-ad cost, aggregate contribution и crossdock guard.
- Фактический результат: targeted профиль **47 passed**; финальный linked профиль после последней правки **313 passed in 4.83s** (15 модулей: projection, scenario/extended contract, target/sensitivity/batch/mix/ad-cap/observation, current/historical query, Telegram UI/runtime). SHA-1 `data/tasks.json` остался `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; lock отсутствует.
- Первый linked pytest invocation сослался на несуществующий `test_telegram_unit_price_calculator_runtime.py`, поэтому тесты не стартовали; исправленный `test_unit_price_scenario_telegram_runtime.py` плюс полный профиль прошёл. Ошибка пути не учитывалась как проверка.

### MA06 — независимые T0/T1 и налоговый мост

- В scenario result добавлен `advertising_tax_bridge` v1. Формула: `after_ad_profit = pre_ad_profit - advertising + (T0 - T1)`. Хранятся оба налога и явные tax basis; при неизвестной рекламе bridge остаётся UNAVAILABLE, пока before-ad projection может быть доступна.
- Проверены N01: USN Income, T0=T1=4.50 ₽, before 33.50 ₽, after 21.50 ₽; N04: USN Income-minus-Expenses T0=5.70 ₽, T1=3.90 ₽, эффект 1.80 ₽, before 32.30 ₽, after 22.10 ₽; minimum tax T0=T1=1.00 ₽; `NONE` — налог 0.00 ₽. Проверенные delta равны 0.00 ₽.
- `TaxService` и налоговая политика не менялись. `calculate_components_only` не вызывает TaxService; явный TaxSpy остаётся пуст. SalesMix test `test_task_15_2_aggregates_rounded_unit_components_and_calls_tax_once` подтверждает один общий налоговый вызов для mix, не per SKU.
- Финальный linked profile **315 passed in 4.97s** на 15 модулях; `data/tasks.json` hash сохранился `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`, lock отсутствует.

### MA07 — выручка, проценты, знаки и округление

- Production code не менялся: проверка подтвердила, что `pre_ad_margin.margin_percent` строится от цены продавца до баллов, налоговая база остаётся внутри canonical `TaxService`, а денежные значения следуют существующему округлению.
- Добавлены независимые регрессии для seller-price denominator, налогового эффекта баллов (USN Income: налог 6.00 ₽ без баллов и 4.50 ₽ при 25% баллов; denominator остаётся 100 ₽), нулевой/отрицательной/out-of-range цены, подтверждённых нулевых расходов, отрицательной прибыли без обрезания и half-cent rounding.
- Точечный Windows профиль: **56 passed in 0.81s** на `test_pre_ad_margin_projection.py`, `test_unit_price_scenario_extended_contract.py`, `test_unit_price_scenario_service.py`. `data/tasks.json` SHA-1 остался `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; lock отсутствует.
- Ограничение: MA07 не утверждает полноту категорий расходов; это предмет MA08. Поскольку логика уже соответствовала контракту, этап отмечен `VERIFIED_EXISTING`.

### MA08 — ownership и полнота нерекламных расходов

- `pre_ad_margin.expense_scope` теперь имеет явные disjoint key sets: included, excluded (с ограниченной причиной), confirmed zero и unknown. Числовая доступность остаётся независимой от полноты.
- Постоянные расходы всего магазина исключены с причиной `OUTSIDE_SKU_CONTRIBUTION_SCOPE`; это сохраняет метрику SKU contribution и не называет её полной прибылью магазина. Storage/placement, возвраты/отмены, кросс-докинг без применимого источника и unmapped expenses остаются UNKNOWN, пока не подтверждены evidence.
- Категория `FINANCE_PAID_STORAGE` с полным source snapshot и суммой 0.00 отображается как included + confirmed zero и больше не остаётся UNKNOWN; явно исключённый source component отражается отдельно, не как ноль.
- Строгая когорта возвратов записывается один раз как `RETURN_LOSS_STRICT_COHORT`; generic additional total для этой ветки не дублирует loss pool. Components с known base-owned key (COGS, commission, logistics, last mile, acquiring), explicit advertising types или window-return type отклоняются как ownership conflict, если переданы как generic additional.
- Сохранён имеющийся guard совместного использования supplied-unit cross-docking и sales-unit extension. В ходе linked проверки обнаружено, что standalone extended cross-docking используется observation consumer; этот поддержанный контракт не блокируется.
- Связанный Windows профиль: **359 passed in 5.12s** на 17 модулях: projection, scenario/extended, return/additional evidence, target, sensitivity, batch, sales mix, ad cap, observation result, product/current economics и Telegram runtime. `data/tasks.json` SHA-1 остался `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; lock отсутствует.
- Первый промежуточный тестовый запуск выявил недостающий internal normalized component list, а следующий — допустимый standalone cross-docking contract. Оба вопроса закрыты; финальный полный связанный профиль зелёный.

### MA09 — рекламные модели и неполнота

- Canonical `UnitPriceScenarioService` принимает взаимоисключающие модели `PERCENT_OF_SELLER_REVENUE` и `ABSOLUTE_PER_SUCCESSFUL_UNIT`. Неизвестная реклама сохраняет доступный before-ad показатель, но не подменяет after-ad числом; оба явных нуля допустимы, абсолютная реклама выше цены может давать отрицательную after-ad прибыль. Смешанный payload отклоняется.
- Cross-mode regression проверяет одинаковые до-рекламные прибыль, маржу и налог для percent zero/nonzero, absolute zero/above-price, unknown ad и некорректного отрицательного absolute amount. Перед исправлением отрицательный ввод вызывал `AttributeError`, потому что `None` передавался в Decimal rounding. Теперь обе точки `calculate` и `calculate_components_only` безопасно fail closed для after-ad, а no-ad ветка остаётся доступной. `tests/test_unit_price_scenario_extended_contract.py` проверяет, что конфликт режимов тоже не блокирует независимый before-ad результат.
- `UnitEconomicsAdvertisingEvidenceService` не изменён: Performance CPC остаётся только reconciliation; net ad credit сохраняет знак и требует review при невозможности вывести валидную удельную ставку.
- Четыре целевых ad/evidence модуля: **78 passed in 1.08s**; связанный MA05–MA09 Windows профиль на 18 модулях после последнего components-only assertion: **378 passed in 5.34s**. `py_compile` и `git diff --check` прошли. `data/tasks.json` SHA-1 сохранился на `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; lock отсутствует.
- Ограничение: это подтверждает контракты расчётного сервиса и synthetic evidence, но не фактическую эффективность рекламы/причинный рост продаж. CPC не используется как ad cost в расчёте без отдельного подтверждённого режима.

### MA10 — текущая карточка SKU

- `ProductUnitEconomicsProvider.build_current` теперь добавляет `pre_ad_margin` v1, производный от уже рассчитанных current `net_profit_per_unit`, `margin_percent` и `tax`. Он повторяет существующие значения, не вызывает TaxService второй раз и не меняет старые поля. Налоговое основание указано как `CURRENT_TAX_POLICY`, знаменатель — seller revenue до баллов, реклама — UNKNOWN/null.
- Число остаётся отдельно от полноты: базовые подтверждённые расходы перечислены в `known_non_ad_expenses_rub`, отсутствующие cross-dock/storage/placement/return/unmapped значения остаются UNKNOWN, fixed store overhead явно исключён. Если нет обязательных входов или seller price, projection имеет `status=UNAVAILABLE`; legacy current result сохраняет прежний контракт.
- Query передаёт точные границы запрошенного недавнего финансового окна и число наблюдавшихся дней продаж, timestamp цены и только allowlisted cross-dock metadata. Периоды относятся к разным источникам и явно разделены. Current formatter отображает существующую note: дни финансового выборочного окна, cross-dock average по 56 завершённым дням и supplied-unit denominator, а также предупреждение о неполном составе расходов.
- `tests/test_current_unit_economics_integration.py` проверяет parity прежних 33.45 ₽ / 34.84% / 5.76 ₽; seller-price denominator при налоговом basis buyer price; partial scope и unknown ad; корректное включение cross-dock; unavailable для missing price; раздельные finance/cross-dock periods; видимый note и allowlist/ограничения источниковых метаданных.
- Связанный Windows профиль MA05–MA10: **401 passed in 6.09s** на 21 модулях; `py_compile` и `git diff --check` PASS. `data/tasks.json` SHA-1 прежний `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; lock absent. Full pytest и exact-head CI ещё не выполнены.

### MA11 — произвольная плановая цена и точный тариф

- Кодовый путь `_prepare_tariff` разрешает кандидата по точным frozen tariff ranges, а `apply_price_planning_candidate` переносит тариф/происхождение выбранной строки в canonical scenario calculation. Для legacy single-rate snapshots ставка привязана к exact price anchor; другая цена становится UNKNOWN до применения явного тарифного профиля или ручной комиссии.
- `test_tariff_aware_comparison_uses_frozen_per_price_rate_and_no_extra_source_reads` подтверждает разные ставки 11%/11%/22% для 99,99/100,00/100,01 ₽, точный `pre_ad_margin` выбранного кандидата, сохранение исходного COGS/ad override и отсутствие второго source read.
- Новая `test_manual_commission_at_candidate_price_preserves_price_cost_and_advertising` проходит публичный runtime edit flow: подтверждённая текущая ставка не переносится на кандидат без тарифа; маржа недоступна до ручного ввода; после ввода комиссия имеет provenance `manual_seller_assumption`, а цена 100,01 ₽, COGS 25 ₽ и реклама 8% сохранены. Canonical результат до рекламы −6,79 ₽/−6,79%, after-ad −14,79 ₽/шт.
- MA11 статус `VERIFIED_EXISTING`: производственная логика уже отвечала контракту, добавлены явные regressions на незакрытые projection/preservation assertions. Windows профиль runtime + frozen snapshot adapter + tariff-profile runtime: **61 passed in 1.53s**. Нет live API, файлов хранилища или изменения production calculation.

### MA12 — историческая маржа до рекламы

- Добавлен отдельный `ProductUnitEconomicsHistoricalPreAdMarginService`. Он сохраняет исходную посленалоговую прибыль и налог и возвращает до прибыли только суммы CPC/CPO/OTHER, если финансовый resolver подтвердил, что весь точный SKU расход уже включён в тот же net.
- Обязательны: полное покрытие типов рекламы, нулевые additional/reconciliation/account/window ledgers, точный owner/store/product/offer/SKU/schema, полный исторический accrual date window и положительные успешные единицы/выручка. Новый `financial.exact_sku_attribution_complete` отличает exact SKU от exact cohort; cohort не распределяется на один SKU. Net credit требует review, CPC Performance не добавляется.
- Synthetic N09 даёт 1 005 ₽ before-ad / 33,50 ₽ на единицу / 33,50% при net 645 ₽, рекламных начислениях 360 ₽ (после одной корректировки) и сохранённом налоге 135 ₽; Performance CPC 359,98 ₽ остаётся только сверкой. N10 неполная CPO, N11 сохранение исторического налогового основания, N12 нулевой знаменатель, N16 duplicate ownership/correction, cohort/store/window mismatch и production query unavailable покрыты тестами.
- `StorePeriodProfitService` и production factory пока не предоставляют точный финансовый ad evidence envelope, поэтому обычный исторический запрос остаётся `UNAVAILABLE` (`HISTORICAL_ADVERTISING_EVIDENCE_NOT_CONNECTED`). Legacy result и независимый current/model path не меняются. Синтетическая интеграция доказывает контракт, но не означает live data availability.
- Налог копируется из результата существующего historical query и помечается `tax_provenance=EXISTING_HISTORICAL_QUERY_RESULT`; projection не вызывает TaxService повторно и не утверждает, что это отдельная запись официальной налоговой отчётности.
- Связанный Windows профиль: **156 passed in 2.83s** на 9 модулях; `py_compile` и `git diff --check` PASS; `data/tasks.json` SHA-1 до/после одинаковый; live Ozon/Telegram запросов не было.

### MA13 — сетка и сравнение цен

- `UnitPriceTargetPlanningService.compare_prices` now returns per-candidate `pre_ad_margin`, after-ad result and explicit ranking basis. Default ranking remains the existing after-ad profit per successful unit; rows with different tax, revenue, unit-denominator or ad-mode bases are not combined under one maximum.
- The existing SKU calculator has a separate explicit no-ad grid action. The mode models zero advertising only for that scenario; it is not an observed value or a forecast of advertising response to price. Applying a candidate from this view does not overwrite the user's active advertising assumption.
- Regression coverage includes the N01 baseline (100 ₽ → 31.74 ₽/31.74% before ad and 15.24 ₽/unit after 16.5% advertising; 95 ₽ → 27.95 ₽/29.42% before ad and 16.55 ₽/unit after 12% advertising), default after-ad maximum, no-ad maximum, input immutability, Telegram copy and response length.
- Implementation touches target planning service, existing calculator runtime and keyboard; no solver goal or saved-plan schema changed. Linked Windows/Python profile: **255 passed in 5.89s** on 9 consumer modules. `data/tasks.json` SHA-1 unchanged; no live request or real bot.
### MA14 — целевые сценарии, чувствительность, пакетный план, mix и экспорты

- Калькулятор целевой маржи, строки sensitivity и batch-план используют `pre_ad_margin` того же уже вычисленного кандидата/current scenario. Дополнительные поиски, чтения источников, оценки SKU или вызовы solver не добавлены; существующая цель оптимизации и ranking не менялись.
- В сводном плане продаж агрегируется canonical прибыль до налога по SKU × плановое количество, вычитаются те же подтверждённые общие расходы, а налог сравнивает after-ad и no-ad aggregate bases одним вызовом публичного `TaxService.calculate`. Постналоговые поля и итоги существующего mix сохранены.
- Денежные суммы mix взвешиваются выручкой продавца до баллов: контрольная смесь 20 ₽ прибыли на 100 ₽ и 90 ₽ на 300 ₽ даёт 110/400 = 27,50%, а не невзвешенные 25%. Налоговый basis и отсутствие рекламы в before-ad помечены.
- Telegram screen для target, sensitivity, batch и saved-plan показывает до рекламы вместе с после-рекламным результатом; частичный expense scope остаётся явно помечен. CSV/JSON exports добавляют before-ad projection для target grid, sensitivity, batch и saved-plan без изменения сохранённого schema.
- Первый связанный прогон выявил три тестовые ошибки предположений; фикстуры/ожидания поправлены. Повторный полный связанный Windows-профиль после commit `0ead66f5`: **261 passed in 5.38s** по 9 модулям. `py_compile` и `git diff --check` PASS. `data/tasks.json` SHA-1 сохранён (`7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`), lock отсутствует. Live Ozon/Telegram calls не выполнялись.
- Этап не меняет default price ranking, solver budget, сохранённые планы, source reads или публичные поля legacy after-ad результата. Экспорт включает JSON-проекцию; синтетические тесты подтверждают присутствие данных, но не проверяют запуск реального бота.

### MA15 — основной экран SKU

- `ProductUnitEconomicsQueryService.format_response` выводит `pre_ad_margin` сразу после заголовка current/historical карточки: чистая прибыль до рекламы на единицу, процент от цены продавца до баллов, налоговое основание и полнота прочих не рекламных расходов. Для current-модели рядом показан только whitelist налоговых режимов; для historical явно сохраняется налог существующего периода.
- Если рекламные данные UNKNOWN, экран говорит, что прибыль после рекламы не рассчитана. Он никогда не выводит 0 ₽ как замену отсутствующей рекламы. Historical after-ad показывается только при `CONFIRMED_INCLUDED_IN_NET` и числовом исходном результате; иначе после-рекламная прибыль не заявляется.
- Отображены источник/период текущих финансовых начислений, наблюдавшиеся дни продаж, дата актуальности цены и (для исторического evidence) границы accrual window. Для partial expense scope показаны известные неподтверждённые классы. Причины UNAVAILABLE переведены в короткие пользовательские формулировки; значения SKU и частные поля evidence не раскрываются.
- Основной путь использует действующий formatter и общий `split_telegram_text`; новый отправитель/путь Telegram не создан. Legacy components, profit fields, historical reconciliation и current/model boundaries сохранены.
- Linked Windows profile на финальном MA15 изменении: **42 passed in 1.07s** на 4 модулях; `py_compile` и `git diff --check` PASS. `data/tasks.json` SHA-1 — `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; lock отсутствует. Live API и запуск бота не выполнялись.

### MA16 — ledger расходы и происхождение

- Добавлен `format_expense_breakdown(result)`, который читает только уже вычисленную projection и не вызывает source/query/calculation dependencies. Для current-модели ledger использует seller price, canonical known non-ad expenses и canonical tax; он проверяет точное равенство с pre-ad profit. При partial scope недостающие суммы названы и остаются неизвестными; реклама обозначена как исключённая из before-ad, а не нулевая.
- Для exact historical advertising evidence показаны seller revenue, известный expense-scope COGS, исторический налог, exact-SKU ad total с однократными корректировками и before/after net. Неразнесённые non-ad fees представлены только вычисляемым balance, а не заявлены как конкретные типы начислений. Проверяются before-ad arithmetic bridge и независимый after-ad sum до копейки.
- Кросс-докинг показан отдельной подстрокой уже включённого line item; источник/сумма и делитель (фактически принятые cross-dock units) помечены как детализация, которую нельзя сложить повторно. Source windows отображаются по каждому доступному виду: цена, finance sample, historical accrual window и cross-docking window.
- Кнопка uses opaque per-user token and bounded in-memory snapshot (15 minutes, 512 entries); details read never re-queries. Other user, expired callback or missing snapshot returns a safe reopen instruction. Snapshot stores only the ready text, no owner/source IDs or raw API payload; it is not persisted.
- Первый MA16 прогон поймал некорректное форматирование строкового Ozon crossdock amount; форматирование исправлено и вся связанная группа повторно прошла. Final Windows profile: **44 passed in 1.12s** на 4 модулях. `py_compile`, `git diff --check` PASS, data hash `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215` unchanged, lock absent. No real API or bot.

### MA17 — действия при неполной проекции

- Существующая форма себестоимости открывается для выбранного SKU. После подтверждённого сохранения одноразовый 15-минутный token возвращает к тому же SKU; перед возвратом проверяются пользователь, tenant и активный магазин. Смена магазина, replay, expiry или другой пользователь завершаются fail-closed. Новый unit query запускается только после явного нажатия возврата.
- Существующая кнопка планового сценария доступна для ручного тарифа и рекламных допущений. Они сохраняют provenance сценария и не превращаются в фактические current/history данные. Внутри сценария остаются прежние ID, revision и CAS guards.
- `Пересчитать этот SKU` явно повторяет factual query; snapshot token связан с пользователем и tenant. Открытие ledger не читает источники. Автоматического retry нет.
- Если для расхода нет подтверждённого per-SKU источника или формы ввода, сообщение называет неподдерживаемые классы; они остаются неизвестными и не распределяются. Store-level расход не предлагается как корректировка SKU; нули не подставляются.

### MA18 — текущие, исторические и экспериментальные представления

- Current and historical SKU cards already carried `pre_ad_margin.tax_basis`, current `tax_mode` or historical tax preserved from the selected period, expense completeness, source periods, and ad status. Existing legacy profit/margin fields and saved historical records remain unchanged.
- The frozen price-experiment snapshot projection remains schema v1, read-only, source-I/O-free and `recalculated=False`; its existing plan input contains the tax mode/rate but not the tax-setting origin. The Telegram frozen view now labels that limitation rather than inferring source provenance, and explicitly says the new pre-ad projection was not applied to this saved experiment.
- A stored experiment result is still the old observation/ranking result, not a pre-ad margin calculation. Its detail shows its saved source timestamp, window, and count of linked snapshot references without exposing reference IDs; where the result schema has no tax basis, the view states that it was not saved and that the new pre-ad margin was not applied.
- No experiment result, revision, ranking input, W42–W44 guard, persistence schema, or export projection was rewritten. Regression profile across 8 modules: **113 passed in 4.23s**; `py_compile`, diff check and owner data hash pass.
- Linked Windows profile: **98 passed in 1.95s** across 6 modules; `py_compile` and `git diff --check` PASS; owner data SHA-1 unchanged, lock absent. No live Ozon/Telegram request or real bot.

### MA19 — публичная offline-приёмка одного SKU

- При проходе от текущей карточки к подробностям и затем к плановой цене обнаружено, что открытие локального `unit_economics_details:` очищало токен выбранного SKU; сценарий цены после этого становился stale. Очистка теперь сохраняет selection для локальных подробностей; добавлена регрессия по публичным callbacks.
- При сохранении сценария цена с десятичной запятой (`100,01`) оставалась в raw-формате и отклонялась frozen-plan repository. Capture теперь валидирует ввод через существующий decimal parser и сериализует каноническое точное значение (`100.01`) без округления; нечисловой ввод fail-closed.
- Основной calculator summary/detail явно показывает `pre_ad_margin` после налога, её полноту, отдельную сценарную маржу после рекламы и текст о неизвестной рекламе как неизвестной, а не нулевой. Legacy строки и вычислительные результаты не переопределены.
- Offline end-to-end regression покрывает current → unknown ads → details → плановая цена → комиссия, отличающаяся от исходной → DRR → before/after → сохранение. Проверены before-ad −6,79 ₽/−6,79%, after-ad −14,79 ₽/шт., ручной provenance комиссии и один factual query. Historical exact/partial cases подтверждены связанными existing regressions.
- Final linked Windows profile: **121 passed in 3.60s** на 6 модулях. `py_compile` и `git diff --check` PASS. `data/tasks.json` SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`, lock отсутствует. Implementation commit `d8532f9a`; live Ozon/Telegram requests и bot launch не выполнялись.

### MA20 — frozen plans и старые схемы

- Production change was not needed: legacy v1/v2 payloads remain readable without current-source reload; v2 plans without frozen tariff/ad basis preserve their original manual assumptions. A tariff refresh is explicit and stores a new revision while the old revision retains the original tariff. Existing guards reject corrupt and future schema payloads without hiding other documents.
- Added read-invariance assertions to `tests/test_planning_workspace_repository.py::test_corrupt_and_future_document_versions_fail_closed_without_hiding_other_rows`: persisted document and revision fields, JSON, revision numbers and timestamps are identical before/after reads and list operations.
- Linked Windows profile: `tests/test_planning_workspace_repository.py` and `tests/test_saved_planning_plan_telegram_flow.py` — **51 passed in 2.35s**. Test commit `2423742b`; owner data SHA-1 unchanged, lock absent. No schema migration, live source call or bot launch.

### MA21 — export из того же price snapshot

- Existing sensitivity and batch export boundaries already accept their frozen in-memory result; freshness checks use the originating scenario/batch snapshot and do not load Ozon data. The serializer keeps JSON projection data intact and emits JSON-valued columns in CSV.
- Extended the real sensitivity runtime regression to export both JSON and CSV from one displayed result, then compare each exported `pre_ad_margin` with the exact originating cell. Assertions cover seller-revenue denominator, no-ad tax basis, one-successful-unit basis, expense scope, source periods, after-ad advertising/tax fields, source-as-of metadata and one source call only.
- Linked Windows profile: `tests/test_analytics_export_service.py`, `tests/test_analytics_export_serializer.py`, `tests/test_telegram_unit_price_sensitivity_runtime_service.py`, `tests/test_telegram_unit_price_batch_plan_runtime_service.py` — **48 passed in 1.54s**. Existing serializer tests preserve formula safety, nullable versus zero values, and size limits. Test commit `7c4f6595`; owner data hash unchanged, lock absent; no production/schema changes.

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

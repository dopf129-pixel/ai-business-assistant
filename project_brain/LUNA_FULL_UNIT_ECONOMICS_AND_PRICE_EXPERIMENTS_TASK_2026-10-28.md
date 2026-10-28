# ТЗ Luna: расширенная экономика SKU и управляемые ценовые эксперименты

Дата: 28.10.2026. Программа: W00–W39, модули A–H.
Статус: READY_FOR_IMPLEMENTATION; это задание, не отчёт о выполненной реализации.
База подготовки: main 9315046cf29c9e8c68da1cab027cb2568040f142 после слияния PR #719 и #720.
Журнал: LUNA_FULL_UNIT_ECONOMICS_AND_PRICE_EXPERIMENTS_PROGRESS_2026-10-28.md.
Основание: FULL_UNIT_ECONOMICS_AND_PRICE_EXPERIMENTS_AUDIT_2026-10-28.md.

## 1. Продуктовая цель и решения владельца

Владелец хочет выбирать цену продавца Ozon, при которой максимальна прибыль в рублях с одной успешно проданной единицы SKU. Рост количества заказов сам по себе не заменяет эту цель.

В этой программе закончить два направления:

1. Расширенная экономика SKU: подтверждённые рекламные расходы, потери возвратов/невыкупов, размещение и другие доказуемо относимые расходы; прозрачные источники и отсутствие двойного учёта.
2. Пошаговый ценовой эксперимент: исходная цена, следующий кандидат, подтверждение фактической смены владельцем, сбор завершённых окон, проверка условий и понятная рекомендация.

Уже принятые решения сохраняются:

- цена — цена продавца, а не цена покупателя после скидок;
- комиссия зависит от диапазона цены; при отсутствии подтверждения пользователь может задать ручной тариф;
- налоговая база и налоговая политика остаются в существующих TaxService/настройках магазина;
- переменные баллы за скидки — наблюдаемое/сценарное допущение с provenance, а не вечная константа;
- единицы продаж не вводятся вручную вместо отсутствующего подтверждённого количества;
- новая рекомендация не меняет цену, ставку или кампании в Ozon;
- FBO — первая поддерживаемая схема этой программы, FBS получает явный UNSUPPORTED, без переноса FBO-тарифов;
- текущий калькулятор, сохранённые планы, наблюдения и отчёты должны продолжить работать.

## 2. Режим автономного исполнения

Начать с W00, выполнять этапы по зависимостям. После каждого этапа делать небольшой проверяемый commit, обновлять журнал и фактические результаты. Не останавливаться для промежуточного согласования обычных технических решений.

На каждом этапе:

1. Прочитать актуальную строку журнала, предыдущие evidence и применимые AGENTS.md.
2. Обозначить входной/выходной контракт и конечную приёмку.
3. Внести минимальную реализацию и содержательные регрессии.
4. Выполнить профиль этапа, записать команду, окружение, SHA/базу, результат и ограничения.
5. Обновить CHANGELOG.md, CURRENT_STATE.md, TEST_MAP.md по фактическому изменению; DECISIONS.md — только при реальном архитектурном решении.
6. Проверить diff и сохранность owner data; продолжить следующий доступный этап.

После сокращения контекста продолжить по журналу: текущая ветка, HEAD, dirty/untracked, последние проверки, следующий этап. Не начинать программу заново и не объявлять этап готовым по старому CI.

Завершить на готовых PR с зелёным CI актуального HEAD и пакетом независимого review. Слияние, развёртывание, запуск/остановка реального бота, реальные Ozon-запросы и изменение цен этой программой не авторизованы.

Не ждать внешних данных, если можно закончить контракт, synthetic приёмку и честный unavailable-путь. Отсутствие подтверждения источника — продуктовый статус, а не основание выдумывать API, количество, нулевой расход или бесконечно блокировать остальные модули.

Обращаться к владельцу только если:

- изменяется цель оптимизации, правило налога или политика реального учёта;
- требуется обязательная платная подписка или платный внешний сервис;
- нужно автоматическое действие в Ozon, фоновые запросы либо отправка уведомлений;
- возникает неустранимый конфликт данных/доступа, который нельзя изолировать или представить ограничением продукта.

Время работы определяется готовностью приёмки. Не растягивать работу до заданного количества часов и не заменять реализацию многократным запуском одних и тех же тестов.

## 3. Область работ и архитектурные границы

### 3.1. Переиспользовать

| Ответственность | Существующая точка расширения |
|---|---|
| Компоненты одной продажи и налог | app/services/unit_price_scenario_service.py; app/services/tax_service.py |
| Тарифные интервалы, frozen evidence | unit_price_tariff_resolver.py; unit_price_tariff_snapshot_adapter.py; unit_price_tariff_source.py |
| Поиск цены, сравнение, рекламные пороги | unit_price_target_planning_service.py; unit_price_advertising_compensation_service.py; unit_price_advertising_cap_service.py |
| SKU/периодные источники | unit_price_scenario_source.py; finance_service.py; experimental_store_economics_runtime_service.py; period_profit_query_service.py и действующие adapters |
| Возвратные финансы и количества | returns_finance_attribution_facts_source.py; returns_finance_attribution_analytics_service.py; returns_buyout_facts_source.py; returns_buyout_analytics_service.py |
| Физическое восстановление товара/COGS | return_inventory_recovery_repository.py и существующие period_profit_return_cogs_* services |
| Наблюдения/качество/рейтинг | unit_price_observation_collection_service.py; unit_price_observation_normalizer.py; unit_price_observation_result_service.py; unit_price_observation_quality_service.py; unit_price_observation_ranking_service.py |
| Хранение, версии, CAS, scope | planning_workspace_repository.py; saved_planning_plan_service.py |
| Telegram | telegram_unit_price_calculator_runtime_service.py; telegram_unit_price_observation_runtime_service.py; существующие batch/sensitivity/saved-plan runtimes |
| Общий лимит запросов/времени | period_profit_operation_diagnostics.py; существующие Ozon/Performance clients |
| Выгрузка/backup | analytics_export_service.py; analytics_export_serializer.py; существующий backup/restore |

Имена в таблице без каталога относятся к app/services/. W01 обязан подтвердить фактические фабрики и интерфейсы.

Новые pure-сервисы нормализации/quality/state-machine допустимы, если у каждого одна ответственность. Не создавать второй финансовый движок, отдельную SQLite-базу для экспериментов, competing repository, scheduler, универсальный workflow framework или LLM-калькулятор денег.

### 3.2. Вне программы

Автоматическая смена цены/рекламы, фоновые сборы и уведомления; мониторинг конкурентов и scraping кабинета; прогноз спроса/глобально оптимальной цены; закупки и поставки; обязательный Premium Analytics; изменение юридической налоговой политики; полная переработка проекта.

Основные финансовые итоги и уже проведённые Return COGS не исправляются этой программой как побочный эффект. Подтверждённую отдельную ошибку вынести в небольшой отдельный fix с её собственной приёмкой.

## 4. Что означает «полнее»

Название функции не доказывает полноту. В каждом результате хранить cost_scope: ожидаемые категории, включённые, исключённые, неизвестные, причины, покрытие и основание знаменателя.

Нужны различимые режимы:

| Режим | Назначение | Правило сравнения |
|---|---|---|
| LEGACY_SUCCESSFUL_SALE_MODEL | Текущий сценарий успешной продажи; старые версии | Сохраняет прежнюю формулу и ограничения |
| WINDOW_COST_ALLOCATION_MODEL | Расходы периода, распределённые по доказуемому количеству; модель | Только с тем же denominator/date/allocation policy; явно не итог когорты |
| COHORT_RETAINED_SALE_MODEL | Модель успешной сохранённой продажи с потерями той же сопоставленной когорты | Требует строгого quantity/lineage/cost gate |
| OBSERVED_PERIOD_FINANCE | Фактические денежные агрегаты периода | Контекст/сверка, не удельная прибыль конкретной цены автоматически |

Названия можно адаптировать к проекту; смыслы и раздельные versioned контракты обязательны. Не повышать старый результат до нового режима при чтении.

Если строгий режим недоступен, пользователь получает работающую карточку причин и доступный ограниченный расчёт. У него не появляется пометка «все расходы учтены». Рейтинг не смешивает эти основания.

## 5. Данные и идентичность

### 5.1. Контракт каждого компонента

Минимальная семантика; конкретные поля/типы согласовать на W03:

- точные owner/store/product/offer/SKU/sale_schema и version;
- category, source, source_method/contract_version, evidence_revision/fingerprint;
- исходная подписанная сумма Ozon и нормализованная сумма расхода;
- numerator_amount, denominator_units, denominator_kind и unit_amount;
- source_window, date_basis, timezone/неизвестная зона, received_at/as_of;
- attribution: EXACT_SKU, EXACT_COHORT, WINDOW_ALLOCATION, UNATTRIBUTED;
- correction/reversal/dedup semantics, completeness, settlement status;
- component ownership: уже включено в base component, дополнительное или только сверка;
- origin: подтверждённый источник / расчётное распределение / явное допущение;
- applicability к цене/периоду, recurring/one-off/unknown, included/excluded reason.

Деньги и rates — Decimal внутри расчётов, сериализация в существующем ограниченном формате; NaN, Infinity, bool и oversized значения отклонять. Отсутствующее значение отличается от подтверждённого нуля.

Одна операция может содержать несколько услуг. Dedup key учитывает ID операции и стабильную идентичность её части. Две разные услуги одной операции нельзя свернуть в одну; повтор одной услуги нельзя посчитать дважды. Конфликтующий duplicate блокирует применимость компонента.

Raw posting/return IDs можно использовать transient для join/dedup по действующим правилам. Новые planning records сохраняют только allowlisted агрегаты, coverage, версии и безопасные fingerprints. Не добавлять сырые ответы, ключи, названия, номера отправлений или весь финансовый ledger в planning payload.

### 5.2. Количества и часы

Различать ordered units, delivered units, cancelled units, confirmed returned units, retained units, posting count, report row count, supplied units. Число строк и отправлений не равно количеству товаров.

Для строгой когорты:

    Q_retained = Q_delivered - Q_confirmed_returned_from_these_deliveries

Вычитание допустимо только при exact SKU/posting lineage, согласованных quantity и доказанном событии возврата/отмены реализации. Наличие type=ClientReturn или смены visual status само по себе этого не доказывает.

Returns со сменой статуса в периоде не вычитать из произвольных продаж того же календарного периода. Указанная дата состояния, дата начисления, дата продажи, дата отчёта Performance и дата восстановления товара сохраняют собственное основание.

Q_retained=0, отрицательное значение, returned>delivered, неизвестная полнота или неразрешённые отправления не дают удельной прибыли. Денежные суммы при этом остаются доступны.

Завершённый календарный день не равен окончательному расчёту Ozon. Поздняя корректировка создаёт новую result revision, старые расчёты остаются неизменными.

### 5.3. Средние и применимость

Начальный исторический ориентир для планового расхода — 56 полностью завершённых локальных календарных дней. Сохранять точные границы, доступное покрытие и дату. Частичное окно не называть полными 56 днями; источник с более коротким доказанным горизонтом получает отдельный статус.

    unit_expense = sum(compatible_net_expenses) / sum(compatible_units)

Не усреднять дневные rates, средние на отправление и средние на единицу между собой. Ставку кросс-докинга за поставленную единицу не преобразовывать в ставку за проданную без отдельной доказанной модели; действующее правило кросс-докинга сохраняется.

Исторический ориентир 56 дней — условие будущей модели. Он не является фактом нового ценового этапа. Для сравнения вариантов с таким ориентиром требуется один frozen reference snapshot.

## 6. Правила отдельных расходов

### 6.1. Реклама

- Финансовые начисления — основной кандидат на весь подтверждённый расход, когда доказаны категория, полный охват и SKU attribution.
- CPC из Performance и CPC из финансов — альтернативные представления одного расхода, не два расхода. При наличии financial primary Performance остаётся сверкой.
- CPO/«за заказ»/другие типы выделяются только по подтверждённому source mapping; имя само по себе не доказывает SKU и отсутствие пересечения.
- Account/campaign расход без проверенного SKU распределения показывать отдельно. Не делить его по выручке, продажам или CPC автоматически.
- Нулевой ответ, отсутствие кампании и partial/429 различаются. Отсутствие CPC не означает отсутствия рекламы.
- Сохранить режимы процент от seller price и абсолютный рекламный расход на совместимую единицу. Абсолютный расход может превышать цену товара; его нельзя искусственно ограничить ставкой 100%.
- При смене цены: fixed RUB/unit остаётся fixed RUB/unit; percent остаётся percent. Преобразование не должно тихо менять выбранное допущение.

### 6.2. Возвраты и невыкупы

Существующий observed_net_amount_total по отправлениям не является готовой суммой потерь: там могут находиться продажа, возврат выручки, комиссии и услуги. observed_average_per_posting нельзя подставить как RUB/unit.

Для строгой модели учитываются дополнительные потери несостоявшихся/возвращённых продаж:

- подтверждённые транспортные/обработочные расходы на эти исходы;
- остаточная комиссия только после сопоставления удержания и возврата комиссии;
- подтверждённая невосстановимая себестоимость минус соответствующая компенсация, без второй COGS-проводки;
- другие однозначные потери, не включённые в успешную продажу.

Gross refund выручки не вычитать как расход из модели, которая изначально считает выручку только retained-продаж. Возвращённый пригодный товар не списывать по себестоимости. SALEABLE_RESTORED подтверждать существующим local inventory/accounting evidence, не одним статусом Ozon.

Pending disposition не равен нулевой потере и не равен полной себестоимости. Показать known amount и unresolved exposure; строгий полный показатель недоступен. Новая плановая оценка не создаёт финансовую проводку и не меняет историю recovery.

### 6.3. Хранение/размещение и прочие услуги

Использовать доказанные типы начислений/товарный отчёт, когда доступно подтверждённое сопоставление и период. Missing не превращать в 0.

Хранение делится на проданные единицы только как явно подписанное window allocation: такой расход зависит также от остатка и времени. Разные остатки/оборачиваемость — изменение условия эксперимента. Если SKU не определён, расход остаётся в общих расходах магазина.

«Прочие начисления» как расчётный остаток не является допустимой категорией для автоматического дополнительного вычитания из юнита.

### 6.4. Знаки, корректировки, повторное включение

Сохранять signed finance amount. Для суммы удержаний S нормализованный expense E=-S: отрицательное начисление увеличивает расход, положительная коррекция уменьшает.

Net credit хранить отрицательным расходом в фактической сводке. Не обрезать до нуля. Разовую компенсацию не экстраполировать как постоянный доход следующего периода: recurring rate получает CREDIT_REQUIRES_REVIEW/UNKNOWN, пока применимость не доказана. Это не мешает показать историческую сумму.

До применения собрать coverage ledger: каждая финансовая часть принадлежит одной группе — BASE_ALREADY_INCLUDED, ADDITIONAL_INCLUDED, RECONCILIATION_ONLY, UNATTRIBUTED или UNKNOWN. Пересечение базовой логистики/комиссии/рекламы с дополнительной суммой блокирует её применение, а не решается повторным вычитанием.

## 7. Расчёт, налог и совместимость

Для полностью пригодной модели:

    G(P) = P - C - Commission(P) - Delivery - LastMile - Acquiring
           - CrossDocking - Advertising(P or RUB/unit) - AdditionalUnitExpenses
    Tax(P) = existing TaxService under active-store scenario policy
    Profit(P) = round_money(G(P) - Tax(P))

AdditionalUnitExpenses — сумма только взаимоисключающих применимых нормализованных компонентов. В неё не входят уже включённые расходы.

Для strict cohort ожидаемые потери распределяются на Q_retained. Для WINDOW_COST_ALLOCATION_MODEL denominator_kind задаётся явно и показывается; он не переименовывается в retained units. Расчёты разных denominator_kind не участвуют в одном рейтинге.

Расходы должны входить в соответствующую base для вызова TaxService. Простое вычитание дополнительных расходов из уже посчитанной прибыли может дать неправильный налог в USN_INCOME_MINUS_EXPENSES. Сохранять существующую модель передачи gross_profit и минимум налога; распределение операционного расхода само по себе не подтверждает его юридическое признание.

Не переписывать TaxService. Если существующая налоговая политика не способна выразить выбранный новый режим, вернуть явную несовместимость режима и продолжить остальные этапы; изменение налоговой политики требует решения владельца.

Расширить canonical forward аддитивным versioned контрактом. Не зашивать новые потери в поле cost и не создавать отдельный расчёт в Telegram/ranking. Legacy payload без нового mode/scope считается legacy, а не новым полным режимом с нулевыми расходами.

Потребители одного режима должны согласованно использовать те же компоненты:

- одиночный калькулятор и сравнение 2–10 цен;
- таргет/безубыточность, рекламные пороги и сетка;
- sensitivity, batch, saved plans и mix;
- результат наблюдения, quality/ranking и export.

При агрегатном mix налог по-прежнему считается один раз на группу. Не умножать per-unit tax и не добавлять один expense pool каждому SKU.

Расширение forward меняет условия search envelope. W15 обязан обновить bounds/guards всех solver-путей, независимо сверять результат и минимальность на копеечной сетке, сохранять per-SKU/shared budgets и R8 recovery. Если формула не поддержана solver, UNKNOWN/UNSUPPORTED, а не неподтверждённый минимум.

## 8. Управляемый ценовой эксперимент

### 8.1. Пользовательский путь

Карточка SKU → «Проверить цену на практике» → цель/исходный сценарий → проверка полноты → baseline → варианты следующей цены → preview условий → план эксперимента → подтверждение владельцем фактически установленной цены и времени → сбор завершённого окна → оценка качества → рекомендация/следующий шаг → история/выгрузка.

Владелец меняет цену в Ozon самостоятельно. Плановая дата не является фактической датой смены. Позднее подтверждение не переписывает результат уже собранного окна.

У одного owner/store/SKU/scheme — не более одного активного эксперимента; использовать существующий guard активного наблюдения, чтобы старый и новый сценарии не обходили ограничение друг друга.

Наблюдение фазы принадлежит своему experiment, а не конкурирует с ним за guard. Baseline observation завершается перед активацией candidate observation в одной защищённой операции; два ACTIVE phase для одного SKU невозможны. Прямое открытие старого observation flow не обходит эту защиту.

### 8.2. Состояния

Предметные состояния: DRAFT → READY → BASELINE_ACTIVE → BASELINE_REVIEW → CANDIDATE_READY → CANDIDATE_ACTIVE → CANDIDATE_REVIEW → COMPLETED.

Дополнительно PAUSED/CANCELLED/ARCHIVED; WAITING_FOR_DATA/INSUFFICIENT_DATA/INCOMPARABLE — состояния результата этапа, не фиктивное завершение эксперимента. Конкретное хранение состояния адаптировать к имеющемуся repository; разрешённые переходы определить таблицей на W03.

- DRAFT/READY не блокирует SKU как фактически активное наблюдение.
- ACTIVE начинается только с подтверждения цены/времени и фиксации exact plan/tariff/cost revision.
- Finish означает остановку сбора в рамках плана, не финализацию финансов Ozon.
- Возобновление после паузы/смены условий создаёт новый phase segment с новым подтверждением; нельзя склеить непоследовательные дни.
- Cancel/archive не удаляет evidence/results. Повтор callback идемпотентен; stale version не меняет текущий этап.
- Изменение control flags после расчёта сохраняется как новая metadata/result revision; прошлое evidence не переписывается.

### 8.3. Временные правила

- По умолчанию 7 полностью завершённых локальных дней на фазу; это операционный шаблон, не доказательство статистической достаточности.
- Поддержать плановое окно 3–28 дней; collection может использовать существующий максимум 56 дней. Окно не растягивается скрыто ради получения желаемого результата.
- Если фактическая смена была внутри дня, первая полная дата фазы — следующий локальный день. При наличии доказанных per-sale timestamps можно реализовать отдельный точный режим, но не агрегаты целого дня.
- Baseline и candidate по умолчанию равной длины и с одинаковым покрытием дней недели; различие даёт причину/предупреждение quality gate.
- Прошлое окно можно связать как baseline только при совпадении scope, evidence basis, объявленной цены и условий. Оно не становится случайно контролируемым A/B-тестом.
- Maturity/as_of хранить отдельно от elapsed days. Начальная минимальная задержка 7 завершённых дней после конца окна — осторожное модельное правило, а не обещанный срок всех возвратов. До неё нет рекомендации превосходства по строгой retained-модели.
- Новые возвраты/корректировки дают новую revision с датой as_of. Предыдущее заключение сохраняется и помечается как основанное на прежней версии.

### 8.4. Выбор следующей цены

Приоритет — максимум ₽/unit только среди заданных и пригодных вариантов. Бот помогает сформировать 2–10 кандидатов:

- явные границы допустимой цены от владельца;
- текущая цена, соседние цены/границы тарифов ±0,01 ₽ в подтверждённой области;
- существующая сетка/target solver и рекламные пороги компенсации;
- запас до убытка и cost completeness.

Не вводить default «падение цены улучшит ДРР». Будущая реклама — сценарий; наблюдённая реклама — evidence своего окна. Без модели реакции спроса нельзя гарантировать глобальный максимум или будущий объём.

Если комиссия/расход кандидата неизвестны, предложить существующий ручной tariff path или показать unavailable строку. Не выбирать её лучшей по пропущенному расходу.

### 8.5. Условия и качество

Фиксировать для каждой фазы: seller price, currency/schema, tariff profile/effective dates, cost/discount/tax/reference-loss revisions, ad budget/rate basis, inventory availability, акции/изменения карточки/кампаний, источник и статус каждого условия.

Сведения об акциях/карточке, не получаемые из подтверждённого источника, можно собрать короткими owner flags (изменялись/не изменялись/не знаю). «Не знаю» сохраняется неизвестным. Не требовать API JSON/Excel для обычного flow.

Quality gate должен различать:

- неполноту и несовместимость, которые блокируют ranking;
- малую выборку/неподтверждённую цену/сезонность, которые ограничивают модель;
- сопоставимые по явно одинаковым допущениям модели;
- фактические денежные показатели окна без доказательства ценового эффекта.

Для рекомендации по полному режиму нужны один cost_scope/calculation version, одинаковое основание рекламных расходов и quantity, применимые tariff rules, отсутствие пересечений окон, сопоставимый maturity/as_of и достаточное покрытие. Разные постоянные допущения не маскировать одной подписью.

Минимум 30 пригодных единиц на фазу — начальный operational small-sample gate. Он не означает «95% достоверность». При агрегатах без распределения наблюдений нельзя вычислять p-value/confidence interval из количества и средней прибыли. Недоступная статистическая уверенность так и показывается.

### 8.6. Рекомендация

Выводить один из понятных исходов:

- CONTINUE_COLLECTING — окно/выборка/созревание недостаточны;
- FIX_DATA_OR_CONDITIONS — устранить конкретную проблему;
- NO_CLEAR_DIFFERENCE — округлённая прибыль равна/разница меньше заранее заданного порога;
- CANDIDATE_BETTER_IN_MODEL — кандидат лучше по сопоставимой модели;
- BASELINE_BETTER_IN_MODEL — исходный вариант лучше;
- INCOMPARABLE — однозначное основание для несопоставимости.

Значимый порог владелец может задать до начала сравнения в RUB/unit; default 0,01 ₽ — технический порог различия после округления, не бизнес/статистическая значимость. После просмотра результата изменение порога создаёт новую revision и явно показывается.

Сравнивать округлённые Decimal прибыли: abs(delta) ниже порога или delta=0 даёт NO_CLEAR_DIFFERENCE; abs(delta) не меньше положительного порога допускает направление улучшения только после остальных quality gates.

Всегда показывать baseline/candidate ₽/unit, абсолютную дельту, состав расходов, Q и период/as_of, причины/ограничения и следующий шаг. Процент улучшения только при положительной ненулевой базе; отрицательная/нулевая база получает абсолютную разницу.

Совет относится к наблюдённым условиям и выбранным кандидатам. Недоказанный вывод «цена вызвала снижение ДРР» запрещён. Пользователь может отметить, какое решение принял; запись не меняет цену Ozon.

## 9. Хранение и обратная совместимость

W17 проектирует additive schema поверх PlanningWorkspaceRepository (на базе задания DB version 5; перепроверить на старте). Допустимы новые experiment/phase/evidence references и новые версии result/payload, если старые readers сохранены.

Требования:

- owner/store/exact SKU/scheme во всех запросах и foreign-key/uniqueness guards;
- plan revision, cost snapshot, tariff revision, observation/result revision immutable;
- отдельные state revision и result revision, CAS, idempotency with payload hash;
- raw evidence transient; persisted projections строго allowlisted/size bounded;
- атомарность experiment → phase → observation links и rollback при любой ошибке;
- пагинация без потери/повтора; bounded quotas с понятным limit status;
- архивирование сохраняет историю; восстановление не делает эксперимент активным без нового owner confirm;
- старые plan schemas/result versions читаются без пересчёта и автодобавления расходов;
- future/unsupported/corrupt version закрывается безопасной ошибкой.

Определить разумные quotas: по умолчанию не более 100 экспериментов на магазин, 10 фаз на эксперимент, 20 result revisions на фазу; общий existing storage cap имеет приоритет. Пределы и поведение при их достижении покрыть тестами. Не удалять историю молча.

## 10. Надёжность и удобство

- Сбор запускается явным действием. Один общий PeriodProfitOperationTrace на операцию и все финансовые/Returns/Performance/Seller источники.
- Начальный верхний потолок — 120 секунд и 128 фактических HTTP попыток; более строгий существующий parent budget имеет приоритет. Retries/пагинация входят в этот счётчик.
- Search budgets сохраняются; новый режим не возвращает скрытый обход ограничений через дополнительный solver или side calculator.
- Повтор кнопки во время работы не запускает второй сбор. После timeout/429 доступен явный bounded retry.
- Смена магазина, SKU, phase/version или нового черновика делает старый callback устаревшим. Поздний ответ не затирает более новое состояние.
- Screen/detail/export читают один exact snapshot; навигация/скачивание не обновляют источник.
- Компактный экран по умолчанию, подробности кнопкой. Использовать существующий UTF-16 splitter для длинных сообщений, не обрезать отчёт.
- Числа с разделителями тысяч, суммы/дельты в ₽/unit, denominator/date bases доступны в подробностях.
- Существующие backup/restore и Windows update/start/status/stop остаются совместимыми; отдельный сервис для инфраструктуры не нужен.

## 11. Этапы и зависимости

Каждый этап завершается работающим результатом и проверками, а не только созданием файла. Названия новых сервисов/tests в таблице — ответственность; точные файлы выбрать на W03 и записать в журнал.

### Модуль A — основа, источник истины и контракты

| Этап | Зависит | Конкретная работа | Приёмка / evidence |
|---|---|---|---|
| W00 | — | Подтвердить merged main/PR, read-only status, чистую/сохранённую базу; создать implementation branch; зафиксировать изоляцию данных | HEAD/base/dirty inventory, baseline manifest, журнал; owner files не включены в commit |
| W01 | W00 | Проследить public routes и data lineage для base costs, ads, returns, storage, quantities, observation | Матрица поле → источник → дата → scope → completeness → consumer; ни одному aggregate не присвоена более сильная семантика |
| W02 | W01 | Подтвердить официальные контракты необходимых источников; новые API только если имеющихся недостаточно | Endpoint/version/fields/page/limits/date evidence; неподтверждённые возможности перечислены как unsupported; без live credentials |
| W03 | W01,W02 | Зафиксировать versioned expense/quantity/experiment contracts, ownership и state transition table; подготовить целевые fixtures | Architecture note, signatures, migration plan, finite quotas, разрешённые переходы, gate matrix; без competing engine |
| W04 | W03 | Собрать независимые numeric oracles и baseline связанных старых tests | Примеры N01–N18 вычислены; проверены старые scenario/target/tax/returns/planning suites; не считать будущие тесты выполненными |

### Модуль B — доказательства дополнительных расходов

| Этап | Зависит | Конкретная работа | Приёмка / evidence |
|---|---|---|---|
| W05 | W03,W04 | Pure normalization signed operations/subcomponents, dedup/conflict, exact identity, coverage ledger | Повтор, конфликт, multi-service operation, same IDs across stores, partial pages; N03,N04,N12 |
| W06 | W05 | Согласовать financial ads primary и Performance reconciliation, типы рекламы и absolute RUB/unit | CPC overlap считается один раз; CPO/other только подтверждённые, account-level остаётся отдельно; N01,N05 |
| W07 | W05 | Разобрать return/non-buyout components и привязку quantity/cohort; отдельно inventory loss/recovery/compensation | Не использовать net posting total/average; pending COGS не ноль; quantity mismatch блокирует strict mode; N02,N06 |
| W08 | W05 | Подключить storage/placement и поддержанные дополнительные услуги с disjoint mapping | SKU есть/нет, нулевая сумма vs missing, base overlap, one-off credit; N04,N07 |
| W09 | W06,W07,W08 | Собрать bounded 56-completed-day reference snapshot и отдельный phase-window snapshot | Weighted numerator/denominator, date/timezone/coverage, reference vs observed scope, budget/429; N08,N12 |
| W10 | W09 | Публичная read-only проекция полноты и применимости компонентов | Included/excluded/unknown, источник, суммы/единицы и причина; zero не подменяет unknown, navigation не делает API calls |

### Модуль C — единый расширенный расчёт

| Этап | Зависит | Конкретная работа | Приёмка / evidence |
|---|---|---|---|
| W11 | W03,W10 | Аддитивно расширить canonical forward компонентами/mode/scope; сохранить legacy behaviour | Ровно один расчёт суммы и rounding; отсутствующий новый contract читает legacy; N01,N09 |
| W12 | W07,W11 | Реализовать strict retained gate и отдельно window allocation; потери/незавершённые исходы | Q0/negative/multi-unit/wrong cohort/inventory unknown; no unsupported full label; N02,N06,N08 |
| W13 | W11,W12 | Передавать расширенный gross profit в existing TaxService, проверить минимум и баллы | NONE/USN income/income-minus-expenses, group tax once, no after-tax subtraction; N09,N10 |
| W14 | W06,W11 | Завершить absolute/percent advertising и frozen policy при смене цены | RUB/unit выше цены допустим, percent bounded, no silent conversion; N05,N11 |
| W15 | W13,W14 | Обновить target/break-even/ad compensation/grid search и их guard/envelope | Тарифные разрывы, копеечная минимальность, exhausted budget и retry новой цели; N11,N13 |
| W16 | W15 | Пронести тот же режим через sensitivity/batch/mix/saved-plan capture и comparison | Таблица consumer parity; canonical amounts совпадают, expense pool и налог не повторяются; N10,N14 |

### Модуль D — сохранение evidence и версий

| Этап | Зависит | Конкретная работа | Приёмка / evidence |
|---|---|---|---|
| W17 | W03,W10 | Реализовать additive repository schema для expense snapshot/experiment/phase references | Миграции из поддержанных версий, CAS/idempotency, invalid/future versions, quota и transactional rollback; N14,N15 |
| W18 | W16,W17 | Сохранять exact calculation/cost/tariff/quantity versions и открывать без I/O | Старые планы и results неизменны; refresh создаёт revision; copy/restore exact scope; N14 |
| W19 | W18 | Пронести новый cost basis в observation result/quality/ranking signatures | Отличающиеся допущения и scopes не сравниваются; confirmed/manual origin корректен; N16 |
| W20 | W19 | Detail/export snapshot projection для экономики, coverage и границ модели | Screen/export amounts/statuses/revisions совпадают, no source reload, privacy/size; N15 |

### Модуль E — предметный процесс эксперимента

| Этап | Зависит | Конкретная работа | Приёмка / evidence |
|---|---|---|---|
| W21 | W17,W19 | Pure state machine и atomic application transitions; общий active-SKU guard с наблюдениями | Все разрешённые/запрещённые переходы, replay, same/other store, interleavings; N15,N17 |
| W22 | W16,W21 | План baseline, metric/scope, price bounds, duration, maturity и fixed decision threshold | Неполный draft сохраняется; impossible input не активирует experiment; target остаётся RUB/unit |
| W23 | W22 | Выбор 2–10 candidate prices через существующие grid/tariff/compensation инструменты | Boundary ±cent, gaps, constraints, ties, no price-demand prediction; N11,N13 |
| W24 | W22,W23 | Preview и owner-confirm фактической цены/времени; связать exact plan/observation | Midday → next full local day, future time/replay/stale rejected; past evidence не становится API proof; N17 |
| W25 | W24 | Запись/обновление control flags, pause/resume сегментов без переписывания evidence | Акции/ad/stock/cost/tariff/unknown, incompatible changes получают reason; old phase immutable |
| W26 | W24,W25 | Сбор completed phase window через shared trace и existing collectors + new cost evidence | Partial/time limit/cancel/late response; нет auto-loop/фонового retry; same snapshot/result revision; N12,N17 |
| W27 | W26 | Maturity/quantity/price/source coverage gates и повторная revision после поздних фактов | 7-day operational delay и 30-unit gate, Q0 и late returns, mixed prices, timezones; N08,N16 |
| W28 | W20,W27 | Сравнение baseline/candidate, ₽/unit delta, tie/threshold, confounder policy | Только compatible modes; negative/zero base без misleading percent; no fake confidence/causality; N16,N18 |
| W29 | W28 | Объяснимая recommendation и следующий шаг; record owner decision | Все outcomes раздела 8.6, максимум только среди оценённых кандидатов; decision не вызывает Ozon mutation |

### Модуль F — законченный пользовательский инструмент

| Этап | Зависит | Конкретная работа | Приёмка / evidence |
|---|---|---|---|
| W30 | W10,W18 | Guided Telegram new economics: scope, detail, missing data actions | Пользователь видит базовый/расширенный режим и различие, manual tariff route возвращает в нужный draft |
| W31 | W24,W25,W30 | Guided experiment wizard от SKU до активной baseline/candidate фазы | Public menu/callback/text, edit/back/cancel, store switch, exact draft ownership, no API JSON requirement |
| W32 | W29,W31 | Экраны результата, рекомендаций и причин; history/revisions/reopen | Restart, stale callbacks, late completion, safe retry, next step reachable; compact text + splitter |
| W33 | W20,W32 | Экспорт experiment/phase/result и сравнения, связь с saved plans | Точный historical snapshot, hashes/versions, all rows, permissions, quotas; N14,N15 |
| W34 | W33 | Руководство владельца и шаги приёмки одного SKU; runbook missing/partial/corrected sources | Инструкция соответствует actual buttons; без ключей/платных обязательных источников; пример полностью воспроизводим offline |

### Модуль G — сквозная надёжность

| Этап | Зависит | Конкретная работа | Приёмка / evidence |
|---|---|---|---|
| W35 | W34 | Сквозные public-route numerical cases и сопоставимость всех consumers | N01–N18, основной путь и каждый conservative fallback; новое поведение проверено assertion значений, не только статуса |
| W36 | W35 | Bounded concurrency/failure/memory/quotas, privacy и shared operation budgets | Parallel confirm/collect/edit/archive, rate-limit/time/cancel/oversize; fixed-seed finite soak без многократного full pytest |
| W37 | W36 | Backup/restore/migration в новый synthetic root; reopen после restart | Tariff/plan/cost/experiment/phase/results/history восстановлены; tenant isolation, corrupted/future versions fail closed |

### Модуль H — завершение и передача

| Этап | Зависит | Конкретная работа | Приёмка / evidence |
|---|---|---|---|
| W38 | W37 | Изолированный полный pytest, compileall, diff/data checks и CI нового HEAD | Windows/Linux штатный Verify, Docker по действующему workflow; точные команды/SHA/result, никаких переносов старого зелёного CI |
| W39 | W38 | Self-review, ready PRs и independent review handoff | Закрыты подтверждённые findings, опубликованы PR+deps+SHA+CI, актуальные docs/journal, owner validation pending отделён от engineering readiness |

Предложенная интеграция: PR foundation/contracts; expense normalization + extended forward; persistence/consumer integration; experiment workflow; Telegram + acceptance. При необходимости укрупнить/разделить по reviewability, но не выпускать автономные дубли двигателей. Для stacked PR явно указывать base, зависимости и порядок слияния.

## 12. Числовая и поведенческая приёмка N01–N18

Все числа ниже synthetic. Налоговые ставки в примерах проверяют существующий алгоритм, не задают новые defaults.

| Код | Вход / ситуация | Обязательный результат |
|---|---|---|
| N01 | P=100, C=20, commission=10%, delivery=5, last mile=1, acquiring=1, ads total=1200 на 100 совместимых единиц, extra expense=5/unit, tax NONE | Ads=12, commission=10, profit_before_tax=46, profit=46. Performance CPC=1000 той же рекламы не добавляет ещё 10/unit |
| N02 | Одна точная когорта: delivered=110, подтверждённых возвращённых единиц из неё=10, retained=100; return fees=200, non-buyout fees=100, irrecoverable cost=60, связанная компенсация=10 | Loss pool=350, loss/unit=3.50. Storage=150 той же модели → 1.50/unit. Общее extra=5.00. Gross refund выручки не является ещё одним расходом |
| N03 | Операция A имеет услуги x=-30,y=-20; A повторена без изменения, операция B=-10 | Expense=60, count разных услуг=3. A с изменённым x — CONFLICT; разные store не dedup друг с другом |
| N04 | Charges=-300, связанные corrections=+50 | Signed finance=-250, expense=250. Net credit сохраняется signed; one-off credit не становится отрицательной recurring rate по умолчанию |
| N05 | CPC=-1000, other proven ad=-200, Performance=1000; отдельная общая кампания=-300 без SKU. Отдельный absolute сценарий N01 с рекламой 120/unit | SKU primary=1200, не 2200/2500; общая кампания отдельно. Missing other ads отличается от полного нуля. Absolute120 при P100 даёт profit=-62, а не ошибку ставки >100% |
| N06 | Returned merchandise SALEABLE_RESTORED; pending disposition; другой вариант confirmed irrecoverable COGS | Восстановленная стоимость не списана; pending — unknown exposure; irrecoverable включается один раз и не создаёт Return COGS commit |
| N07 | Размещение -1.74 доказано по SKU; часть fees уже входит в base logistics; account storage без SKU | SKU storage пригодно как явно выбранный allocation; base overlap заблокирован; account storage не делится по продажам автоматически |
| N08 | Суммы 100/10 units и 100/100 units | Weighted=200/110, не среднее 10 и 1. Q=0 → unit unknown. Возвраты другого окна не уменьшают denominator. Partial pages не дают complete |
| N09 | N01, USN_INCOME=6%, points=0 | Tax=6.00, profit=40.00; при points=20 taxable revenue=80, tax=4.80, profit=41.20 по текущей политике |
| N10 | N01, USN_INCOME_MINUS_EXPENSES=15%, minimum=1% | Gross profit=46, tax=6.90, profit=39.10; не 38.35 от вычитания extra после старого налога. В mix общий TaxService вызван один раз |
| N11 | N01 baseline P100 ads12; candidate P95 ads7, прочие costs и tariff10% те же | Candidate commission=9.50, profit=46.50, delta=+0.50/unit. Это модельное улучшение; постоянная ставка не переносится через неподтверждённую тарифную границу |
| N12 | Общий parent лимит, HTTP retries/pagination/429; один источник исчерпал время | Оставшиеся источники не обходят лимит; результат partial и safe explicit retry; исходные API attempt counters не обнуляются |
| N13 | Сетка возле тарифной границы, копеечные toggles, unknown gap и per-row/shared search exhaustion | Проверка direct canonical и минимальности; нет global optimum claim; новая цель может повторить bounded exhausted row |
| N14 | Старый saved-plan/result, новый полный mode, изменение cost/tariff reference и повторное открытие | Старый результат неизменен; новая revision/explicit refresh; single/batch/mix/sensitivity/export используют один cost scope |
| N15 | Cross-store/SKU callbacks, duplicate confirm, replay с новым payload, failed transaction, oversized record | Fail closed, один переход/запись, rollback, quota status; raw IDs/API secrets отсутствуют в persisted/exported planning data |
| N16 | Разные denominator/date/ad/cost/maturity policies; окна пересекаются; малая выборка | Incomparable либо явный insufficient; несовместимые модели не ранжируются; 30 units/7 дней не дают выдуманную статистическую уверенность |
| N17 | Цена подтверждена 12:00 local; окно содержит незавершённый день; switch store/new draft while collect in flight | Фаза начинается со следующего полного дня; незавершённое окно запрещено; поздний ответ не изменяет новый draft/store |
| N18 | Прибыль baseline 46,candidate46.50; tie после округления; base0/negative; стоимость/реклама поменялась между фазами | Дельта +0.50 и корректное ограниченное объяснение; ties не объявляются победой; percent только при positive base; changed conditions получают reason |

W04 должен хранить проверяемый oracle input/output для каждого случая. W35 добавляет сценарии восстановления из incomplete в available, финансовой корректировки после рекомендации, нескольких единиц в отправлении и rollback частично начатой фазы.

## 13. Проверки и изоляция данных

Базовый профиль переиспользовать, не заменяя его будущими mock-only тестами:

- tests/test_unit_price_scenario_service.py;
- tests/test_unit_price_target_planning_service.py;
- tests/test_unit_price_advertising_cap_service.py;
- tests/test_unit_price_sensitivity_service.py;
- tests/test_unit_price_batch_plan_service.py;
- tests/test_unit_price_tariff_snapshot_adapter.py;
- tests/test_unit_price_scenario_telegram_runtime.py;
- tests/test_telegram_unit_price_observation_runtime.py;
- tests/test_unit_price_observation_collection_service.py;
- tests/test_unit_price_observation_normalizer.py;
- tests/test_unit_price_observation_result_service.py;
- tests/test_unit_price_observation_quality_service.py;
- tests/test_unit_price_recommendation_ranking_service.py;
- tests/test_unit_price_profit_per_unit_end_to_end.py;
- tests/test_returns_finance_attribution_facts_source.py;
- tests/test_returns_finance_attribution_analytics_service.py;
- tests/test_period_profit_sku_advertising.py;
- tests/test_sales_mix_planning_service.py;
- tests/test_planning_workspace_repository.py;
- tests/test_unit_price_backup_restore.py;
- tests/test_discount_points_tax_end_to_end.py;
- tests/test_analytics_export_service.py.

Новые тесты должны проверять деньги/quantity/state/privacy/actual calls и реальные границы интеграции. Не писать регрессии, которые просто повторяют implementation branch или утверждают собственный fake output. Сложный числовой случай проверять через canonical forward и независимый small-domain brute-force oracle.

Для file-backed tests: новая synthetic storage root/basetemp; PYTHON_DOTENV_DISABLED=1, plugin autoload и credential environment отключены. Не читать .env/owner DB, не печатать secrets. Полный pytest выполнять в disposable checkout/worktree, поскольку существующий suite может писать tracked data/tasks.json и data/users.json. Сохранить hashes/status исходного checkout до/после, не восстанавливать поверх owner data тестовые файлы.

CI — штатный .github/workflows/verify.yml. Если обязательная проверка не запущена/не прошла, этап остаётся incomplete с точной причиной. Не обходить guard, skip/deselect или ослаблять assertions ради зелёного результата.

## 14. Финальные артефакты и Definition of Done

В review handoff обязательны:

- PR URL, base/dependencies, code SHA и последний PR HEAD, CI run URLs с привязкой к SHA;
- карта новых/изменённых файлов и архитектурное влияние;
- contract/version/migration и allowed transitions;
- source audit: что действительно получено, что ограничено и почему;
- numerical acceptance N01–N18 с фактическими результатами;
- consumer parity и full pytest/compile/diff/data safety;
- backup/restore и privacy evidence;
- шаги владельца для проверки одного SKU; runtime evidence pending отдельно;
- оставшиеся ограничения, риск неполных источников и отсутствие причинной гарантии;
- независимый review checklist, без заявления «всё готово» только по self-review.

Программа завершена, когда:

1. Расширенная модель добавляет каждую доказанную категорию ровно один раз; unknown/credit/correction/zero различаются.
2. Налог и все ценовые consumers используют один canonical contract, без нарушений legacy и immutable history.
3. Ценовой эксперимент проходит весь public flow, переносит правильные frozen revisions и выдаёт только обоснованный следующий шаг.
4. Модель доступна в подтверждённой области, а недоступные источники имеют законченный рабочий UX.
5. Новые тесты, полный изолированный pytest и CI последнего HEAD зелёные, owner data сохранены.
6. Ready PRs и independent review package опубликованы; merge/deploy/live bot не выполнялись.

Если реальный источник не позволяет подтвердить retained cohort или полный SKU ad/storage scope, обязательный результат — корректный ограниченный режим, причины и удобный путь обновления. Запрещено ради формального закрытия программы объявлять window allocation фактом, вводить вручную «успешные продажи» или повторно вычитать account totals.

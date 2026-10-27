# Рейтинг цены по прибыли на единицу (Q22)

Дата: 27.10.2026  
Статус: VERIFIED  
Классификация: Architecture Review Required

## Что сравнивается

Плановые сценарии и наблюдения остаются разными основаниями.

- Плановые варианты используют существующий `UnitPriceTargetPlanningService`, ярлык `SCENARIO_ASSUMPTIONS` и выбранные пользователем входы. Сетка показывает максимум только среди доступных проверенных цен, не глобальный максимум. В равных сценариях отображаются все лидеры.
- Наблюдения оцениваются новым `UnitPriceRecommendationRankingService`. До ранжирования обязательно проходит `UnitPriceObservationQualityService` Q21. Если весь набор не `COMPARABLE`, список победителей пуст — частичного ранжирования нет.
- Для `CANONICAL_FACT_COMPARABLE` берётся только `observed_profit_per_unit`; для `MODELLED_FROM_OBSERVED_INPUTS` — только `profit_per_unit`. Модель остаётся `verified=false` и не называется фактической прибылью.

Цель ранжирования — прибыль в рублях на одну успешную продажу. Число заказов/успешных единиц не умножает и не перевзвешивает прибыль. Сумма по периоду не становится скрытым критерием.

## Telegram flow и границы данных

На карточке наблюдения с сохранённым результатом и в детализации результата доступна кнопка «Сравнить прибыль по наблюдениям SKU». Рейтинг scoped к текущему owner/store и точной identity product/offer/SKU/FBO. Он читает локальные observation records, append-only result revisions и точные сохранённые версии исходных планов. Сетка цены, Ozon API, collection runtime и live bot не вызываются.

Для каждой отличающейся seller price выбирается её последний сохранённый результат. Повторные наблюдения той же цены не создают дублирующий ценовой вариант. Сравниваются не более 10 последних уникальных цен; количество не включённых из-за лимита показывается пользователю. Кандидаты отображаются от самого раннего окна; оно служит базовым периодом для разницы. Разные frozen inputs, окна, источники, basis или scope блокируют рекомендацию через Q21.

Вывод показывает цену продавца, прибыль ₽/шт., разницу ₽/шт. к базовому окну и процент только при положительной базовой прибыли. Округление прибыли до копеек использует `ROUND_HALF_UP`; совпадающие округлённые максимумы объявляются равными. При нулевой или отрицательной базе денежная разница остаётся, процент не вычисляется. Пояснение всегда ограничивает вывод проверенными вариантами и не утверждает, что изменение вызвано только ценой.

В рейтинговом payload нет owner/store/product/SKU raw identity или operation IDs. UI показывает SKU текущей карточки, уже известный владельцу. Assessment Q21 остаётся доступным для диагностики причин/предупреждений. Внешние записи и цены не меняются.

## Изменённые файлы

- `app/services/unit_price_recommendation_ranking_service.py` — новый pure ranking по ₽/шт. после quality gate, tie handling, delta и процентное правило.
- `app/services/unit_price_observation_ranking_service.py` — owner/store-scoped чтение результатов и exact frozen plan revision, подпись допущений сценария, выбор последней записи на цену и bounded candidate selection.
- `app/services/telegram_unit_price_observation_runtime_service.py` — callback, компактный result text и stale-ответ после переключения магазина.
- `tests/test_unit_price_recommendation_ranking_service.py` — ranking regression matrix.
- `tests/test_telegram_unit_price_observation_runtime.py` — persisted-result, tenant/SKU path, absence of source calls, assumption mismatch and cross-store callback regressions.
- `project_brain/LUNA_PRICE_PROFIT_PER_UNIT_PROGRESS_2026-10-26.md`, `CURRENT_STATE.md`, `TEST_MAP.md`, `CHANGELOG.md` — фактический этап и профиль.

`DECISIONS.md` не менялся: Q03/Q15/Q21 уже задают evidence labels, цель ₽/шт., quality gates и запрет причинных выводов. Storage schema, Ozon contracts, result schema и формула unit-profit не менялись.

## Проверки

- Адресный Windows/Python 3.12 профиль после выделения local comparison application service: **26 passed in 1.42s**.
- Связанный Windows/Python 3.12 Q16–Q22 профиль на 16 targets: **274 passed in 5.68s**. Включает repository, collector, normalizer, result/quality/ranking, Telegram runtime, finance/Performance guards, factory и всю существующую target-planning test module.
- Проверки выполнялись на synthetic evidence, в уникальных TEMP storage/basetemp; plugin autoload/dotenv отключены, имена provider credentials удалены из среды. Owner DB, `.env`, Ozon/Telegram API, tracked `data/*.json` и реальный бот не использовались.
- Полный `pytest`, Linux/Windows exact-head CI и Docker workflow запланированы в Q33–Q35.

## Ограничения

Текущие источники часто не подтверждают фактическую прибыль на продажу; тогда пользователь может получить модельное сравнение лишь при успешном Q21 gate. В нём использован CPC-only расход и владелец подтверждает цену вручную. Это модель при замороженных допущениях, не измеренный эффект цены, статистическая уверенность или гарантия будущего результата. Внешняя валидация конкретного магазина не выполнялась.

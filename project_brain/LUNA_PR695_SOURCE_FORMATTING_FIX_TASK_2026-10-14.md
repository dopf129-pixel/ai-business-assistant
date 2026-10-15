# ТЗ для GPT Luna — R10: безопасное отображение значений источника в PR #695

Дата: 14.10.2026. Статус: **X00–X03 завершены. R10 исправлен, локальные проверки и exact-head CI зелёные, repeat review без новых blockers. Слияние проведёт другая модель**.

## Цель и исходная ревизия

Закрыть остаточный путь R5: неподдерживаемая денежная величина из существующего источника должна оставлять калькулятор доступным для ручного исправления, а не вызывать generic callback/text error без кнопок.

- PR: https://github.com/dopf129-pixel/ai-business-assistant/pull/695.
- Ветка: `codex/unit-price-calculator`.
- Проверенный head: `060b0e6e57e3fc5e3ba28c42d90a4adcd4f03f6d`; production code совпадает с `9ed3e2d9bee334b54b874f63493f69dc4197d15f`.
- Exact-head Verify `38621806447`: Windows/Linux full suite, compile, Docker build/smoke — success. Повторный targeted calculator set: **48 passed in 1.16s**. Новый случай в штатном наборе отсутствует.
- Review evidence: `ARCHITECTURE_REVIEW_PR695_2026-10-14.md`, раздел R10.

## Подтверждённый дефект

Действующие `TelegramSellerCostUpdateService._cost` и `SellerCostTableService._cost` принимают конечную положительную себестоимость `1e100`. Воспроизведение не сохраняло её в реальную БД: fake cost getter возвращал такую уже сохранённую запись.

Production source принимает эту стоимость в `_load_cost` / `_nonnegative_number`. Math service корректно признаёт её недопустимой, но runtime форматирует исходный `session.inputs.cost` через `_money`. `number.quantize(Decimal("0.01"))` в строке 1034 текущего runtime вызывает `decimal.InvalidOperation`.

При публичном выборе товара handler возвращает `UNIT_PRICE_SCENARIO_CALLBACK_FAILED` без keyboard и без scenario result. Следующий текст возвращает `UNIT_PRICE_SCENARIO_TEXT_FAILED` без keyboard. Пользователь не может исправить стоимость кнопками калькулятора. Аналогичная граница существует для неподдерживаемой seller price из источника.

## Ограничения

Прочитать AGENTS.md, CURRENT_STATE, DECISIONS, TEST_MAP, feature task и оба предыдущих corrective tasks. Сначала проверить актуальный head/diff. Сохранить все существующие пользовательские data-файлы, БД, credentials, locks и временные каталоги; не выполнять широкий restore/reset/clean/stash и не включать их в fixtures или commits.

Не менять бизнес-формулу, TaxService, пределы и интерфейсы сохранения себестоимости, реальные цены/стоимость/налоговые настройки. Не вводить коммерческий максимум цены или стоимости. Использовать уже существующую техническую границу калькулятора; unsupported source value не становится нулём. R8 precision для bounded rates, R9 cache age/TTL, callbacks/tickets/store isolation, source budgets и Decision 045 сохранить. Live Ozon, merge и production restart не требуются.

## X00 — baseline и красные регрессии

Добавить meaningful source → math → runtime → handler regressions в штатные calculator modules. Использовать fake catalog/current facts/cost/tax/finance и injected clocks, без пользовательского storage и API. До исправления подтвердить неправильное поведение.

1. Реальный `UnitPriceScenarioSource`, cost getter возвращает `1e100`, seller price 500 и commission 15%. Выбрать SKU публичным picker/callback. Ожидание: normal input-required result и working keyboard; unsupported cost обозначена как invalid/unknown; прибыль unavailable. Generic callback/text exception неприемлем.
2. В полученном сценарии публично изменить cost на 120, ввести L/M/E=0 и advertising=0; при полном weighted source итог available=True. Stored cost source не меняется; отображение edit prompt тоже безопасно.
3. Аналогично проверить unsupported source seller price и успешный ручной ввод 500. Нельзя скрывать дефект только предварительным изменением persisted inputs.

**Фактический результат:** добавлены оба публичных интеграционных сценария в `tests/test_unit_price_scenario_repeat_review_regressions.py`. До исправления они оба падали, потому что handler возвращал `UNIT_PRICE_SCENARIO_CALLBACK_FAILED` без keyboard. Данные и HTTP не затрагивались.

## X01 — узкое исправление

- Обеспечить безопасное отображение в `_format_result`, `_edit_prompt`, `_money` и `_percent` независимо от того, что math service уже отклонил raw source input. Неподдерживаемый Decimal не должен дойти до unhandled quantize/overflow.
- Можно согласовать source normalization с существующим техническим validation contract. Если источник превращён в unknown, completeness и provenance должны соответствовать фактической недоступности, а не обещать подтверждённую стоимость.
- Не терять working keyboard и возможность manual scenario override. Unknown/invalid source не считается нулём и не разрешает итоговую прибыль до заполнения необходимых полей.
- Не создавать новый слой и не переписывать источники либо seller-cost persistence. Изменять только подтверждённый путь отображения/валидации калькулятора.

**Фактический результат:** `_nonnegative_number` в source применяет тот же технический precision/magnitude contract, что math service; недопустимые seller price/cost выходят как unknown. `cost_as_of` не выставляется при неизвестной стоимости. `_money` и `_percent` проверяют отображаемый диапазон и ловят Decimal formatting errors; unknown показывается как «не задано». Локальное исправление не меняет формулу и seller-cost persistence.

## X02 — проверки

Новые regressions, пять calculator modules, смежные handler/factory/tax проверки. Existing explicit zero, localized input, invalid manual retry, extreme precision/magnitude, non-finite tax output, 28-digit automatic rates и freshness/refresh tests должны оставаться зелёными.

**Фактический результат:** calculator/source/math/runtime/architecture/UI/request-bound-tax-policy selection — **59 passed in 1.51s**. Полный изолированный Windows pytest без seller data/.env — **3 144 passed in 16.17s**; два production-policy tests получили синтетический default tax JSON только в копии. `compileall -q app tests` прошёл с одной существующей SyntaxWarning в returns-impact test, `git diff --check` прошёл. Exact PR head `2207ec86ec96012f7911706429fdc1b4dfacde23` прошёл Verify runs **38634572358** и **38634565693**: Windows/Linux full suite, compile, Docker build/runtime smoke. Повторный review R10 завершён без открытых blockers; live Ozon/source/API/credentials не использовались.

## X03 — документация и повторный review

Обновить CHANGELOG, CURRENT_STATE, TEST_MAP, feature task и review; DECISIONS менять только при настоящем новом архитектурном решении. Пройти повторную проверку новой ревизии по R10 и сохранности R1–R9. Слияние выполнит другая модель после приёмки.

| Этап | Статус |
|---|---|
| X00 | Выполнен: 2 meaningful интеграционных regressions; red на старом коде подтверждён |
| X01 | Выполнен локально: source normalization + safe Decimal formatting |
| X02 | Выполнен: targeted 59 passed, full isolated 3 144 passed, compileall/diff check прошли, exact-head Windows/Linux/Docker CI зелёный |
| X03 | Выполнен: документация обновлена, repeat review R10 без открытых blockers; слияние другой моделью |

Бизнес-решение для этого исправления не требуется.

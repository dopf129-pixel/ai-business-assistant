# ТЗ для GPT Luna — R11: неразрешённый SKU в источнике среднего баллов

Дата: 15.10.2026. Статус: **код и локальные регрессии выполнены; ожидаются новый CI и повторный review**.

## Цель и исходная ревизия

PR #695, ветка `codex/unit-price-calculator`, проверенный head `9185f65fa75ca0b7dc4d333cc362997209a5cd59`, base `655b3a0c46acb258a5e884cccc8da6728a5216a7`. R1–R10 приняты; их исправления сохранить. Слияние выполнит другая модель после исправления R11, нового CI и повторного review.

В `FinanceService.get_daily_discount_points_evidence` отсутствующий/null/пустой/пробельный SKU продукта превращается в пустую строку и попадает в ветку «другой SKU». Строка исчезает из evidence, `malformed_record_count` остаётся нулевым, день становится complete. Последующая проверка identity в `UnitPriceScenarioSource` уже не видит отброшенную строку.

Контрольный пример: 28 полных ответов дней; в одном дне есть известная продажа выбранного SKU на 100 ₽ с 20 баллами и положительная строка на 900 ₽ без SKU. Сейчас source возвращает автоматические 20% и `complete=true`. Нельзя определить принадлежность второй строки, поэтому по исходному контракту необходимы unknown/incomplete и ручное значение, а не подтверждение 20%.

## Границы

- Сохранить существующие изменения, пользовательские `data/tasks.json`, `data/users.json`, locks и временные каталоги. Не делать общий restore/reset/clean/stash.
- Исправить только новый метод evidence и необходимые regressions. Не менять финансовые итоги, TaxService, формулу, seller-cost persistence, API/DB contracts, callbacks, cache TTL и Decision 045.
- Не угадывать SKU по другим полям и не приписывать неразрешённую строку выбранному товару.
- Известный непустой SKU другого товара по-прежнему исключается из выбранной когорты. Его отсутствие bonus не должно ломать корректную выборку выбранного SKU.
- Не вводить API calls, credentials или пользовательские данные в тесты.

## Y00 — штатная регрессия до изменения кода

В `tests/test_unit_price_scenario_source.py` добавить проверки отсутствующего поля SKU, `None`, пустой и пробельной строки. Использовать fake raw daily response и настоящий `FinanceService.get_daily_discount_points_evidence`; подтвердить incomplete для неразрешённой identity. Сохранить успешный пример с явно другим SKU.

Добавить один интеграционный сценарий в существующий repeat-review module: настоящий FinanceService evidence → UnitPriceScenarioSource → math/runtime/handler, 28 дат, корректная выбранная строка плюс строка без SKU. Ожидать unknown automatic rate, incomplete provenance/source, экран заполнения и отсутствие итоговой прибыли до ручного ввода b. После ручного b и остальных обязательных допущений расчёт должен работать; записи в сохранённые данные нет.

Фактический review probe вне стандартного suite уже дал **3 expected failures in 0.28s** для SKU `None`, `""`, `"   "`: source возвращает `"20"` вместо `None`. Это evidence дефекта, не успешная проверка реализации.

## Y01 — узкое исправление

Перед исключением строки как известного другого SKU различать валидную identity и её отсутствие. Строка POSTING с неразрешённым SKU не должна позволять выставлять `complete=true`. Использовать существующий механизм `malformed`/incomplete; source должен получить неполное evidence и оставить auto-b неизвестным. Не вводить новый parser или слой.

## Y02 — проверки

- Red → green новых штатных regressions, включая manual fallback и явно другой SKU.
- Пять calculator/source/math/runtime/review modules; смежные finance и tax проверки по затронутому пути.
- Полный pytest, compileall, git diff --check и Windows/Linux/Docker CI нового code SHA. Старый зелёный CI не закрывает R11.
- Обновить фактические результаты и ограничения окружения; не записывать предполагаемые результаты как выполненные.

## Y03 — документация и приёмка

Обновить CHANGELOG, CURRENT_STATE, TEST_MAP, исходное feature ТЗ и review. DECISIONS менять только при новом архитектурном решении; здесь оно не требуется. Провести повторный review R11 и сохранности R1–R10. Слияние остаётся другой модели.

| Этап | Статус |
|---|---|
| Y00 | Выполнен: четыре штатных parser regressions добавлены; до фикса они подтвердили malformed identity gap |
| Y01 | Выполнен: неизвестный SKU учитывается как malformed, известный другой SKU остаётся исключённым |
| Y02 | Локальный этап выполнен: целевые шесть модулей **63 passed**; compileall и diff check прошли. Полный suite и CI нового SHA ожидаются |
| Y03 | Локальная документация обновлена; repeat review на опубликованном SHA ожидается |

## Результат реализации — 15.10.2026

- В `FinanceService.get_daily_discount_points_evidence` пустая identity больше не проходит как известный другой товар: она увеличивает `malformed` и делает evidence incomplete. Явно иной непустой SKU всё ещё пропускается до разбора его bonus.
- Parser regressions покрывают отсутствующее поле, null, пустое и пробельное значения, а также контрольный случай другого известного SKU.
- Сквозной regression проходит через FinanceService, weighted source, math, runtime и public Telegram handler: неполная когорта оставляет auto rate неизвестным и расчёт закрытым до ручного fallback; после ввода ручного значения результат снова доступен.
- Локальные проверки: **63 passed in 1.32s**, `compileall -q app tests` success, `git diff --check` success. Полный pytest/CI нового SHA и финальный repeat review ещё не выполнены; они обязательны до передачи PR другой модели на слияние.

Бизнес-решение не требуется: это соблюдение уже принятого контракта unknown identity → unavailable auto estimate.

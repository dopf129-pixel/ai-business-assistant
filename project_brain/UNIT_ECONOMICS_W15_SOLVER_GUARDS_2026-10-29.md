# W15 — решатели, бюджеты и границы поиска

Дата: 29.10.2026
Ветка: `codex/full-unit-economics-experiments-implementation-20261028`
Входной code SHA: `779f45fa` (W14)
Реализация: `16ea05d3 Verify extended unit economics price searches`
Зависимости: W13, W14.
Статус: DONE.

## Изменения

- `UnitPriceTargetPlanningService.solve` и `compare_prices` принимают те же `extended_scenario` и `strict_return_evidence`, что и canonical forward. Target/break-even, тарифный поиск, список вариантов, grid и DRR compensation threshold передают их в `UnitPriceScenarioService.calculate`; strict evidence без extended scenario отклоняется явно.
- Обычный поиск по явно заданной комиссии использует тот же ограниченный тарифный segment solver, что и поиск по frozen tariff. Кандидат проверяется независимым canonical forward; предыдущая копейка должна не достигать цели. Для тарифного разрыва минимальность остаётся scoped к проверенным сегментам, неизвестные пробелы не заполняются.
- Аналитическая верхняя граница теперь включает абсолютную рекламу в ₽/успешную единицу, кросс-докинг, расходы из extended contract или строгой когорты и фиксированные комиссии. Реклама в процентном режиме остаётся наклоном функции. Граница сверяется с canonical forward в начале/середине/конце каждого tariff segment; неизвестная или непостоянная дополнительная сумма закрывает поиск.
- Результаты сравнения и grid expose `additional_unit_expenses`, чтобы проверить включённую canonical сумму. Неизвестный/неполный expense evidence не становится нулём и не создаёт `FOUND`.
- На вызов target solver сохраняется один общий ограниченный budget 128 forward calculations для break-even/target и их independent validation. Сравнение сохраняет общий per-call ceiling 1,024, а DRR compensation — ceiling 64 с тем же callback/budget. Повторный запуск новой цели создаёт новый вызов и budget, не переиспользуя кэш/счётчик прошлой попытки. Фиксированная реклама не получает выдуманный процентный порог компенсации.
- Ценовая сетка остаётся конечным набором введённых/тарифных точек и не заявляет глобальный оптимум.

## Регрессии

- `tests/test_unit_price_target_planning_service.py`: absolute advertising + W11 window expense в target solver; независимые проверки найденной цены и предыдущего цента; tariff segment envelope с extension; grid-to-canonical parity; DRR threshold с тем же дополнительным расходом; incomplete evidence; exhausted budget и повторный запуск; strict return evidence без сценарного контракта.
- `tests/test_unit_economics_return_evidence_service.py`: реальный synthetic W07 retained-cohort resolver проходит через W15 target solver; для возвращённой цены forward подтверждает цель, предыдущая копейка её не достигает, 3.50 ₽ loss применяется один раз.
- Обновлены существующие cents oracles: в двух ранее ошибочно объявленных минимальных ценах solver теперь действительно возвращает первый cent, подтверждённый canonical forward; trailing-zero входы дают одинаковый результат.

## Фактические проверки

Windows, Python 3.12.10, pytest 8.4.2; временные pytest/storage roots. Запускался профиль:

```powershell
python -m pytest tests/test_unit_price_target_planning_service.py tests/test_unit_price_scenario_extended_contract.py tests/test_unit_price_scenario_service.py tests/test_unit_price_advertising_cap_service.py tests/test_unit_price_tariff_snapshot_adapter.py tests/test_unit_economics_return_evidence_service.py -q --tb=short
```

Результат: **168 passed in 1.86s**.
`py_compile` для трёх изменённых Python-модулей: PASS.
`git diff --check`: PASS.
Добавленные строки Python длиной не более 120 символов: PASS.
`git diff -- data`: пустой.

Во время разработки адресный прогон выявил, что recursive interval guard не получал normalised additional expense. Это приводило к лишнему обходу центов и исчерпанию бюджета около корня. Расход передаётся в каждый recursive bound; повторный полный профиль прошёл. Других известных W15 failures нет.

## Ограничения и безопасность

- Тарифная минимальность заявляется только по покрытым frozen-сегментам; gaps, неизвестный source и budget exhaustion остаются unavailable.
- В фиксированной рекламе сравнение работает с заданной суммой за успешную единицу. Процентные DRR-пороги для неё не синтезируются.
- Использованы только synthetic fixtures и локальный canonical calculator. Реальные Ozon-запросы, Telegram, production bot, `.env`, owner database/data не использовались.

## Продолжение

W15 закрыт. Следующий этап — W16: протянуть тот же frozen extended contract в sensitivity, batch, mix и saved-plan capture, доказав canonical parity, единый expense pool и однократный aggregate tax.

# Пакет независимого review: маржа SKU до рекламы

## Закрытие двух P2 повторного review (2026-11-02)

- Сравнение цен больше не теряет самостоятельную before-ad проекцию, когда после рекламная прибыль неизвестна. В Telegram видна прибыль/маржа до рекламы для baseline и кандидатов, причина отсутствия after-ad и подтверждённая комиссия; цены не ранжируются и реклама не считается нулём. Новая публичная regression использует известный тариф 15% и значения 226.00 ₽/шт. для цены 500 ₽ и 266.10 ₽/шт. для цены 550 ₽.
- При валидной strict retained cohort проекции сумма `RETURN_LOSS_STRICT_COHORT` включена. Явное исключение из общего расширенного пула не маркирует эту же strict сумму исключённой, если нет отдельно включённого mapped-компонента. Неизвестные статусы и смешанное включение/исключение mapped-алиасов продолжают давать partial/unknown; добавлена regression этого guard.
- До фикса три новых регрессии падали; после — **3 passed in 0.81s**. Связанный профиль 12 модулей **304 passed in 6.29s**, полный Windows pytest **4,426 passed in 46.21s**, `compileall app tests` и `git diff --check` PASS. `data/tasks.json` восстановлен к baseline SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`, lock отсутствует.
- Кодовый commit `f248237f646a39f141b993d4dc498d3eec039278` опубликован в PR #724 и прошёл exact-head run `41431891843`: Windows **4,426 passed in 108.57s**, Linux **4,426 passed in 26.14s**, Docker build/smoke PASS. Artifact `13133939194`, digest `sha256:66889d7a950792c334004978dae7380f8b1db7246159a9e13fa2311e15b755a4`.
- Документационный follow-up SHA `509af1fafc4e61d0481f3a7cc4293208820efcbd` также прошёл exact-head run `41432470109`: Windows **4,426 passed in 135.07s**, Linux **4,426 passed in 27.35s**, Docker build/smoke PASS. Artifact `13135435513`, digest `sha256:c0af92797c94e78b8dcadaa8425cbffef8a6feb32a1431a87fce4f281584b5d0`.
- После следующего документального обновления понадобится новый exact-head CI; далее нужен независимый review. Слияние, deploy и запуск бота не выполнялись.

## Закрытие P2: базовая сумма конфликтовала со статусом расширенного источника (2026-11-02)

- Подтверждённый пример: `LOGISTICS` уже имел известную сумму и входил в `included_expense_keys`, но `excluded_component_statuses={"LOGISTICS":"EXCLUDED"}` добавлял ту же категорию в `excluded_expense_keys`. Статус `UNKNOWN` аналогично создавал пересечение включённого и неизвестного. В sales mix сумма логистики оставалась вычтенной, но выводилась как неизвестная.
- Исправление ограничивает действие статусов дополнительной областью: они не меняют совпадающий ключ из известных базовых расходов модели. Регрессии покрывают `calculate`, `calculate_components_only`, sales mix и оба конфликтующих статуса.
- До исправления новые сценарии воспроизводимо падали; после него связанный профиль — **165 passed in 4.30s**, полный Windows pytest — **4,424 passed in 47.82s**, `compileall app tests` и `git diff --check` PASS. `data/tasks.json` совпадает с baseline SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`, lock отсутствует.
- Exact-head GitHub Actions run `41416052784` на кодовом SHA `372e921c3b4a6c07504754702abd49699efdcf3a` завершился success: Windows **4,424 passed in 146.47s**, Linux **4,424 passed in 29.42s**, Docker build и smoke — PASS. Проверяемый merge ref `3ab500ee038e0d9d1c51d95edf4d86e992bfc558`; artifact `13127109252`, digest `sha256:3dfef7873205c793ca47fcdb7afc8ee54f2663ef843d69a9ae52227958acc2f8`. Документальный follow-up после этого exact-head запускается отдельно.


Дата подготовки: 31.10.2026
Реализационная ветка: `codex/pre-ad-margin-implementation-20261031`
Целевая ветка PR: `codex/pre-ad-margin-spec-20261031` (ветка задания PR #723)
Реализационный PR: https://github.com/dopf129-pixel/ai-business-assistant/pull/724
Предыдущий CI: run `41240191495` прошёл на исходном SHA `fd4d79ed76fb1c2b77382e0f02a14fc22e3edd00`. Для последующих правок нужен отдельный exact-head CI; результаты прежней головы к ним не относятся.
Слияние, развёртывание, live-запросы и запуск бота этим изменением не выполняются.

## Повторный review: предел производной детализации сохранённого плана (2026-11-01)

- Исправлен отказ сохранять валидный frozen capture, если extended source содержит 60–64 компонента: derived scope дополнительно перечисляет базовые категории и причины исключений. Отдельный лимит для списков scope/reasons теперь 72; источник остаётся ограничен 64 компонентами, формат/уникальность/allowlist и payload budget сохранены.
- Regression в `tests/test_saved_planning_plan_telegram_flow.py` сохраняет и перечитывает 60- и 64-компонентные сценарии при 64 исключённых типах; также проверяет отказ 73-го derived key.
- Связанный профиль **163 passed in 4.43s**, полный локальный Windows pytest **4,422 passed in 47.55s**, `compileall` и `git diff --check` PASS. Пользовательские данные восстановлены к baseline SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; lock отсутствует.
- Code SHA `7de3598cdc0d07fd41bfce738fc3e7ef3edf466d` прошёл exact-head run `41343413057`: Windows/Linux full suites по **4,422 passed**, Docker build/smoke success; artifact `13098127220` (`sha256:ba829ba86632fcf8fe644ab7068e9e4f467ca88b4fd0f0f2f67e99b288ff05f9`).
- Перед повторным независимым review проверить exact-head CI для последующей docs-only записи этого результата.

## Повторный review R1–R3 — исправления подготовлены (2026-11-01)

- Исправлено округление состава известных расходов: остаток в несколько копеек отражается как `ROUNDING_ADJUSTMENT`, Telegram-детализация показывает подпись и сходится с канонической прибылью.
- STORAGE/PLACEMENT aliases агрегируются по категории до вывода `CONFIRMED_ZERO`.
- Конфликт между явным исключением категории у одного SKU и включённой категорией другого SKU превращает агрегированное покрытие в partial/unknown.
- Добавлены четыре регрессии в sales mix, pre-ad projection и formatter; linked profile **158 passed**, полный Windows suite **4,420 passed**. Code SHA `18ba381b663370aa6a78264bba012c24c8c073ad` прошёл exact-head run `41338557148`: Windows/Linux full suites, Docker build и smoke — success; artifact `13096362251`, digest `sha256:1a82c63bb909d4bfe71151142526811db5037b1eaf6c6ce2bcf0468511a942f5`. Независимый повторный review нового diff ещё нужен.

## Что меняется

Добавляется аддитивная проекция `pre_ad_margin` с прибылью до рекламы после налога на одну успешную единицу и процентом от цены продавца до баллов. Проекция используется в карточке текущей юнит-экономики, ценовом сценарии, ценовых сетках/целевой марже/чувствительности/пакетном расчёте, составе продаж и поддерживаемых детализациях и выгрузках. Основные старые поля прибыли и сохранённые версии не переопределяются.

### Архитектурное влияние

**Небольшое расширение существующих расчётных контрактов.** Нового framework, внешней зависимости, таблицы или миграции БД не вводилось. Расчёт использует текущий `UnitPriceScenarioService` и `TaxService`; current projection переиспользует уже рассчитанные значения, а историческое восстановление вынесено в отдельную проекцию. Новые поля передаются через существующие query/provider, Telegram handlers, saved-plan/export и snapshot/detail пути. Историческая production-интеграция намеренно fail-closed, когда не хватает точной доказательной оболочки.

## Финансовые основания и ограничения

- Процент считается как `прибыль до рекламы после налога на единицу ÷ цена продавца до баллов × 100`.
- Баллы за скидки могут уменьшить налоговую базу в соответствующей налоговой политике, но не знаменатель процента маржи.
- Для плановой цены налог рассчитывается заново в no-ad ветке через существующий `TaxService`. При налоге с прибыли no-ad налог может отличаться от налога после рекламы.
- Для исторического периода налог не пересчитывается как новый сценарий: берётся налог исходного зафиксированного результата. Разница основания маркируется.
- Историческая реклама добавляется обратно к нетто только при доказанном exact-SKU financial advertising, уже включённом именно в тот же net, того же владельца/магазина/SKU/окна/схемы. Корректировки учитываются единожды. Performance CPC, когортный/аккаунтный/распределённый расход, неполный CPO или рекламный кредит не превращаются в add-back.
- Текущие и плановые значения не являются подтверждённым P&L. Неподтверждённые расходы, реклама, storage/placement/returns и неполные источники остаются unknown/partial, не нулём.
- Ручные цена, тариф, себестоимость и реклама являются сценарными допущениями; цена в Ozon не изменяется.
- Cross-docking применяется только с подтверждённым SKU и знаменателем фактически принятого кросс-докингом количества; это не количество проданных единиц.

## Доступные и недоступные режимы

| Режим | Доступно | Ограничение |
|---|---|---|
| Текущая экономика SKU | До-рекламный вклад из уже полученных текущих суммы прибыли/налога; расходы и окна источников раскрываются | Текущая рекламная стоимость по SKU остаётся неизвестной, если нет точного источника; неподтверждённые категории не включаются как ноль |
| Плановая цена | Before/after ad, налог, сравнение кандидатов при валидных исходных данных | Комиссия должна быть подтверждена для кандидатной цены либо введена вручную как явное допущение |
| Исторический период | Add-back точной финансовой рекламы, доказанной как уже включённая в тот же net; налог сохранён из исторического результата | Текущий production source пока не передаёт полный exact-SKU evidence envelope; тогда новая проекция `UNAVAILABLE`, legacy historical output доступен как раньше |
| Сетка, sensitivity, batch и mix | Общая before-ad проекция и процент при сопоставимой полноте; mix взвешен по выручке | Неполные/несопоставимые случаи не участвуют в ложном общем результате |
| Сохранённые планы и выгрузки | Новые поля в совместимых frozen snapshots/exports без обновления Ozon | Просмотр/экспорт старого snapshot не освежает источники; новая revision создаётся только существующим явным действием |

## Локальная проверка

### Review remediation R1–R5 (2026-11-01)

- Закрыты: stale seller-cost callback между магазинами/SKU; устаревший query cache после явного refresh/save; пропажа before-ad при неизвестной рекламе; потеря partial expense scope в mix/output/export; отсутствие явного T0/T1 в деталях сценария.
- Связанный профиль на текущей локальной голове: **208 passed**; полный Windows pytest: **4,411 passed in 45.99s**.
- `python -m compileall -q app tests` и `git diff --check`: PASS. `data/tasks.json` восстановлен к исходному SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; `data/tasks.json.lock` отсутствует.
- Кодовая голова PR #724 `2e82355d1b0353be0ea3eeb4ed722bba0ac9e498` прошла Verify run `41328828173`: Windows и Linux — по **4,411 passed**, Docker build/smoke — PASS. PR runner проверял merge ref `142e97a80ce08caf047a1b52701bf1c5333ea1d9`; SHA-bound artifact ID `13092810821`, digest `sha256:e9d661a1f64b050fef668e91e7eb61d821c46adc1d64cc4b7e610a17a68df184`.
- Пять исправлений добавлены в открытый PR #724. Нужен повторный независимый review; merge/deploy/bot launch не выполнялись.

- Полный Windows `pytest`: **4,404 passed in 46.19s**, полный прогон без `-k` и deselect на тестовом SHA `eb14db29`.
- Первый прогон выявил недостаточный fake в одном legacy test: он не реализовывал существующий `build_unit_economics_detail_keyboard`. Fake дополнен без изменения production-контракта; целевой модуль: **10 passed**, после чего полный suite повторно прошёл.
- `python -m compileall -q app tests`: PASS.
- `git diff --check`: PASS до текущего документационного коммита; будет повторён на окончательном локальном HEAD.
- Защита пользовательских данных: `data/tasks.json` восстановлен до MA00 baseline SHA-1 `7fcef9d518b4dd2be4b3bb6fd307b93474f6b215`; `data/tasks.json.lock` отсутствует. Проверки выполнялись без Ozon/Telegram запросов и без запуска бота.
- Owner acceptance на реальных данных: **USER_VALIDATION_PENDING**; synthetic tests не представлены как проверка реального кабинета.
- Remote Windows/Linux/Docker CI: GitHub Actions run `41240191495` passed оба job на SHA `fd4d79ed76fb1c2b77382e0f02a14fc22e3edd00`; отчёт `verification-f0731b2556f19e13ebe4e034a3e04ab67108cb49` привязан к этому SHA. Последующие PR heads должны получить собственные exact-head checks; результаты старого spec PR #723 или другого SHA не засчитываются.

## Независимому reviewer проверить

1. Сравнить PR с базой `codex/pre-ad-margin-spec-20261031` и проверить, что в целевой ветке присутствует ТЗ PR #723.
2. Проверить canonical calculation: denominator — seller price before points; no-ad tax и after-ad tax — отдельные вызовы для планового сценария; historical tax — только сохранённый результат периода.
3. Проверить exact-SKU/owner/store/window/schema guards и отсутствие двойного учёта рекламы/корректировок; Performance CPC не участвует в historical add-back.
4. Проверить, что unknown/partial расходы, invalid inputs и неподтверждённая комиссия не становятся нулём, а after-ad не показывается при неизвестной рекламе.
5. Проверить совместимость legacy profit outputs, historical records, frozen plan revisions, ownership/CAS, cache, backup/restore и exports; удостовериться, что новые переходы не добавили скрытых Ozon запросов.
6. Проверить exact-head CI для Windows/Linux/Docker после финального doc commit, чистоту owner data и отсутствие merge/deploy/bot launch.

## Файлы для быстрого просмотра

- `app/services/unit_price_scenario_service.py`
- `app/services/product_unit_economics_historical_pre_ad_margin_service.py`
- `app/services/product_unit_economics_provider.py`
- `app/services/product_unit_economics_query_service.py`
- `app/services/unit_economics_advertising_evidence_service.py`
- `app/services/telegram_unit_price_calculator_runtime_service.py`
- `tests/test_pre_ad_margin_projection.py`
- `tests/test_product_unit_economics_historical_pre_ad_margin.py`
- `tests/test_current_unit_economics_integration.py`
- `project_brain/LUNA_PRE_AD_MARGIN_PROGRESS_2026-10-31.md`

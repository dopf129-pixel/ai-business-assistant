# ТЗ для GPT Luna — R8/R9 дополнительного review PR #695

Дата: 14.10.2026. Статус: **не начато; исправления обязательны до merge**.

## Цель и проверенная ревизия

Закрыть две воспроизведённые технические ошибки на границах существующих source/math/runtime калькулятора. Формулу прибыли и налоговую модель сохранять; бизнес-решение не требуется.

- PR: https://github.com/dopf129-pixel/ai-business-assistant/pull/695.
- Ветка: `codex/unit-price-calculator`.
- Review head: `73c4c74cf786f0a8a38168a27a3a61240d07ce06`; code SHA `3f4942b6c2e01238cabfd9fda7c274ab479bcba7`; base `655b3a0c46acb258a5e884cccc8da6728a5216a7`.
- Evidence: дополнительный review в `ARCHITECTURE_REVIEW_PR695_2026-10-14.md`.
- Baseline: четыре calculator modules — 45 passed; exact-head full CI Verify `38617595326` success. Два isolated probes правильного поведения дают 2 failed, подтверждая R8/R9. Это не acceptance будущих исправлений.

## Ограничения

Прочитать AGENTS.md, CURRENT_STATE, DECISIONS, TEST_MAP, исходное feature ТЗ и предыдущий corrective task. При изменении PR head сначала изучить новый diff. Сохранить существующие data/users.json, data/tasks.json, lock-файлы, базы, credentials и временные каталоги; не включать их в коммиты и fixtures. Не выполнять широкие restore/reset/clean/stash, live Ozon calls, merge или production restart.

Использовать существующие калькулятор, picker, sources и TaxService. Сохранить Decision 045, read-only сценарии, tenant/SKU isolation, operation tickets, callback/version checks, eviction/pending isolation, explicit advertising=0, ручные L/M/E, weighted 28 completed days, source cache bounds и HTTP budget. Исправления не должны менять реальные цены, себестоимость, настройки налогов, расходы или исторические отчёты.

## W00 — baseline и красные интеграционные регрессии

1. Записать branch/head/base и git status без содержимого пользовательских данных.
2. Добавить regressions правильного поведения в штатные calculator test modules; пересечь production source → math → runtime, использовать fake catalog/current facts/finance/cost/tax и injected clocks.
3. Подтвердить red на проверенном коде. Не писать assertions, принимающие недоступный результат или ложную свежесть как правильное поведение. Игнорируемый `.codex-test-pr695-repeat-review/probes.py` в текущей рабочей копии содержит локальную воспроизводимость; необходимые сценарии полностью описаны ниже и не зависят от наличия scratch файла.

## W01 — R8, P2: допустимая точность автоматического среднего баллов

Причина: `UnitPriceScenarioSource._load_discount_points` возвращает Decimal weighted rate строкой с 28 значащими цифрами; `UnitPriceScenarioService._decimal` после R5 ограничивает любое значение 15 цифрами. Полная корректная выборка sale=300, bonus=50 даёт `16.66666666666666666666666667` и блокирует результат как invalid discount_points_rate.

Требования:

- Согласовать precision контракт автоматической ставки на границе источника и math service: безопасное представление/округление с описанной точностью либо отдельная допустимая precision для ограниченных ставок. Не отключать всю защиту числовых inputs и не превращать такой источник в unknown/0.
- Сохранить weighted rate = sum(points)/sum(sales)×100, exact SKU completeness, provenance и период. Пользователь не должен вручную перепечатывать достоверное среднее для получения прибыли.
- Сохранить magnitude/non-finite/negative/range checks и обычный retry UI для недопустимого ручного ввода; неизвестные/конфликтующие данные не становятся допустимыми из-за ослабления проверки.
- Установить единый контракт для первичной загрузки, refresh и «Вернуть среднее баллов».

Минимальные regressions:

1. Production source с полным 28-дневным evidence: одна sale=300 ₽, points=50 ₽; остальные дни полные и пустые. Price=500, cost=120, commission=15%, ручные L/M/E=0, advertising=0, USN_INCOME=6%. После публичного ввода полей итог available=True, tax=25 ₽, profit=280 ₽, margin=56%; invalid discount_points_rate отсутствует.
2. Другой недесятичный weighted rate, первичная загрузка/refresh/restore mean: все дают рассчитываемый сценарий; ручной points override сохраняется после refresh.
3. Existing extreme/non-finite inputs остаются invalid с retry; explicit zero points допустим; incomplete/conflicting source остаётся unknown.

## W02 — R9, P2: возраст cache hit переносится в сценарий

Причина: source отдаёт snapshot cache age, runtime при открытии записывает source_loaded_at=now и теряет уже накопленный возраст. Это продолжение R7, отдельно от исправленного sliding inactivity.

Требования:

- Runtime/source должны передавать фактическую свежесть снимка: origin timestamp или исходный age плюс elapsed в сценарии. Cache hit не продлевает source TTL.
- Один возраст и состояние используются на результате и экране допущений. Источник свеж только при `age < TTL` (как и cache reuse в source); на точной границе TTL current-price comparison уже недоступен и видна просьба обновить источники. Локальные ручные допущения сохраняются.
- Открытие другого сценария на тот же SKU, повтор текста, редактирование и восстановление среднего не обновляют source age. Не делать HTTP для каждого локального пересчёта.
- Успешный реальный refresh переносит свежий origin/age; failed refresh не омолаживает прежний snapshot. Same-key wait/cache reuse учитывает настоящий возраст возвращённого снимка.
- Различать source freshness и sliding session inactivity. Сохранить injected clocks и согласованный TTL; не сравнивать wall-clock timestamp с monotonic clock напрямую.

Минимальные regressions с настоящими source и runtime:

1. t=0 загрузить source, t=590 открыть новый сценарий на тот же SKU через cache hit, t=610 показать результат и assumptions. Underlying current facts read=1; actual source age=610; STALE, comparison unavailable; оба экрана предупреждают об устаревании.
2. Закрыть и снова открыть сценарий до истечения cache TTL — исходный возраст сохраняется. Local edits/restore mean/session activity его не сбрасывают.
3. После stale успешный force refresh получает свежую цену и возраст, ручные поля сохранены. Failed refresh сохраняет STALE. Existing R7 direct-load и R1–R6 regressions остаются зелёными.

## W03 — приёмка и документация

После W01/W02 выполнить новые integration regressions, четыре calculator modules и смежные handler/adapter/factory/tax/tenant checks. Затем обязательный full pytest, compileall, Windows/Linux/Docker CI нового code SHA и повторный review.

Обновить CHANGELOG, CURRENT_STATE, TEST_MAP, исходное feature ТЗ, оба corrective tasks и acceptance в review. DECISIONS изменять только при настоящем новом архитектурном решении; ожидается небольшой patch существующего контракта без нового слоя. Записывать реальные SHA/runs/results, не использовать прежний зелёный CI как acceptance нового кода.

Порядок: W00 → W01 → W02 → W03; маленькие проверяемые коммиты. Критерий завершения: R8/R9 red→green в штатном suite, сохранённые предыдущие guarantees, зелёный full CI нового кода и повторный review без блокеров. Слияние проведёт другая модель после приёмки.

| Этап | Статус |
|---|---|
| W00 | Завершён | Добавлены штатные integration regressions; до исправления обе проверки красные на исходной логике, после — зелёные. Базовая ревизия: `34b38e9`. |
| W01 — R8 | Завершён локально | Ограничение 28 значащих цифр только для bounded ставок; money guard остался 15 цифр. Проверка source→math→runtime и precision boundary зелёные. |
| W02 — R9 | Завершён локально | Runtime сохраняет cache age + elapsed и source TTL в сценарии; result/assumptions используют общий freshness state. Повторное открытие и локальная активность не омолаживают cache; на age==TTL состояние stale; успешный refresh обновляет возраст и сохраняет manual ad override. |
| W03 | Выполняется | Calculator набор **48 passed**, полный isolated Windows pytest **3 141 passed in 25.15s**, compileall прошёл с прежней SyntaxWarning. Остались публикация нового code SHA, GitHub CI и повторный review до слияния. |

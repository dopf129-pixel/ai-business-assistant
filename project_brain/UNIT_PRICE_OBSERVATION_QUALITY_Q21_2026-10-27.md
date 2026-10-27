# Quality/comparability gate наблюдений цены (Q21)

Дата: 27.10.2026
Статус: VERIFIED
Классификация: Architecture Review Required

## Контракт

`UnitPriceObservationQualityService.assess()` принимает 2–10 сохранённых результатов, owner/store scope, их явно переданную `assumption_signature` для модели и timezone-aware `now`. Переданный store должен совпасть с store результата, а сравнение разных owner/store запрещается. В assessment payload выдаются общий статус/основание, `verified`, причины, предупреждения и данные каждого варианта: ревизия, цена, число дней, подтверждённые успешные единицы и возраст evidence. Идентификаторы операции/товара в payload не копируются.

Сравнение блокируется при разных owner-store/product/offer/SKU/scheme identity, одинаковых ценах, разных evidence/revenue/advertising bases, несовместимых датах/окнах/timezone/source bases, пересечении окон, неподтверждённом denominator, неполных/устаревших источниках или различающихся frozen допущениях модели. Число строк источника не используется вместо количества проданных единиц.

`CANONICAL_FACT_COMPARABLE` возможен только когда подтверждены per-sale `SELLER_PRICE` history, successful units, полный finance/Analytics/ad/return data, тариф, налог, unit cost, window и dedup, а все требуемые source records полные и свежи. Event-date bases finance/Analytics/ad/returns/seller-price должны совпадать; tariff/tax/cost подтверждаются собственными source window/completeness, без требования совпасть с event-date basis. Для model-only допускается только `MODELLED_FROM_OBSERVED_INPUTS`, `AVAILABLE`, полный CPC + успешный знаменатель, ручные тариф/налог/себестоимость и одинаковая непустая assumption signature в одном owner/store scope. Такая пара может иметь статус `COMPARABLE`, однако основание остаётся модельным и `verified=false`; ручная цена, CPC-only, возвраты и отсутствие причинной связи выводятся предупреждениями. Статус отдельного кандидата — `READY` или `INCOMPARABLE`; один кандидат не получает `COMPARABLE`.

Начальные технические ориентиры: желательная длительность — 7 дней; ниже 30 подтверждённых единиц — малая выборка; evidence старше 14 суток — устаревшее. Выборка и длительность дают только предупреждения. Ни пороги, ни сравнение не создают статистического confidence score или причинного утверждения. Настройки ограничены параметрами сервиса: 3–56 дней, 1–10 000 единиц, свежесть 1–90 суток.

В Telegram detail результат показывает проверку для одного сохранённого варианта как `NOT_READY`, сообщает выборку, предупреждения и все причины; полный machine-readable `quality_assessment` приложен к response payload. Durable comparison snapshot будет добавлен в Q23; сейчас assessment вычисляется локально и не меняет immutable source result.

## Изменённые компоненты

- `app/services/unit_price_observation_quality_service.py` — pure gates, совместимость model/fact оснований, overlap/freshness/sample checks, safe assessment payload.
- `app/services/telegram_unit_price_observation_runtime_service.py` — quality assessment на result detail, понятная подпись модельного результата и причин.
- `tests/test_unit_price_observation_quality_service.py` — синтетические quality fixtures.
- `tests/test_telegram_unit_price_observation_runtime.py` — проверка one-candidate `NOT_READY` в UI payload.
- `CHANGELOG.md`, `CURRENT_STATE.md`, `TEST_MAP.md`, progress journal — этап и acceptance.

## Проверки

- Q21 focused service + Q19 result/Q16 repository + Telegram runtime: **32 passed in 1.69s** (Windows/Python 3.12).
- Связанный isolated Q16–Q21 profile, 15 targets: **205 passed in 4.87s** (Windows/Python 3.12).
- AST parse четырёх затронутых Python-файлов: passed. `git diff --check`: passed; Git выдал только уведомления LF→CRLF для Markdown/runtime. `git diff -- data`: empty.
- Синтетические candidate fixtures покрывают одинаковые допущения модели (разрешённый model-only результат, `verified=false`), mixed identity, duplicate price, different dates/source bases, overlap, denominator, stale oldest source, малую выборку и условный полный canonical fact. Неполная цена запрещает verified label.
- Ограничения среды: API/Ozon/Telegram/owner DB/`.env`/tracked data и реальный бот не использовались; source evidence смоделировано фикстурами. Comparisons пока не сохраняются durable-ревизией; это Q23.

## Следующий этап

Q22 должен отдельно ранжировать сценарные допущения и quality-approved наблюдения по прибыли ₽/шт., обрабатывать равенство, отрицательную базу и разницы без причинного вывода. Нельзя включать кандидатов с `INCOMPARABLE`/`NOT_READY` в рейтинг; отбор лучшего всегда ограничен проверенными вариантами.

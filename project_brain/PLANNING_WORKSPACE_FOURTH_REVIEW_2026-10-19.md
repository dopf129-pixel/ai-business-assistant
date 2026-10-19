# Четвёртый review planning workspace — 19.10.2026

Решение: **REQUEST CHANGES. PR #708 пока не сливать.**

Проверенный head: `0e0f7928a22eeca10995c72c1e3f8bab100f0b25`.
Base PR #708: `b66ebc45686e276c76bfcb4173c92cade6100c9c`.
Локальная ветка: `codex/planning-workspace-20261019`.
Remote head: `codex/planning-workspace-ln`.

Проверены исправления R16–R17, соседние входы целевой маржи, restore/refresh/
readiness/update, привязка к exact catalog identity, default tenant scope,
snapshot/export и свежие CI статусы. Production code и tests при review не менялись.

## Результат прежних исправлений

- R16: default owner-only tenant согласован с пустым store ID в saved runtime,
  repository и transient snapshot store. Public regression export CSV/JSON,
  comparison/export, readiness cost/Q edit и изоляция явного store проходят.
- R17: цель из «Цена для целевой маржи» переживает apply/back, сохранение,
  восстановление и повторное сохранение. Дополнительный public probe подтвердил
  сохранение цели 25 после source refresh, ручной правки цены и CAS update.
- Сохранился отдельный непокрытый вход цели через рекламный калькулятор (R18).

## R18 · P2 · Цель рекламного предела не попадает в сохранённый рецепт

Место: `app/services/telegram_unit_price_calculator_runtime_service.py:2128–2136`.
Связанный producer: строки 1550–1560.

`_target_margin_assumption` читает `price_planning_target_margin` и временный
`price_planning_result`. Ввод в «Сколько можно тратить на рекламу?» сохраняет цель
только в `advertising_cap_result.target`, поэтому capture её не видит. Применение
рекламного предела удаляет этот результат; восстановить цель из него позже нельзя.

Воспроизведения через настоящий AssistantButtonHandlerService, temporary SQLite,
один fake source read, без внешних вызовов:

1. Single → рекламный предел → цель 25 → «Подставить предел целевой маржи» →
   сохранить. В принятом результате target_margin_percent="25", сохранённая
   advertising_rate="24.20", но payload.target_margin_percent=null.
   Исторический рекламный предел пишет, что явной цели нет.
2. Та же цель 25 → «Назад к расчёту» → сохранить: target=null, при историческом
   просмотре снова нет цели.
3. Сначала цена для цели 25, затем рекламный предел для цели 30 → применить →
   сохранить: рецепт хранит прежние 25, хотя последний рекламный расчёт был для 30.

Это затрагивает I00 (saved recipe сохраняет target), J02 (historical advertising
cap) и обязательный O00 flow single → advertising caps → save → restart → read.

Исправление: записывать принятое явное допущение цели также на входе рекламного
калькулятора и согласованно переносить его в capture/restore. Если продукт допускает
разные цели price/ad-cap, сохранять и показывать их отдельно вместо молчаливой
подмены/потери. Не полагаться на disposable result после apply/back.

Регрессии: advertising goal → apply/back → save → restart → historical cap;
price goal 25 → advertising goal 30 → save; update существующей revision.

## R19 · P2 · План без sales mix допускает перенос старых overrides на другую карточку

Место: `app/services/telegram_saved_planning_plan_runtime_service.py:1824–1826`.
Связанные границы: `_execute_action(refresh)`, calculator `_refresh`, строки
1773–1782 и 1792–1802.

При отсутствии sales mix `_preserve_saved_plan_context` возвращает capture до
проверки exact identity. Refresh перед этим проверяет у fresh snapshot только
tenant scope и накладывает старые manual overrides. Реальный source ищет текущий
товар по SKU; текущая product_id/offer_id может не совпасть с сохранённой identity.
В результате новая revision принимает другую карточку со старой себестоимостью.

Public reproduction на temporary SQLite с согласованными fake каталогом и source:

1. Сохранить single-план без sales mix: product-1/offer-1/sku-1, manual cost=125.
2. Изменить текущий fake каталог и snapshot: тот же sku-1, product-new/offer-new,
   актуальная cost=999.
3. Открыть сохранённый план → «Обновить источники» → «Сохранить изменения в этот план».
4. Получены UNIT_PRICE_SCENARIO_READY и PLANNING_DOCUMENT_UPDATED. Revision 2
   содержит product-new/offer-new, но cost="125", manual_seller_assumption.
   Предупреждения/подтверждения смены товара не было. Сделано два source reads:
   первоначальная загрузка и явный refresh.

Это нарушает I03.4 и архитектурное решение в DECISIONS: при обновлении переносить
только manual assumptions с точным совпадением identity. Наличие sales mix не
должно определять обязательность этой проверки. Существует service helper
`capture_refreshed_copy` с exact-identity matching, но runtime этот путь не использует.

Исправление: проверить owner/store + product_id/offer_id/SKU до переноса old
overrides и публикации обновлённого сценария. Смена identity должна дать controlled
unresolved/scope-change либо явный переход к новому плану, без переноса старых
manual values. При save-update проверять состав identity и без sales mix.

Регрессии: restore/refresh без mix с изменением product_id и offer_id по отдельности;
тот же SKU в другом store; штатное совпадение identity сохраняет manual values;
отказ не меняет durable revision и не выдаёт новую карточку с прежними overrides.

## Проверки и границы review

- Новый локальный targeted профиль: **41 passed in 1.28s** — saved-plan public flow,
  scoped snapshots и historical comparison. Полный локальный pytest не повторялся
  из-за зафиксированного Windows ACL/shared-storage инцидента.
- Fresh exact-head CI для `0e0f7928a22eeca10995c72c1e3f8bab100f0b25`:
  Verify `39235275558` и `39235284525` — success на Windows/Linux. В run
  `39235284525` дополнительно прочитаны jobs/steps: полный pytest, compile,
  production Docker build и runtime smoke успешны. Новые R18/R19 flows не покрыты
  существующим regression suite.
- Воспроизведения: `.review-h-o-round4-20261019/review_probes.py`, отдельные
  UUID-каталоги и synthetic SQLite; Ozon/Telegram API, .env и реальный бот не использовались.
- Hash пользовательских файлов сохранился:
  tasks `8F7FFF206A4748DE6EFB3E5DCABABD07E3341188A7326383A21D966B73710698`;
  users `0B12986702D5C62B8A410EE4B3B3228923FF72BA897F18FF62FEF556CDA88409`.
- `git diff --name-only HEAD -- app tests` пуст. Созданы только локальные review
  report и probe, Git HEAD и PR metadata не менялись; review submission/merge/deploy
  не выполнялись.

## Зависимости и следующий шаг

PR #705–#708 остаются открыты, проверенные heads:

- #705 `050563b6e8766efa06e3b733fc69bc35e086899d`, base main `722f368526c278b701cbfd69f3dbb9a474d52386`.
- #706 `4e6b1bc1f2d05433537f7caf2fda450b33ccce65`, base #705.
- #707 `b66ebc45686e276c76bfcb4173c92cade6100c9c`, base #706.
- #708 `0e0f7928a22eeca10995c72c1e3f8bab100f0b25`, base #707.

Предыдущие исправления зависимостей включены в верхний #708. На момент review до
слияния требовалось исправить R18/R19, добавить meaningful public regressions,
получить CI нового SHA и повторный review. После принятия стек сливает другая
модель с перепроверкой base/head и CI при каждом retarget.

## Исправления R18/R19 — 19.10.2026

- R18: принятая в рекламном калькуляторе цель теперь записывается в долговечное
  session assumption `price_planning_target_margin`. Она сохраняется после
  apply/back, capture/restore, исторического просмотра и CAS-обновления плана;
  последняя явно введённая цель заменяет предыдущую.
- R19: refresh сравнивает owner/store/product/offer/SKU identity до переноса
  ручных overrides. При несовпадении карточки или магазина он завершается
  контролируемым отказом и не публикует свежий snapshot поверх старых ручных
  значений. Save-update повторно проверяет полный набор identity и для плана без
  sales mix.
- Добавлены public-flow regressions на restart/historical advertising cap,
  пересечение целей price/ad-cap, update существующей revision, смену
  `product_id`, `offer_id`, `store_id`, неизменность прежней revision и
  дополнительную проверку identity без sales mix.
- Проверки на рабочем Windows окружении: **86 passed in 1.99s** для пяти
  связанных модулей; `compileall -q app tests` и `git diff --check` прошли.
  Полный локальный suite не запускается из-за известного Windows ACL/shared-
  storage инцидента. SHA-256 пользовательских `data/tasks.json` и
  `data/users.json` совпали с baseline этого review. Новый exact-head CI PR #708
  и повторный independent review ожидаются; merge/deploy не выполнялись.

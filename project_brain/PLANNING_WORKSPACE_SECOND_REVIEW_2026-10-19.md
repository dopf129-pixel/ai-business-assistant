# Повторный review planning workspace — 19.10.2026

Решение на проверенном SHA `84ab5168f21a407d86495b4caecaedc1e78c1102`: **REQUEST CHANGES.** Это исторический вердикт для того SHA; R11–R15 ниже реализованы в текущем рабочем дереве и прошли целевые регрессии. Для допуска к слиянию остаются публикация, exact-head CI и повторный review. Слияние этим исправлением не выполняется.

Проверенный head PR #708: `84ab5168f21a407d86495b4caecaedc1e78c1102`.
Base: `b66ebc45686e276c76bfcb4173c92cade6100c9c`.
Локальная ветка: `codex/planning-workspace-20261019`.
Review включает исправления `d0570313` относительно предыдущего review
`6099294a` и взаимодействие с сохранением, обновлением источников,
historical comparison, fallback tenant scope, экраном и выгрузками.

PR #705–#707 всё ещё открыты на прежних проверенных heads:
`050563b6`, `4e6b1bc1`, `b66ebc45`. Исправления из второго раунда находятся
в #708; они не перенесены отдельно в нижние PR. Слияние этим review не выполняется.

## R11 · P2 · Одинаковые неподдерживаемые версии пересчитываются текущим калькулятором

Место: `app/services/planning_plan_comparison_service.py:39`, `145–157`.

Compare проверяет только равенство двух payload.calculation_version. Если оба
документа сохранены версией 1, а активный scenario service уже версии 2, gate
пропускает их и `_project_mix` вызывает текущий calculator. Результат объявляется
COMPARABLE и historical, хотя вычислен по другой версии правил. Сохранённые деньги
старой версии не используются как источник для этого пересчёта.

Изолированное воспроизведение: два payload версии 1; текущему calculator задан
VERSION=2 и установлен счётчик вызовов `calculate_components_only`. Compare вернул
`COMPARABLE`, `recalculated_from_saved_inputs=True`; новый calculator вызван дважды.
После реального изменения формулы это меняет исторические profit/margin deltas.

Исправление: сравнивать поддерживаемую текущую calculation version перед любым
пересчётом либо использовать отдельный совместимый исторический calculator/stored
aggregate projection. Для неподдерживаемой версии оставить input differences,
подавить derived metrics и дать причину. Регрессия должна включать две одинаковые
устаревшие версии, а не только два разных номера.

## R12 · P2 · Refresh → ручная правка снова теряет связь с сохранённым планом

Место: `app/services/telegram_saved_planning_plan_runtime_service.py:442–465`.

Refresh добавляет кнопку `save_update`, но не регистрирует соответствующий editor
context. Связь регистрируется только при входе через readiness edit. Когда
пользователь после refresh нажимает обычную кнопку изменения поля, прежний action
очищается, а decorator не может восстановить CAS controls для исходного документа.

Воспроизведение через настоящий public handler: single → сохранить v1 → открыть
план → «Обновить источники» (save-update присутствует) → «Цена» → 650. После ввода
кнопки «Сохранить изменения в этот план» нет, durable revision остаётся 1; доступно
только сохранение отдельного документа. Эта последовательность должна позволять
обновить исходный план по explicit CAS.

Исправление: привязать refreshed single/batch editor к exact document, payload
revision и state_revision до возврата результата, как в readiness path. Добавить
public single/batch regressions refresh → несколько правок → save-update, а также
stale state/store switch rejection.

## R13 · P2 · Поддерживаемый fallback scope отвергается как изменение состава SKU

Место: `app/services/telegram_saved_planning_plan_runtime_service.py:1750–1753`.

`rows_by_identity` требует непустое значение каждого элемента ключа, включая
store_id. Но Telegram `_resolve_tenant_scope` поддерживает legacy/default scope
в виде user_id; `UnitPriceScenarioSource` формирует для него store_id=None,
а repository корректно нормализует его в пустую строку. Остальные planning paths
принимают такой scope.

Воспроизведение: tenant `user-1`, store_id=None в source snapshot → save single →
сохранить sales mix → refresh → save-update. Первые операции успешны, последняя
возвращает `PLANNING_SALES_MIX_SCOPE_CHANGED`, хотя SKU, владелец и магазин не менялись.

Исправление: обязательность product/offer/SKU проверять отдельно; store scope
сравнивать в той же нормализованной форме, что и repository/source. Пустой store_id
не должен сам по себе означать смену товара в разрешённом fallback tenant scope.
Нужна public regression с tenant без `::ozon::client_id`.

## R14 · P2 · Экран скрывает изменение расходов и пишет, что параметры не менялись

Место: `app/services/telegram_saved_planning_plan_runtime_service.py:1411–1424`.

Service уже формирует корректные `expense_changes`, и export их сохраняет.
Renderer обходит только SKU input_changes; ни одной строки expense_changes он
не показывает. Если изменён только расход, выводится «Введённые параметры не
изменились», хотя прибыль и маржа уже другие.

Воспроизведение: два совместимых плана с одинаковыми SKU/inputs/Q, во втором
добавлен `New expense=10`. Модель содержит before=0, after=10, delta=10; экран
не содержит названия расхода и содержит утверждение об отсутствии изменений.

Исправление: включить добавление/удаление/переименование/сумму расходов в видимый
список before/after и вычислять empty-state по всем типам изменений. Нужна
public-renderer regression, не только service/export tests.

## R15 · P2 · Подробнее повторяет обрезанный экран и скрывает добавленный SKU

Место: `app/services/telegram_saved_planning_plan_runtime_service.py:1391`, `1424`.

Экран берёт только первые 24 изменения, затем режет всё сообщение до 3500 символов.
Callback «Подробнее» вызывает тот же renderer без страницы/detail режима.
Следовательно, оставшиеся изменения недоступны в интерфейсе и пользователь
не получает предупреждения о неполном списке. Это также оставляет R10 частично
незакрытым: добавленный/удалённый SKU после изменённых общих строк снова исчезает.

Воспроизведение: три общих SKU, 33 изменения полей/Q и добавленный четвёртый SKU.
Service содержит четыре identity и added row. Основной экран не содержит
`sku-added`; «Подробнее» возвращает идентичный текст и тоже скрывает его.
CSV/JSON полный scope при этом сохраняют.

Исправление: доступные страницы/подробности из того же immutable snapshot,
с явным показом количества скрытых изменений и гарантированной видимостью scope
changes. Регрессия: >24 изменений, added/removed SKU в конце сортировки,
достижимость каждого изменения, message/callback limits и отсутствие новых Ozon reads.

## Проверки и статус прежних исправлений

- На текущем SHA повторно проверены Verify `39222308985` и `39222302010`:
  Windows и Linux full-verification — success; compile и production Docker
  build/runtime smoke успешны. Зелёный CI не покрывает перечисленные случаи.
- Повторный локальный целевой pytest: **49 passed in 3.23s**. Команда включает
  repository, saved-plan Telegram flow, sales mix, comparison и export modules,
  с тем же изолированным ACL-compatible temp fixture plugin.
- R2/state CAS, R3/batch save, R5/new capture status, R6/atomic initialization,
  R7/reset invalidation и R9/aggregate bounds проходят соответствующие регрессии.
  R1/R8 работают в проверенных основных сценариях, но имеют пробелы R12/R13.
  R4 устраняет исключение сервиса, но экран требует R14; R10 исправлен для export,
  но неполон на длинном экране (R15).
- Пять новых замечаний воспроизведены на синтетических данных; probe script:
  `.review-h-o-round2-20261019/review_probes.py`. Отдельная проба navigation/query
  interleaving не используется как блокирующее замечание: реальный polling
  обрабатывает updates последовательно, её достижимость этим review не доказана.
- Полный локальный pytest не повторялся из-за записанного ACL/shared-storage
  инцидента. Реальный бот и Telegram/Ozon API не запускались; .env не читался.
- Код/тесты/PR head не изменены. Добавлены только локальный review report и scratch
  probes/SQLite files. Слияние, коммиты и публикация GitHub review не выполнялись.
- Контрольные суммы пользовательских данных после проверок совпали с исходными:
  tasks `8F7FFF206A4748DE6EFB3E5DCABABD07E3341188A7326383A21D966B73710698`,
  users `0B12986702D5C62B8A410EE4B3B3228923FF72BA897F18FF62FEF556CDA88409`.

Следующий шаг: исправить R11–R15, добавить регрессии на эти последовательности,
получить CI для нового SHA и повторно проверить изменения перед слиянием.

## Исправления R11–R15 — 19.10.2026

- **R11**: `PlanningPlanComparisonService` теперь требует, чтобы общая сохранённая `calculation_version` совпадала с текущей поддерживаемой версией scenario calculator. Для старой версии сохраняются input differences, но derived metrics остаются NOT_COMPARABLE; calculator не вызывается.
- **R12**: после refresh single/batch editor context запоминает новый editor id/version вместе с документом, payload revision и state revision. Регрессии проверяют несколько обычных полевых правок перед CAS обновлением той же ревизии.
- **R13**: обязательными остаются product_id/offer_id/SKU; store ID нормализуется к пустой строке на обеих сторонах точного сравнения. Публичный flow проверяет поддерживаемый fallback tenant scope через refresh/update.
- **R14**: экран отображает статьи фиксированных расходов с суммой до и после и больше не сообщает «изменений нет», когда менялись только расходы.
- **R15**: сравнение форматирует изменения состава SKU, inputs и fixed expenses в страницы по 8 элементов. Scope changes идут первыми; переходы и exports читают прежний snapshot, без повторного вызова Ozon. Регрессия обходит все страницы при 34 изменениях.
- Локальная проверка: связанные repository/saved-plan/sales-mix/comparison/export/readiness тесты — **62 passed in 3.85s**; compileall и diff-check — PASS. Хэши пользовательских `data/tasks.json` и `data/users.json` остались прежними. На момент записи проверка относится к незапубликованному рабочему дереву; exact-head CI/review ещё не выполнялись.

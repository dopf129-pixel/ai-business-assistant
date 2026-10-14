# Архитектурный review PR #694

Дата: 14.10.2026, Europe/Moscow.

PR: https://github.com/dopf129-pixel/ai-business-assistant/pull/694

Проверенный исходный код: `ac0f10147806440a0b97203b273a07892aacd42b`.
База: `acbbabb5ee610998a336fa41496600560bc64243` (`main`).
Ветка: `codex/p00-project-baseline`; diff — 92 файла, 10 286 additions / 710 deletions.

**Вердикт: требуется исправление R1–R5 до слияния.** Два замечания P1 и три P2 воспроизведены на текущих production-классах с подставными источниками. Исправления реализации в рамках этого review не выполнялись.

## Проверенные границы

- P01: JSON task store, стабильный coordination file, OS locking POSIX/Windows, optimistic fingerprint, atomic replace, file fsync и явное предупреждение о неподдерживаемом directory fsync Windows. Замены storage engine нет; межпроцессные Windows/POSIX проверки входят в CI. Архитектурного блокера в этом расширении не найдено.
- P02: подтверждение даты/истории себестоимости, CSV preview, tenant-local `BEGIN IMMEDIATE` и batch rollback, доказательная SKU/quantity цепочка. Атомарность batch сохранения устроена последовательно; граница пользовательского подтверждения нарушена в R1, граница pending scope — в R2.
- P03/P04: account net accrual сохраняет денежный авторитет; классификация расходов выделяет непересекающиеся суммы и сверочный остаток; last mile вложена в доставку, Performance CPC не вычитается повторно. Counts строк реализации и физические единицы остаются отдельными величинами. `ClientReturn` отделён от `Cancellation`; отсутствующие Analytics metrics остаются unknown. Принятые ранее ограничения live-источников этим review не отменяются.
- P05: Seller API использует request-local trace и потокобезопасную резервацию запросов; HTTP-таймауты ограничены оставшимся временем. Performance остаётся вне общей резервации (R4).
- P06: внешние расходы используют существующий repository/evidence contract, явное подтверждение и отдельное подтверждение coverage; состояние ввода описания нарушено в R3.
- P07: read-only представление использует canonical Return COGS resolver и снимок собственного store/user/report id; новые accounting recognition/authorization/commit consumers не появились.
- P08: новый экран использует существующий Product Decision, фильтрует свежесть, ограничивает сообщение и summary cache; shared decision LRU требует синхронизации (R5).

Общий характер PR: **Minor architectural extension / Architecture Review Required**. Новые UI/runtime сервисы добавлены в существующую composition factory; конкурирующий framework или замена core pipeline не обнаружены.

## R1 — P1: кнопка подтверждения себестоимости не связана с показанным черновиком

Места: `app/services/telegram_seller_cost_update_service.py:11`, `:215`, `:249`, `:276`, `:413`; CSV-кнопка — `:348`. Адаптер принимает те же постоянные callback strings.

Все previews используют постоянные callbacks (`seller_cost_confirm_date`, `seller_cost_table_confirm` и варианты всей истории). Обработчик выбирает последний `_pending[user_key]` и проверяет только магазин и текущий step. Он не может определить, к какому preview относится нажатая кнопка.

Воспроизведение:

1. В одном магазине открыть товар `s1`, ввести 10 ₽ и сохранить callback из preview.
2. Открыть товар `s2`, ввести 20 ₽, получив новый preview.
3. Нажать callback из первого сообщения.
4. Фактически сохраняется `s2 = 20`, хотя пользователь нажал подтверждение сообщения `s1 = 10`.

Фактический вывод probe: `{'saved_sku': 's2', 'saved_cost': 20.0, 'error': False}`.

Та же форма ошибки относится к повторному preview того же товара, CSV и подтверждению всей истории. Старое cancel-нажатие также может отменить новый черновик.

Необходимое исправление: каждый preview/пакет получает уникальный draft id; callback связывается с user/store/draft/action; при подтверждении идентичность и версия черновика проверяются до записи. Старые callbacks отклоняются. Переходы выбора всей истории должны сохранять привязку к тому же draft.

Регрессии: старый preview A после preview B; один SKU с двумя суммами; два SKU; две CSV-таблицы; старая whole-history кнопка; старый cancel; повторное и параллельное подтверждение одной версии. Недействительное нажатие не записывает данные.

## R2 — P1: pending произвольного периода переносится в другой магазин

Места: `app/services/assistant_period_profit_runtime_service.py:59`, `:109`, `:149`; `app/services/experimental_store_economics_runtime_service.py:186`, `:205`.

Pending custom period хранится по Telegram user без tenant/store. Новый inflight key уже включает tenant, но этот ключ создаётся после чтения старого pending и не защищает происхождение формы. Store-selection callback обслуживается `TelegramCommandService` до button handler, поэтому очистка в button handler не выполняется. При следующем тексте старый режим/SKU используется под credentials нового магазина.

Воспроизведение: под `store-a` вызвать `begin_custom_sku_period(101, 'store-a-sku')`, затем под `store-b` отправить `01.08.2026 - 31.08.2026`.

Фактический результат probe: `{'scope': 'store-b', 'sku': 'store-a-sku', 'period': ['2026-08-01', '2026-08-31']}`.

Если такой SKU существует в B, пользователь получает расчёт чужого выбранной форме магазина; иначе получает необъяснимую ошибку. Общий custom period, pre-COGS и эксперимент имеют ту же потерю origin scope.

Необходимое исправление: сохранить исходный tenant/store вместе с pending и сверять его до потребления формы/вызова query. Переключение или отключение магазина должно отменять старую форму либо возвращать явное stale-сообщение; нельзя тихо пересоздавать её под B.

Регрессии: полная production-route последовательность «начать в A → `ozon_store:B` → ответить датами», все четыре режима, отключение магазина и два независимых пользователя. Ни один старый pending не запускает query в новом store.

## R3 — P2: введённое описание внешнего расхода отменяет черновик

Места: `app/services/telegram_external_expense_runtime_service.py:86`, `:144`, `:152`.

После суммы draft получает `AWAITING_DESCRIPTION`. Следующий `handle_text` допускает только `READY`, поэтому отклоняет корректное описание до обработки stage `description` и очищает pending. Кнопка «пропустить» работает, поскольку другой helper допускает этот статус; имеющиеся тесты используют именно пропуск.

Воспроизведение: выбрать период → добавить расход → дата → категория → сумма → ввести описание.

Фактический вывод probe: prompt `TELEGRAM_EXTERNAL_EXPENSE_INPUT_DESCRIPTION`, затем `TELEGRAM_EXTERNAL_EXPENSE_DRAFT_STALE` вместо preview.

Необходимое исправление: согласовать допустимые draft statuses с каждой текстовой стадией, сохранив блокировку текстовых изменений во время сохранения/после подтверждения.

Регрессии: непустое описание до preview и записи, повтор после слишком длинного описания, skip-description, cancel, stale/confirmed/saving draft.

## R4 — P2: общий бюджет операции не ограничивает Ozon Performance

Места: `app/api/ozon_performance_historical_reports.py:575`, `:641`, `:650`, `:771`; transport `app/api/ozon_performance_client.py:146`.

Historical Performance проверяет только собственные 180 секунд / 120 calls. Вызовы auth, JSON и download не резервируются через активный `PeriodProfitOperationTrace` и не ограничиваются его оставшимся временем. Поэтому объявленный общий лимит 600 секунд / 300 HTTP-попыток применяется к Seller API, но не ко всем Ozon запросам одной операции.

Два изолированных probes с активным trace:

- `ozon_request_budget=0`: `_json` выполнил один Performance `_request`; shared `ozon_requests_reserved=0`.
- `time_budget_seconds=0`: `_json` также выполнил один Performance `_request`.

В production optional CPC может продолжать сеть после исчерпания общего бюджета и добавлять свой отдельный лимит поверх общего. Auth использует transport timeout без уменьшения до остатка общего времени.

Необходимое исправление: все фактические Performance HTTP-попытки (включая token refresh и download) используют тот же operation trace, когда он активен; independent enrichment limits остаются дополнительными верхними границами. Таймаут берётся из минимума оставшихся global/local budgets. При исчерпании optional enrichment финансовый результат сохраняется с объяснением неполной сверки.

Регрессии: исчерпанные shared requests/time budgets до auth/JSON/download, cached token без фиктивной HTTP-попытки, 401 refresh, 429 retry, shared лимит при Seller + Performance и сохранение базового результата без CPC.

## R5 — P2: конкурентное вытеснение из decision LRU вызывает KeyError

Места: `app/services/product_business_decision_query_service.py:475`, `:483`, `:494`, `:496`.

Новый bounded `OrderedDict` общий для worker threads. В `_cached_decision` чтение, проверка expiry и `move_to_end` выполняются без общей блокировки со `_store_decision`/eviction. Пока reader уже прочитал entry, writer может удалить этот key при заполнении LRU; reader затем вызывает `move_to_end` для отсутствующего key и падает. Telegram обрабатывает параллельные запросы через `asyncio.to_thread`; summary lock защищает только другой cache.

Воспроизведение с контролируемым межпоточным interleaving и `decision_cache_max=1`:

1. Reader читает entry `s1` и ждёт.
2. Writer сохраняет `s2`, вытесняя `s1`.
3. Reader продолжает `_cached_decision('s1')`.
4. Фактический результат: `KeyError`.

Необходимое исправление: синхронизировать get/expiry/move/store/evict как одну операцию над cache. Блокировку нельзя удерживать на время запросов Ozon. Tenant isolation и bounds должны сохраниться.

Регрессии: контролируемый read/eviction interleaving, одновременные stores/users, expiry и сохранение capacity; нет исключений или смешения tenant данных.

## Фактические проверки и ограничения

- GitHub checks для reviewed head `ac0f101` зелёные. Exact push Verify #2979: Linux Python 3.11 — 3 077 passed; Windows Python 3.12 — 3 077 passed; Linux production Docker build/smoke прошли. После открытия PR checks также завершились успешно.
- Пять описанных behavioral probes выполнились на production-классах и подтвердили R1–R5. Ещё один probe R4 отдельно подтвердил игнорирование time budget. Это воспроизведения дефектов, а не новые passing regression tests.
- Probes использовали fake catalogs/repositories/transports и controlled context/clocks/events. Реальные Ozon HTTP-вызовы, продавецкие файлы и БД не использовались.
- CURRENT_STATE, TEST_MAP, DECISIONS и LUNA task проверены strict UTF-8; NUL bytes отсутствуют.
- Production source не менялся. Рабочие `data/users.json`, `data/tasks.json`, lock и существующие временные каталоги сохранены.
- Зелёные 3 077 tests не включают найденные interleavings и пути stale/description; они не закрывают замечания.

## Условия для последующего слияния

1. Исправить R1–R5 небольшими изменениями с перечисленными meaningful regression scenarios.
2. Обновить фактические статусы/TEST_MAP и выполнить targeted regressions, затем required full CI Windows/Linux и Docker для нового code revision.
3. Повторно проверить изменения, связывающие callback approval, pending scope, общий HTTP budget и shared LRU.
4. Сохранить P04 source limitations как unknown; новые checks не являются live-подтверждением источников Ozon.
5. Модель, выполняющая merge, должна увидеть отсутствие открытых R1–R5 на проверенном новом code head. Этот review не даёт разрешения на слияние исходного `ac0f101`.

Следующий этап — исправления замечаний; сама реализация этих исправлений не входит в текущий review.

## Follow-up к R1–R5 — исправления внесены, проверка нового revision ожидается

Статус на 14.10.2026: пять замечаний исправлены в рабочем дереве PR #694. Слияние не выполнялось. Текущий follow-up не заменяет независимый повторный review.

- **R1:** cost/CSV drafts получают уникальный draft id; callback содержит его, а подтверждение, переход к применению всей истории и отмена сверяют его с текущим draft. Проверки покрывают старый preview того же SKU с другой суммой, другой SKU, замену CSV, stale history/cancel и параллельный повтор подтверждения.
- **R2:** обычный период, выбранный SKU, pre-COGS и экспериментальная форма хранят origin tenant/store. Ввод после переключения магазина отменяет форму до расчёта и просит выбрать период заново; проверка подтверждает отсутствие query в новом store.
- **R3:** `AWAITING_DESCRIPTION` разрешён только на стадии описания; регрессия проверяет слишком длинное описание с повторным вводом, preview и сохранение описания.
- **R4:** Performance JSON/auth requests и direct report downloads резервируют каждую реальную HTTP-попытку в общем `PeriodProfitOperationTrace`; timeout ограничен оставшимся общим бюджетом. Регрессии покрывают cached token, auth, 401, 429, download и исчерпание времени.
- **R5:** decision LRU get/expiry/move/store/eviction атомарны под общей блокировкой; контролируемый потоковый тест проверяет одновременный read/eviction и сохранение capacity.
- Targeted regression suite: **74 passed**; `compileall` изменённых production модулей прошёл. Локальный полный pytest не подтверждён: Windows ACL блокирует используемые pytest временные каталоги; предыдущий исходный revision имел зелёный CI, но он не покрывает этот patch.
- Следующие условия закрытия: отправить этот revision в PR #694, получить зелёные Windows/Linux и production Docker checks на его SHA, затем выполнить независимый re-review перечисленных границ. Только после этого другая модель сможет принять решение о слиянии.

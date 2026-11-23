# Журнал выполнения — предварительный FIFO

Основа: `project_brain/LUNA_FIFO_PROVISIONAL_LEDGER_TASK_2026-11-22.md`, PR #740.
Начат: 2026-11-23 (Europe/Moscow).

## PF00 — база и сохранность

- PR #740: открыт; source branch `codex/fifo-provisional-ledger-spec-20261122`; head `49dbbd77ffa10ac0493b1bb4e83acf123b3005cf`; base `main` `b14658c80c9feef4f8595547eb489dde984cb59c`.
- CI PR #740 на точном head: два successful runs `45024247975`, `45024273483` (Windows и full-verification); текущая голова подтверждена диагностикой.
- Выделенная рабочая копия: `C:\Users\gelashvilee\.codex\worktrees\fifo-provisional-ledger-pr-a\fifo-provisional-ledger-spec-20261122`.
- Ветка создана: `codex/fifo-provisional-summary`, начальный SHA `49dbbd77ffa10ac0493b1bb4e83acf123b3005cf`; `git status --porcelain` чист.
- Рабочая копия Desktop `C:\Users\gelashvilee\Desktop\Ai ассистент` и её пользовательские правки не изменялись; рабочий бот не запускался и не останавливался.
- Базовые SHA файлов `data/` из `git ls-tree -r HEAD data`:
  - `data/history.json` — `d537fb1e49b920a91fb6ab7704e91978b670e56b`
  - `data/profiles.json` — `185607c3dd54ca8418934189c688765e58024559`
  - `data/tasks.json` — `38637702206478ab3c08d7ae1c4ac87f1f1c6354`
  - `data/tax_configuration.json` — `60c0f31405fd47d591367b673ffaf1080988caab`
  - `data/users.json` — `dd06c3aa18fcf3510bf39dbf3a1e5b5c8bd81784`
- Команды проверки: `git status --short --branch`, `git rev-parse HEAD`, `git rev-parse origin/main`, `git ls-tree -r HEAD data`; результат соответствует чистой изолированной основе.
- Что не проверялось на этом этапе: поведение кода (это этап PF01+); реальные Ozon/Telegram вызовы запрещены задачей.

## Resume

- Последний завершённый этап: PF00.
- Следующий этап: PF01 — сверить Decision 066/067, руководство FIFO, импорт документов, contracts и действующие точки подключения.
- PR A: ветка `codex/fifo-provisional-summary`, база `49dbbd77ffa10ac0493b1bb4e83acf123b3005cf` (spec PR #740).
- PR B: `codex/fifo-provisional-timeline`, поверх PR A после публикации.
- PR C: `codex/fifo-provisional-saved-estimates`, поверх PR B после публикации.
- Блокеров нет. Неизвестность реального дела владельца не блокирует синтетическую разработку.

## PF01 — архитектурные границы и интерфейсы

- Прочитаны Decision 066/067, `FIFO_COST_CONTRACTS_2026-11-06.md`, руководство владельца по поставкам и спецификация текущего отчётного импортера.
- Подтверждён путь документов: `FifoCostReportImportService` создаёт redacted `ReportEvidence`; существующий `TelegramFifoCostReportImportService` записывает только после явного подтверждения периода/сохранения; `FifoCostTransitionService._read_saved_transition_report` восстанавливает typed evidence; `FifoCostRepository.read_transition_evidence` — scoped read-only список документов по точному case/store/product/offer/SKU.
- `FifoCostTransitionEvidenceService.load` подтверждает только фактический путь и содержит строгие cutoff/finance/movement требования; предварительная оценка не будет его вызывать и не ослабит его gates.
- Проверены `TelegramFifoCostTransitionRuntimeService` callbacks/session/revision, карточка `_show_summary`, `SellerCostTelegramAdapter` и factory wiring. PR A добавит отдельный `TelegramFifoCostProvisionalService` и безопасную ветвь `provisional_*`; фактические prepare/apply, `FifoCostAllocationService`, Period Profit/Return COGS и existing report evidence contracts остаются без изменений.
- Проверка: `rg` по точкам входа и сигнатурам; выборочное чтение contracts/importer/repository/runtime/factory. Результат: новая оценка может читать только подтверждённые отчёты текущего дела; filename candidate/partial report не подходит. Реальные запросы не выполнялись.
- Не выполнялось: тесты кода (этапы реализации впереди); фактический запуск Telegram и проверка Ozon.

## PF02 — тестовые числовые данные

- До реализации выписана synthetic контрольная матрица §4.3: `A=3712`, `L=12959`, `R=12`, `S=5931`, `D=22`, `B=10730`; восемь bucket snapshot `1988/0/2/6/0/0/70/1646`; сумма snapshot `3712`, opening/closing receipts/expenses контроль равен нулю.
- Ожидания заранее закреплены: closing old `[21,21]` → old sold `3669..3703`, new sold `2228..2262`, COGS `110187.30..110403.20`; `[31,31]` сдвигает оба конца вниз на `63.50`; неизвестный close → `0..3724` старых и COGS `86889.15..110536.55`; условная прибыль от базы `130000` → `19596.80..19812.70`.
- Включены негативные контроли: перенос одной единицы между bucket на стыке, неподдержанные категории, несовпадающие period/SKU, невалидный balance и пустое пересечение.
- Контрольные и негативные fixtures созданы в `tests/test_fifo_cost_provisional_summary_service.py`; все synthetic, без рабочих файлов/ID/данных.

## PF03–PF06 — расчётные контракты и контроль

- Добавлены `fifo_cost_provisional_contracts.py`, чистый `FifoCostProvisionalSummaryService` и scoped read-only `FifoCostProvisionalEvidenceReader`. Только полные, owner-confirmed, exact-scope оборотные ведомости; filename candidate, partial, другой case/store/SKU, нестыкованные окна и контрольные ошибки fail closed.
- Реализованы checks восьми bucket на границе дня, балансы всех компонент, неподдержанные L–R/U–Z блокируют деньги; S/AA остаются исключёнными компенсациями. Формулы и Decimal/ROUND_HALF_UP дали матрицу §4.3: `[21,21]` → старые `3669..3703`, новые `2228..2262`, COGS `110187.30..110403.20`; неизвестный closing — широкие границы.
- Проверки: `pytest tests/test_fifo_cost_provisional_summary_service.py tests/test_fifo_cost_provisional_evidence_reader.py -q` — **18 passed** после добавления invalid timezone и ненулевых компенсаций S/AA; `compileall -q` для новых контрактов/сервисов — успешно. При первом прогоне крайняя пара COGS обнаружила ошибочную связку старых/новых границ; формула исправлена и профиль повторно зелёный.
- Не проверялось: сохранённые документы рабочего магазина и внешние источники; ничего из них не читалось.

## PF07–PF08 — предварительный экран в обычном Telegram FIFO-пути

- Добавлен `TelegramFifoCostProvisionalService`, инъекция в общий transition runtime/factory и кнопка карточки партии. Callback проходит обычные owner/tenant/case/revision/flow_revision проверки; выбор отчёта хранит только внутренний отпечаток в ограниченной in-memory сессии.
- В мастер входят выбор однодневного снимка, соседней ведомости движений, подтверждение двух явных допущений, выбор широкого неизвестного остатка или ручного сценарного числа/диапазона и просмотр диапазона COGS. Повтор старой кнопки получает STALE. Импорт используется существующий и только после выбора «Загрузить оборотную ведомость»; частичные и неподтверждённые ведомости исключены reader.
- Никакой вызов factual readiness/prepare/apply; сценарий не пишет кейс, FIFO layers/allocations/events, Period Profit/Return COGS и пока не сохраняет сценарий.
- Импорт FBO CSV и сверка дельты +1 намеренно не входят в PR A: это PF11–PF13 PR B. Матрица A12 будет закрыта там, не имитируется в этой сводной оценке.
- Synthetic ordinary-callback regression проверяет контроль `[21,21]`, границы и отсутствие FIFO writes. Расширенный связанный профиль (provisional summary/evidence/Telegram, production workflow, transition runtime/contracts и оба импортера) — **113 passed in 16.53s**. Предыдущий полный изолированный suite на `f967f7aa` прошёл **5,489 passed in 111.85s**; добавлены две регрессии после него, поэтому повторный full run обязателен. `compileall -q app tests`, `git diff --check` и `git diff --exit-code -- data` успешно проходили до добавленных тестов; после обновления будут повторены.
- Что не проверялось: реальные Telegram callbacks/сообщения и документы владельца (запрещены задачей).

## Resume (состояние после PF10)

- Последний завершённый этап: PF10; PF00–PF10 закрыты.
- PF10 локальная часть завершена на implementation commit `63f60c2a3fe3b00268be1be8a124d7e90cb7f893`: полный suite в disposable worktree без проектного `data/`, только synthetic tax config — **5,491 passed in 110.55s**; `compileall -q app tests` — успешно; `git diff --exit-code -- data` — без изменений; disposable worktree удалён после проверки его точного расположения.
- Linked profile на implementation SHA — **113 passed**. Exact-head CI на PR A SHA `15894e4528db089d0d6e7969fd03b6a88d9206e2` зелёный: Windows/Linux Verify и Docker smoke. Документация включает Decision 068, owner guide, CHANGELOG/CURRENT_STATE/TEST_MAP и этот журнал.
- PR A опубликован как [#741](https://github.com/dopf129-pixel/ai-business-assistant/pull/741), база — PR #740 SHA `49dbbd77ffa10ac0493b1bb4e83acf123b3005cf`; head SHA `15894e4528db089d0d6e7969fd03b6a88d9206e2`. Exact-head CI зелёный: Windows full verification, Linux full verification, Docker build/smoke.
- PF10 завершён. Следующий этап: PF11 — отдельный bounded parser контракта Ozon FBO CSV в зависимой ветке `codex/fifo-provisional-timeline`, созданной от PR A.
- PR B/C до сих пор не опубликованы; blocker отсутствует.


## PF11 — контракт Ozon FBO CSV

- Добавлен отдельный FifoCostProvisionalFboCsvImportService; строгий CSV физических продаж и legacy CSV стоимости не менялись.
- Синтетические входы фиксируют UTF-8/BOM, разделитель ;, точный SKU фильтр, игнорирование дополнительных полей, квоты 10 MiB / 50 000 строк / 1 000 000 единиц, безопасный digest отправления, дедупликацию идентичной строки и блокировку противоречий.
- Даты-время нормализуются к часовому поясу магазина; точность DAY остаётся отличной от INSTANT; неоднозначное и несуществующее DST время и физически невозможный порядок дат отклоняются. Неизвестный статус сводится к UNKNOWN без echo исходной строки.
- Документация: docs/fifo-provisional-fbo-csv-guide.md; в тексте указаны принятые заголовки, временная семантика, приватность и ограничения полноты.
- Проверка: установленный Python проекта, запуск pytest с app в sys.path, tests/test_fifo_cost_provisional_fbo_csv_import_service.py — 6 passed in 0.82s; compileall новых parser/tests — успешно. Сначала один DST regression выявил различие между неоднозначным и несуществующим локальным временем; parser скорректирован, повтор прошёл.
- Не проверялись: worker, Telegram upload/preflight, реальные Ozon CSV и хронологическое использование — это PF12+; рабочих файлов владельца не использовали.

## Resume (актуально после PF11)

- Последний завершённый этап: PF11; PF00–PF11 закрыты в рабочей ветке PR B.
- Следующий этап: PF12 — allowlist нового формата в bounded worker, подтверждение worker output, tenant/case-bound загрузка, preflight до скачивания, TTL/один pending upload и регрессии совместимости с legacy CSV.
- PR A #741: branch codex/fifo-provisional-summary, base PR #740 SHA 49dbbd77ffa10ac0493b1bb4e83acf123b3005cf, exact head 15894e4528db089d0d6e7969fd03b6a88d9206e2; Windows/Linux full Verify и Linux Docker build/smoke зелёные.
- PR B: branch codex/fifo-provisional-timeline, пока локальная, начинается от PR A head 15894e4528db089d0d6e7969fd03b6a88d9206e2; ещё не опубликована. PR C не начат.
- Изменений в пользовательском data не было; реальный бот/API не запускался. Blocker отсутствует.


## PF12 — bounded worker и Telegram upload

- В существующий import worker добавлен отдельный `PROVISIONAL_FBO_CSV` allowlist kind. Worker/client сохраняют общую semaphore/timeout, ограничение исходного файла, environment allowlist и строгую проверку родителем точного manifest. Результат не может включать дополнительные поля или сырой номер отправления.
- Обычный FIFO runtime проверяет owner/tenant/case/revision и выбранную ведомость до загрузки. Preflight размер/тип/активная стадия выполняется до Telegram download. Временная загрузка живёт не более 15 минут и остаётся в памяти текущей сессии. Истечение, смена магазина/дела, неправильная стадия и ожидающий предпросмотр закрывают повторную загрузку без fallback в старые CSV импорты. Переход в импорт физических продаж удаляет только временный FBO выбор.
- Preview считает только целевой числовой SKU и строки DELIVERED с датой доставки внутри окна ведомости, сравнивая их с `redeemed_units` (T). Пример synthetic fixture дал дельту +1, при этом summary сохранил T=5931, контрольные old sold 3669–3703, и factual FIFO write count остался 0.
- Документы обновлены: `docs/fifo-provisional-fbo-csv-guide.md`, `CHANGELOG.md`, `CURRENT_STATE.md`, `TEST_MAP.md`. Нового architectural decision нет; factual import contracts не изменены.
- Проверка: linked parser/worker/adapter/provisional flow/transition runtime/physical-sales evidence profile — **56 passed in 9.77s**; before final commit repeat compileall, `git diff --check`, `git diff --exit-code -- data` and full isolated suite. Один ошибочный запуск включил несуществующее имя теста и не выполнил тесты; корректный linked profile зелёный.
- Реальные файлы владельца, Ozon/Telegram API и рабочий бот не использовались.

## Resume (актуально после PF12)

- Последний завершённый этап: PF12 локально завершён; PF00–PF12 закрыты в PR B worktree. Следующий этап PF13 — диагностическая сверка FBO delivered rows с движениями ведомости без изменения агрегатного T.
- PR A #741: branch `codex/fifo-provisional-summary`, head `15894e4528db089d0d6e7969fd03b6a88d9206e2`, exact-head Windows/Linux Verify and Linux Docker smoke passed.
- PR B `codex/fifo-provisional-timeline`: currently local and unpushed; PF11 parser commit is `353776e379f73467b096e5988979d54a655af996`; PF12 changes remain uncommitted. Publish only after PF19 final verification/review packet.
- PR C not started. No tracked `data/` file changed; no blocker or owner business decision.


## PF13 — FBO / turnover reconciliation

- Расширен временный preview: отдельно считает `DELIVERED` units по дате доставки в окне movement statement, сопоставляет с typed `redeemed_units` T, выводит delta CSV − T и отдельный count по pre-snapshot dispatches, доставленным после snapshot. Этот count разбит на deliveries внутри и после окна; отдельно показываются pre-snapshot shipments, остающиеся со статусом IN_TRANSIT при выгрузке. Delivery date без dispatch date и неизвестный status отражаются как неполнота, без отказа от полезной суммы сравнения.
- Контракт границы: `dispatch.local_date <= snapshot.period_to` классифицируется как отправление до/на снимок; доставка после `snapshot.period_to` попадает в старую группу. Точная линия движения пока не подтверждена одним агрегатным отчётом; никакие данные не доказывают полноту CSV. Показ старой категории не влияет на новую ставку или `T`.
- Synthetic fixture воспроизводит: 5 932 доставок внутри окна, T=5 931, delta +1; 1 319 старых dispatches доставлены в окне; 2 старых dispatches доставлены после окна; 19 old dispatches in transit at export; дополнительно по одной строке с missing dispatch date и unknown status. Preview проходит, T=5931 остается у summary model, factual writes=0.
- Проверка до documentation-only updates: `tests/test_fifo_cost_provisional_fbo_telegram_flow.py tests/test_fifo_cost_provisional_fbo_csv_import_service.py tests/test_fifo_cost_provisional_summary_service.py` — **25 passed in 1.57s**; расширенная FBO Telegram flow file после усиления fixture — **3 passed**. Повторить весь связанный профиль и compile/data checks перед фиксацией.
- Обновлены `docs/fifo-provisional-fbo-csv-guide.md`, `CHANGELOG.md`, `CURRENT_STATE.md`, `TEST_MAP.md`. Изменений в factual/import services и `data/` нет. Реальные отчёты и API не использовались.

## Resume (актуально после PF13)

- PF00–PF13 завершены локально в зависимом PR B worktree; следующая стадия PF14 — нормализованные события и отдельный optional movements CSV contract, строго read-only.
- PR A #741 exact head `15894e4528db089d0d6e7969fd03b6a88d9206e2` имеет зелёные Windows/Linux Verify и Linux Docker smoke.
- PR B branch `codex/fifo-provisional-timeline`, current head после PF12 commit `2463cfcaadd2f7d65dd2571d1d5403cbaa04ffbec`; PF13 локально изменён и не закоммичен/не опубликован. PR C не начат.
- No `data/` modifications; no live bot/API. Неразрешённых блокеров нет.

- Final PF13 linked verification: **72 passed in 9.90s** across FBO parser/worker/adapter/Telegram, summary model, transition runtime, and physical-sales import/evidence suites. `compileall -q app tests`, `git diff --check`, and `git diff --exit-code -- data` passed after docs were updated.

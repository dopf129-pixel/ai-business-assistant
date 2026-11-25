# Журнал выполнения — предварительный FIFO

## Проверка исправлений review — FIFO история с постраничным просмотром (2026-11-25)

- В списке переходов SKU добавлены страницы по 20 записей с кнопками «Новее» и «Раньше». Доступ к сохранённым оценкам использует те же case-scoped callbacks и сохраняет read-only поведение.
- Добавлена регрессия на 21 переход: после очистки временной сессии обычная карточка SKU открывает страницу 1, переход «Раньше» показывает запись 21, а сохранённая оценка открывается и отображает период.
- Результат exact-head CI будет зафиксирован в описании PR после завершения проверки на итоговом SHA.

## Проверка исправлений review — 2026-11-25

- Первый exact-head CI PR C `f80757a57663beafc1d23a082aa0354b6539b20a` завершился ошибкой сбора тестов: в новой регрессии генератор `next(...)` требовал явных скобок. Исправлена форма генератора и удалена запятая, которая превращала выбранную кнопку в кортеж; функциональные тесты ещё не выполнялись на этом SHA. Новый CI запускается на следующем коммите.


# 2026-11-25 — Provisional FIFO review fixes (PR B/C)

- PR B now classifies old/new sales by source layer and compares the replayed old-layer closing balance with the owner's exact/range assumption; conflicting results withhold modeled money.
- Valid typed closing-old input clears stale timeline output; invalid input preserves the current scenario.
- PR C exposes the saved-estimate history entry from the regular FIFO SKU card. APPLIED/CANCELLED cases reopen read-only through the production SellerCostTelegramAdapter path; callback tickets bind to the listed case revision.
- Regressions cover returned old layers, equal cost rates, typed input freshness, post-restart APPLIED/CANCELLED history access, stale case revisions, and zero writes.

Основа: `project_brain/LUNA_FIFO_PROVISIONAL_LEDGER_TASK_2026-11-22.md`, PR #740.
Начат: 2026-11-23 (Europe/Moscow).

## Resume — состояние после PF26 (публикация и первый exact-head CI завершены)

- Последний завершённый этап: PF26, публикация PR C и exact-head hosted CI. После этой документационной записи проверить новый final SHA PR C: этот коммит сам запускает повторный exact-head CI.
- PR A #741: branch `codex/fifo-provisional-summary`, head `15894e4528db089d0d6e7969fd03b6a88d9206e`, exact-head CI run `45142413339` green. PR B #742: branch `codex/fifo-provisional-timeline`, head `9f5aa5cbea5f990beb782fa45791afcc94e59af4`, exact-head CI run `45172484489` green. PR C branch `codex/fifo-provisional-saved-estimates` is based on exact PR B head.
- PR C #743 package head before this follow-up record: `5ec77fa3e7c94535e288d5a6c04134688d6ce07c`; exact-head Actions run `45193059919` green (Windows and full verification); duplicate run `45192990093` also green. PR A/B remain open and unmerged.
- PR C local code/test SHA `61480ae48e75e3ffedce87c62d23bb0363b3ad5b` passed the isolated full suite: **5,579 passed in 97.95s**. The current documentation-only commit requires one final hosted check on its own SHA.
- PR C branch `codex/fifo-provisional-saved-estimates` is based on exact PR B #742 head `9f5aa5cbea5f990beb782fa45791afcc94e59af4`. PF20 changed FIFO-owned schema v20 and synthetic tests only; `Planning` metadata and tracked `data/` remain unchanged. Its focused profile was **54 passed**. PF21 commit `201853c4017f8dd4a09b8393e0366b29d0e18a3d` adds fresh, idempotent provisional estimate saving and strict model-specific payload validation; linked profile: **66 passed in 4.73s**.
- PF22 adds exact-scope paginated history reads, a Telegram detail view that can reopen saved records after a new session, source freshness messaging, and conservative model comparison. Compatible ranges use `[new_low - old_high, new_high - old_low]`; different source coverage is disclosed; incompatible dimensions or missing timeline amounts withhold a combined delta. Linked history/timeline/FBO/repository/schema/backup profile: **69 passed in 4.70s**. `compileall -q app tests`, `git diff --check`, and `git diff --exit-code -- data` passed.
- PF23 adds manually owner-confirmed conditional pre-tax profit for the exact selected SKU/period/redeemed-unit scope. Formula `base − COGS` reverses interval endpoints; negative bases are accepted, automatic store-profit substitution is prohibited, and history comparison withholds deltas across different profit perimeters. Saved payload v2 preserves legacy v1 rows and validates scope plus arithmetic. Final linked profile after provenance guard: **76 passed in 5.02s**; `compileall -q app tests`, `git diff --check`, and `git diff --exit-code -- data` passed.
- PF24 strengthens the full synthetic Telegram journey: estimate before base remains without profit, entry shows gross COGS and manual-source warning, profit appears only after owner confirmation, saved estimate survives a new session, all screens stay below Telegram's 4,000-character limit, and only the dedicated estimate repository receives a write. The factual case remains revision 1; transition writes are zero and production apply/Period Profit services are absent. Final linked profile: **76 passed in 5.02s**; compile, diff check and tracked `data/` equality passed.
- PF25 updates the owner guide, Decision 068, CHANGELOG, CURRENT_STATE and TEST_MAP. Acceptance mapping: A01–A13 in PR A packet; B01–B16 in PR B packet; C01–C08 in PR C regressions and PF20–PF24 tests; C09's no-apply/gap behavior covered synthetically across the independent summary/FBO/timeline paths. The real owner case remains deliberately unvalidated because real Ozon/Telegram requests and owner files are excluded.
- Known limit: manually entered finance base cannot be independently validated for gross/net semantics or source dates; bot now states this before owner confirmation. If the external base does not match SKU/period/redeemed-unit perimeter, owner must not confirm it. No tax recalculation is implemented.
- PR C #743 is open with its independent review packet and green hosted CI on `5ec77fa3`; recheck exact-head CI after this progress update. No merge, deployment, live bot, Ozon or Telegram request was performed.

## PF25 — document owner flow, boundaries, acceptance map and limits

- Updated `docs/fifo-provisional-summary-owner-guide.md` with the manual-base contract, exact SKU/period/redeemed-unit perimeter, formula/range endpoint order, negative-base handling, explicit confirmation, save/reopen behavior and comparison rules. It clearly states the bot cannot independently validate a manual base against a separate finance report.
- Updated Decision 068 index/detail with the new estimate-vs-fact boundary: confirmed profit remains nested in an immutable provisional estimate and is not sent to tax, FIFO, Return COGS or Period Profit. Updated `CHANGELOG.md`, `CURRENT_STATE.md` and `TEST_MAP.md` to reflect PF23–PF24 behavior and exact local test results.
- Acceptance mapping: A01–A13 are in PR A review packet; B01–B16 are in PR B review packet; C01–C08 are covered in PF20–PF24 repository/Telegram/migration/backup regressions. C09's incomplete-return/+1 scenario is represented by synthetic summary and FBO comparison tests; actual owner files and live sources were not used. The full per-case evidence table will be included in the final PR C review packet.
- Residual product-data limitation: owner-entered base comparability is an explicit owner assertion; no external finance report is independently cross-matched, and this feature does not recalculate tax or financial return reversal. The bot discloses these limits before confirmation.
- Linked local suite after the final PF25 guard: **76 passed in 5.02s**. `compileall -q app tests`, `git diff --check`, and `git diff --exit-code -- data` passed. No factual data, live service or running bot was used.

## PF26 — isolated full-suite verification and review handoff

- The first disposable full-suite attempt at `49a29d390ba72f0f454f3b6b06cf4b798391b6b7` reported **5,561 passed, 18 failed in 106.53s**. Fourteen failures were stale test expectations for schema v19 after the additive v20 table; four were caused by test-runner tax environment variables that differ from the CI contract. The implementation tests were not changed to hide product failures.
- Updated synthetic migration tests to assert schema v20 and its preview table, and adjusted the v12 teardown fixture to remove the two v20 triggers/table before dropping their parent tables. The focused migration/checkpoint profile then passed **29 tests in 2.48s**.
- On exact code/test SHA `61480ae48e75e3ffedce87c62d23bb0363b3ad5b`, reran the complete repository suite in a disposable clean copy without `.env` or owner `data/`; only a synthetic USN income tax policy was present: **5,579 passed in 97.95s**, exit 0. `compileall -q app tests`, test DB initialization, `git diff --check`, and tracked `data/` equality passed. The disposable copy was not copied back into the project.
- Added `FIFO_PROVISIONAL_LEDGER_PR_C_REVIEW_PACKET_2026-11-23.md` with PR dependency, exact tested code SHA, C01–C09 evidence mapping, synthetic transcript summary, architecture boundary, data preservation and residual owner-data limitations. PR C publication and exact-head CI are the remaining PF26 packaging actions.
- No owner files, API credentials, live Ozon/Telegram calls, production bot, merge or deployment were used.

## PF23 — conditionally calculate profit from an owner-confirmed base

- Added a bounded money-input step and a separate confirmation screen tied by an opaque ticket to owner/store/SKU/case revision, selected model, period, redeemed units, evidence and the exact estimate fingerprint. The screen states the financial perimeter and shows the gross COGS range before confirmation. A negative base remains a valid numeric value.
- Conditional profit is shown only after explicit confirmation. It is labeled conditional and before tax; its base is described as owner-entered, before product COGS/tax and return reversal. Bounds use `base - cogs_high` for the low result and `base - cogs_low` for the high result. The value is never auto-filled from store-wide profit or another period. Profit comparison requires the same currency, period, redeemed-unit count, perimeter, tax stage and return-reversal rule.
- Persisted the confirmed value inside a v2 aggregate-only saved-preview payload. Repository validation checks exact allowlisted keys, period/scope/unit count, cents precision, supported provenance and recomputed formula. Existing schema-v1 saved rows remain readable. No factual FIFO, COGS, return-cost or Period Profit write path was added.
- Regressions cover the accepted 130,000 ₽ base and expected 19,596.80–19,812.70 ₽ interval, visible COGS before confirmation, negative base calculation, tampered-formula rejection, and withheld comparison deltas when return reversal or tax stage differs. The synthetic Telegram path confirms, saves, reopens, and asserts zero factual transition writes. Linked profile: **76 passed in 4.96s**. Compilation, diff check and tracked `data/` equality passed.
- `CHANGELOG.md`, `CURRENT_STATE.md` and `TEST_MAP.md` remain for the PF25 documentation pass after PF24. No architectural decision changed; no live service or bot was used.

## PF24 — verify the full calculator flow without factual writes

- Expanded the synthetic Telegram integration test across the existing session: load the reports and owner assumptions, calculate the provisional range, enter a manual base, explicitly confirm, save, then open the saved record in a fresh session.
- Added explicit assertions that no conditional profit is shown before the owner confirms; the confirmation displays the COGS interval; after confirmation the exact expected profit interval is shown; no apply action is offered; each message remains below 4,000 characters; only the separate estimate append is written; case revision stays unchanged; transition writes remain zero; and production apply/Period Profit services are not connected.
- Command: `PYTHONPATH=app python -m pytest tests/test_telegram_fifo_cost_provisional_service.py tests/test_fifo_cost_provisional_fbo_telegram_flow.py tests/test_fifo_cost_provisional_preview_repository.py tests/test_fifo_cost_repository.py tests/test_bot_backup_service.py tests/test_fifo_cost_provisional_timeline_service.py -q` using the existing project virtual environment — **76 passed in 5.03s**. `compileall -q app tests`, `git diff --check`, and `git diff --exit-code -- data` passed.
- This is synthetic test coverage only; no live bot, Telegram/Ozon calls or owner data were used. No runtime architecture changed in PF24.

## PF21 — save only a fresh provisional estimate

- Production composition injects the existing FIFO repository into the provisional scenario service. A save button is shown only for `SUMMARY_RANGE` or a final `TIMELINE_MODEL`; timeline gaps can save only the separate aggregate summary.
- Save callback re-reads the exact case and selected complete reports, recomputes the summary, and for a timeline result re-reads confirmed physical-sales evidence and verifies the still-current, non-expired FBO/owner-movements inputs. The canonical input fingerprint includes case/identity/revision, model policy, rates, period, assumptions, selected evidence digests and timeline source-presence/coverage state. The button ticket is owner/store/SKU/case/revision/flow scoped by the existing runtime and carries that fingerprint.
- Repository append runs `BEGIN IMMEDIATE`, rechecks exact owner/tenant/store/product/offer/SKU and current editable case revision, validates the allowlisted aggregate-only payload, and appends to the v20 table. A key `prov1_<input fingerprint>` makes a same-input retry return the existing row. Changed input, stale case/source, invalid scope, closed case, payload or 100-row limit fails without evicting records. No factual FIFO prepare/apply or COGS/Period Profit write is called.
- Added repository API and regressions for idempotent append, conflicting reuse, wrong identity, stale revision, closed case, unapproved payload, incomplete model result, mismatched method and non-ISO date. Ordinary Telegram regression saves a synthetic estimate, confirms only digest references are stored, and rejects an old save callback after the selected report disappears. Linked profile: **66 passed in 4.73s**; `compileall`, diff check and tracked data diff passed.
- Updated Decision 068 implementation note, owner guide, CHANGELOG, CURRENT_STATE and TEST_MAP. No production data, real Ozon/Telegram calls or working bot were used. PF23 conditional profit remains pending.

## PF22 — scoped saved-estimate history and comparison

- Added `read_provisional_preview_history` with exact case/owner/tenant/store/product/offer/SKU filtering, stable newest-first ordering, bounded page size/offset and no owner/tenant fingerprint fields in rows. Invalid/cross-scope reads fail closed; stored payloads are revalidated before history is returned.
- The ordinary provisional screen exposes «История оценок» even if current source reading fails. History is loaded from the durable repository, not the short-lived calculation flow. The detail screen shows periods, method/policy, rates, assumptions, redeemed units, source-count and a freshness explanation; raw file data and fingerprints stay hidden.
- Comparison requires same case scope (from repository query), model kind, currency, exact period, method, policy version and redeemed-unit basis S. Compatible cost intervals use `[new_low - old_high, new_high - old_low]`; source coverage difference is shown as counts. Incompatible cases and missing timeline monetary totals show both records without a delta. No comparison changes the active factual FIFO or profit.
- Tests cover repository pagination/order and tenant/identity isolation, reopening a saved estimate in a newly initialized Telegram session, interval arithmetic, different coverage, and withholding deltas for changed period or S. `PYTHONPATH=app python -m pytest tests/test_telegram_fifo_cost_provisional_service.py tests/test_fifo_cost_provisional_fbo_telegram_flow.py tests/test_fifo_cost_provisional_preview_repository.py tests/test_fifo_cost_repository.py tests/test_bot_backup_service.py -q`: **69 passed in 4.70s**. `compileall`, `git diff --check`, tracked `data/` equality passed.
- Docs updated: owner guide, CHANGELOG, CURRENT_STATE and TEST_MAP. No architectural decision changed. No owner data, live API, working bot, merge or deployment was used.

## PF20 — append-only provisional estimate storage

- Added FIFO schema v20 table `fifo_cost_provisional_previews`. Each row binds owner/tenant/store/product/offer/SKU to an exact transition case revision, stores a bounded payload plus fingerprints and an idempotency key, and rejects duplicate keys, scope/revision mismatch, UPDATE/DELETE, payloads above 64 KiB, or more than 100 rows per case. Overflow never evicts prior rows.
- Added the v19→v20 migration regression with existing case/revision rows and `Planning` sentinels. The upgrade creates only the additive FIFO table and preserves `planning_schema.version=12` and `PRAGMA user_version=41`.
- Added backup/archive verification/dry-run/full-restore coverage proving a synthetic saved estimate survives restore with FIFO v20, Planning v12 and user_version 41. The production backup service requires no code change because its SQLite snapshot includes the new table automatically.
- PF20 profile: `PYTHONPATH=app python -m pytest tests/test_fifo_cost_repository.py tests/test_bot_backup_service.py -q` — **54 passed in 3.54s**. `python -m compileall -q app tests`, `git diff --check`, and `git diff --exit-code -- data` passed. Development-only fixture assertions were corrected before the final run; no product defect remained.
- Updated Decision 068 implementation note, owner guide boundary, CHANGELOG, CURRENT_STATE and TEST_MAP. No real owner data or live integrations were used.

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

## PF14 — normalized event sources and owner movement template

- Added `fifo_cost_provisional_timeline_contracts.py`, `fifo_cost_provisional_movements_import_service.py`, and `fifo_cost_provisional_timeline_normalizer.py`. Event inputs carry exact case/SKU scope digests, store-local date and `DAY`/`INSTANT` precision, positive bounded quantity, safe event/source keys and hashed posting keys; raw IDs and free-text references do not survive parsing.
- Added header-only `docs/templates/fifo_provisional_movements_template.csv` for the six owner event kinds. The parser enforces UTF-8/BOM, exact header, numeric target SKU, 10 MiB / 50,000-row / 1,000,000-unit limits, timestamp/DST validity, unique event references, numeric source-row locators, and per-event allowed/required fields. A physical event before model start is not replayed twice; an opening transit link must exactly match the FBO posting and dispatch timestamp/date and cannot exceed its quantity.
- Added a scoped read-only method for the existing confirmed physical-sales evidence and injected it into the provisional reader. Only exact-case, complete owner-confirmed turnover/stock documents are exposed; duplicate report versions over the same window create a conflict. Report totals remain anchors, never time-stamped events. Physical sale rows remain day-precision and deduplicate against identical FBO posting/quantity/day; mismatches remain a gap.
- Updated FBO CSV guide, `CHANGELOG.md`, `CURRENT_STATE.md`, and `TEST_MAP.md`. `data/` was not changed; no factual FIFO write, bot launch, or live request occurred.
- Verification command: project Python with `app` on `sys.path`, pytest on `test_fifo_cost_provisional_movements_import_service.py`, `test_fifo_cost_provisional_timeline_normalizer.py`, `test_fifo_cost_provisional_evidence_reader.py`, `test_fifo_cost_provisional_fbo_csv_import_service.py`, `test_fifo_cost_provisional_fbo_telegram_flow.py`, `test_fifo_cost_transition_evidence_service.py`, and `test_fifo_cost_transition_production_workflow.py` — **36 passed in 10.36s**. `compileall -q app tests`, `git diff --check`, and `git diff --exit-code -- data` passed.
- Not verified yet: timeline replay, Telegram upload for the optional owner-movements template, full repository suite, PR B CI, and real owner documents. These remain later task stages; aggregate controls do not establish event completeness.

## PF15 — finite provisional FIFO replay

- Added `FifoCostProvisionalReplayService` as a pure scenario-only kernel. It creates a finite opening available layer at the old rate, finite new receipt layers at the new rate, and distinct held layers for receipts not yet available. Exact pre-window `OPENING_TRANSIT_LINK` events create a separate old-rate posting reserve bounded by the corresponding hashed FBO posting capacity; they do not consume opening available stock.
- `BUYER_DISPATCH` consumes available layers in FIFO order and can split one posting across rates. The reserve contains exact layer, quantity, and amount lines; dispatch COGS remains `0.00`. No `BUYOUT`, returns, release-hold, or non-sale-outflow is guessed in PF15; unsupported kinds fail closed pending PF16/PF17.
- Identical normalized duplicate events are idempotent; changed payload under the same event key, duplicate posting assignment, unknown capacity, scope/SKU mismatch, outside-window events, insufficient stock, invalid money, and unresolved event ordering fail closed. Same-day DAY precision is not used to invent an order; distinct explicit instants are ordered by UTC after checking their store-local dates.
- Normalizer now returns an immutable map of exact FBO posting capacities keyed only by existing SHA-256 posting digests. The pure service validates those capacities before applying an opening link or dispatch.
- Added `tests/test_fifo_cost_provisional_replay_service.py` covering split allocation, zero COGS, opening reserve, duplicate behavior, negative stock, capacities, held zones, order ambiguity, exact instants, scope/window, unsupported events, and money validation. Normalizer regression asserts hash-only posting capacities.
- Documentation updated: FBO scenario guide, CHANGELOG, CURRENT_STATE, TEST_MAP, and implementation note under Decision 068. No files under tracked `data/` changed; no production bot, live APIs, or Telegram requests were used.
- Verification command: project Python with `app` on `sys.path`, pytest on `test_fifo_cost_provisional_replay_service.py`, `test_fifo_cost_provisional_timeline_normalizer.py`, and `test_fifo_cost_provisional_movements_import_service.py` — **30 passed in 0.90s**. `compileall` for `app` and `tests` passed; `git diff --check` passed; `git diff --exit-code -- data` passed.
- Implementation commit: `a94f818eb2290400ccec48212b5bdc30a90ac937` (`Add provisional finite-layer FIFO replay`) on `codex/fifo-provisional-timeline`; working tree clean after the code commit. This is not a hosted PR head and does not yet have hosted CI.
- One early targeted run exposed a test-fixture day/date mismatch; the fixture was corrected to derive store-local date from explicit instants. Final repeated profile above is green.
- Not verified yet: return/buyout replay, holds release, non-sale movement ledger, source completeness/balance status, normal Telegram timeline display, full suite, PR B hosted CI, and owner documents. These remain PF16–PF19 or later.

## PF16 — buyout, cancellation, and sale-return replay

- Extended the pure replay with exact posting-reserve-to-buyout transition. A buyout must match the full remaining reserve quantity and can be recorded once; its line allocations move to a separate bought-out journal and add gross COGS. Dispatch still contributes zero COGS; gross buyout COGS remains gross after returns, while `financial_cogs_reversal_rub` remains zero absent a separately confirmed financial event.
- `NON_BUYOUT_RESTOCK` consumes only the open reservation. Full restock restores each exact source layer; partial restock is allowed only when all remaining reserved units belong to one layer. Partial cancellation from a mixed-rate reservation returns `TIMELINE_RETURN_ALLOCATION_AMBIGUOUS` instead of guessing which units came back. A non-resellable physical return stays in a separate held-return bucket.
- `SALE_RETURN_RESTOCK` requires a prior exact posting buyout. Partial return allocation walks the saved buyout lines in reverse order (last consumed first), enforces cumulative returned quantity, and restores each resellable slice to its original source layer and FIFO priority. Non-resellable slices stay held. Identical event replay is idempotent; duplicate buyouts, unlinked/over-quantity returns, mismatched buyout quantity, and invalid cancellation lifecycle fail closed.
- Fixed the opening-link completeness condition: a posting dispatched before model start but cancelled with an owner-confirmed return in the window must still be linked to the opening `buyer_delivery` reserve. Without it, the timeline is incomplete; with an exact link/quantity/date, normalized opening and restock events are available to the replay.
- Added synthetic B04–B07 regressions: old transit posting bought out after new receipts without double-consuming opening available stock; mixed old/new dispatch COGS only at buyout; partial returned new-cost units first; repeated and excessive returns; cancellation/resellable vs held; and ambiguous partial multi-layer cancellation.
- Documentation updated: FBO scenario guide, CHANGELOG, CURRENT_STATE, TEST_MAP, and Decision 068 implementation note. No tracked `data/` files changed; no bot, API, Telegram, or owner records were used.
- Verification command: project Python with `app` on `sys.path`, pytest on `test_fifo_cost_provisional_replay_service.py`, `test_fifo_cost_provisional_timeline_normalizer.py`, and `test_fifo_cost_provisional_movements_import_service.py` — **40 passed in 0.86s**. `compileall` for `app` and `tests` passed; `git diff --check` passed; `git diff --exit-code -- data` passed.
- Implementation commit: `59c5f674317fd4d940e87989515fa0535a95cd46` (`Add provisional buyout and return replay`) on `codex/fifo-provisional-timeline`; working tree clean after the code commit. It is still a local PR B head without hosted CI.
- An early test run identified three fixture/expectation issues (duplicate returns at an identical instant correctly trigger ordering ambiguity, one held-zone quantity expectation, and a 10-column CSV fixture); the fixtures/expectations were corrected and the final linked profile is green. No implementation defect remained.
- Not verified yet: RELEASE_HOLD and NON_SALE_REMOVE replay, mixed-event balance checks, source coverage/final timeline status, normal Telegram timeline rendering, full suite, PR B hosted CI, and owner reports; these remain PF17–PF19 or later.

## PF17 — held zones, non-sale movements, and gap-safe prefix

- Replay accepts owner-confirmed opening held balances by exact stock zone (excluding available and buyer_delivery); these finite opening layers keep the old cost. New held receipts and non-resellable physical returns retain their original layer and effective-date priority.
- RELEASE_HOLD transfers only a quantity present in its exact held zone. It restores the source cost/FIFO layer and does not create units. Buyer-delivery releases/removals without a posting transition are rejected. Partial movement from mixed-cost held layers is blocked when the input cannot identify which cost slice moved.
- NON_SALE_REMOVE uses FIFO for available stock and a separate known-cost ledger for held stock; it records quantity/value apart from gross buyout COGS. Negative available, unavailable held quantity, lifecycle conflicts, and unresolved cost slices fail closed.
- The replay now returns only events before the first invalid or ambiguous event and exposes supplied/unprocessed event counts. Equal exact instants and mixed DAY/INSTANT groups stop before the disputed group; tail events cannot patch the result. Static lifecycle validations were moved into chronological replay so an earlier safe prefix can be retained.
- Added B08/B12-oriented cases: a 70-unit opening return hold releases one unit while 69 remain held and total units stay 70; held new-cost receipts and non-resellable sale returns release to availability with their original layers. Added FIFO non-sale write-off, mixed-cost ambiguity, over-release, buyer-delivery linkage, same-time ordering, negative-stock tail, and posting lifecycle regressions.
- Files changed: replay service/contracts, replay tests, owner guide, CHANGELOG, CURRENT_STATE, TEST_MAP, this journal, and Decision 068 implementation note. No tracked runtime data or factual FIFO/finance/Period Profit records changed.
- Implementation commit: 4e9236be (Add provisional held-stock replay) on codex/fifo-provisional-timeline. The implementation commit is clean; this journal checkpoint records its verified state.
- Verification: tests/test_fifo_cost_provisional_replay_service.py — **39 passed**; linked replay/normalizer/movement/FBO/evidence/workflow profile — **76 passed in 10.62s**; compileall -q app tests, git diff --check, and git diff --exit-code -- data — PASS. All replay fixtures are synthetic.
- Not verified: source coverage, eight-bucket closing reconciliation, owner evidence, normal Telegram TIMELINE_MODEL/TIMELINE_GAP presenter (PF18), full test suite and hosted PR B CI (PF19). No Ozon/Telegram calls or production bot use.

## PF18 — gated timeline presenter on the ordinary Telegram path

- Added `FifoCostProvisionalTimelineService`, a read-only final gate over the exact selected snapshot/movement reports, accepted FBO CSV, optional owner movement CSV and exact-case confirmed physical-sales evidence. `TIMELINE_MODEL` is returned only after owner coverage confirmation, exact selected-window FBO coverage, valid report boundaries, complete event replay, opening buyer-delivery links, event totals matching independent turnover controls, and all eight ending stock buckets reconciling.
- The normal scenario card now offers a bounded owner-movements CSV upload and a separate completeness confirmation. The parser runs through the existing limited worker with parent-side manifest revalidation, file/timeout bounds and scoped 15-minute previews; raw references/IDs are not rendered or saved.
- `TIMELINE_GAP` presents only safe progress counts. It withholds partial timeline COGS/sold units; an available `SUMMARY_RANGE` is shown below as an independent model. Replacing or reconfirming either CSV clears the previous completeness confirmation and timeline result. No factual FIFO, COGS, finance or Period Profit write is added.
- Code commit: `f247ff04` (`Present gated provisional FIFO timeline in Telegram`) on `codex/fifo-provisional-timeline`.
- Updated the provisional FIFO owner guide, CHANGELOG, CURRENT_STATE, TEST_MAP and Decision 068 implementation note. Tracked `data/` is unchanged; no owner documents, live Ozon/Telegram requests or production bot were used.
- Verification command (project Python with `PYTHONPATH=app`): pytest over `test_fifo_cost_provisional_timeline_service.py`, `test_fifo_cost_provisional_replay_service.py`, `test_fifo_cost_provisional_timeline_normalizer.py`, `test_fifo_cost_provisional_movements_import_service.py`, `test_fifo_cost_provisional_evidence_reader.py`, `test_fifo_cost_provisional_fbo_csv_import_service.py`, `test_fifo_cost_provisional_fbo_telegram_flow.py`, `test_telegram_fifo_cost_provisional_service.py`, `test_fifo_cost_report_import_worker_client.py`, `test_fifo_cost_transition_evidence_service.py`, and `test_fifo_cost_transition_production_workflow.py` — **97 passed in 12.81s**. `compileall -q app tests`, `git diff --check`, and `git diff --exit-code -- data` passed.
- The synthetic incomplete-history Telegram case stays `TIMELINE_GAP` and retains the separate aggregate summary. No full repository suite or hosted CI was run yet; these are PF19.

## Resume (актуально после PF18)

- PF00–PF18 are complete on PR B branch `codex/fifo-provisional-timeline`; next is PF19: run the isolated full suite, recheck exact PR A/PR B bases, prepare the architecture/review packet, publish PR B and obtain green CI on its exact head.
- PR A #741: `codex/fifo-provisional-summary`, head `15894e4528db089d0d6e7969fd03b6a88d9206e2`; exact-head Windows/Linux Verify and Linux Docker smoke passed. PR B is still local and is based on PR A. Latest PR B code commit is `f247ff04`; this checkpoint will follow it.
- PR C has not started. Tracked `data/` remains unchanged. No production bot or live Ozon/Telegram requests were used. No unresolved blocker.

## PF19 — PR B local full-suite and review preparation

- Full isolated suite ran from a disposable copy of implementation/docs SHA `520eed936328793bd62fda3df621ad06b965cea4`: **5,565 passed in 95.75s** on Windows/Python 3.12. The copy was created from the tracked git tree, excluding `.env` and project `data/`; only a synthetic `data/tax_configuration.json` (USN_INCOME, 6%, minimum 1%) was added inside the copy. No owner data was read or changed.
- Initial harness attempts were invalid, not product failures: one did not populate tracked files due to using the wrong Git listing command; a second exposed `app/` imports correctly but set tax environment variables globally inside pytest, conflicting with tests for a missing policy. The corrected run used `git ls-tree` and a synthetic policy file; all 5,565 tests passed.
- Separate worktree checks: `compileall -q app tests`, `git diff --check`, `git diff --exit-code -- data` passed. All five `data/` Git blob IDs match the PF00 baseline exactly. PR B merge-base is PR A #741 head `15894e4528db089d0d6e7969fd03b6a88d9206e2`.
- Rechecked PR A exact-head GitHub run `45142413339`: Windows verification and Linux full verification/Docker build/runtime smoke all succeeded. Prepared `FIFO_PROVISIONAL_LEDGER_PR_B_REVIEW_PACKET_2026-11-23.md` with architecture boundary, file ownership, checks, limitations, and review classification.
- PR B is not yet published at this checkpoint; hosted CI on its final public SHA remains pending. No production bot/live API/Telegram operation occurred.

## Resume (актуально после PF19 local verification)

- PF00–PF19 local implementation/review preparation are complete; next action is to publish `codex/fifo-provisional-timeline` as PR B targeting PR A branch `codex/fifo-provisional-summary`, then wait for and inspect exact-head CI before closing PF19.
- PR A #741 head `15894e4528db089d0d6e7969fd03b6a88d9206e2`, exact-head run `45142413339` green. PR B current pre-packet SHA was `520eed936328793bd62fda3df621ad06b965cea4`; the packet/journal commit will advance the final head and CI must run on that SHA.
- PR C has not started. Tracked data matches PF00 exactly; no owner documents, real Ozon/Telegram request, bot start, merge, or deployment. No unresolved blocker.

## Resume (актуально после PF17)

- Последний закрытый этап: PF17. Следующий: PF18 — подключить безопасный presenter TIMELINE_MODEL/TIMELINE_GAP в обычный FIFO Telegram-путь; сводный диапазон остаётся отдельной моделью при пробеле.
- PR A #741: `codex/fifo-provisional-summary`, head `15894e4528db089d0d6e7969fd03b6a88d9206e2`; hosted exact-head Windows/Linux Verify and Linux Docker smoke passed.
- PR B: `codex/fifo-provisional-timeline`, based on PR A head; PF14 implementation `502f376a` plus checkpoint `8e101fd4`; PF15 implementation `a94f818eb2290400ccec48212b5bdc30a90ac937`; PF16 implementation `59c5f674317fd4d940e87989515fa0535a95cd46`. Keep the branch local until PF19; PF17 implementation `4e9236be`. Keep the branch local until PF19.
- PR C not started. Tracked `data/` unchanged. No live Ozon/Telegram calls and no production bot launch. Blocker none.


## Review follow-up — 2026-11-25

- PR B review fixes are published at 1248617c70d95de92b37129157abae138153160e; hosted Verify run 45571794948 passed.
- PR C follow-up makes saved history accessible from READY_TO_CONFIRM, APPLIED and CANCELLED case cards with no transient calculator flow. Read-only terminal navigation returns to the case card and cannot continue to calculation.
- Integrated PR C exact-head CI remains pending until its merge commit is published. No merge into main, deployment, production bot launch or live Ozon/Telegram request was performed.


## Exact-head review verification — 2026-11-25

- PR B #742 head 1248617c70d95de92b37129157abae138153160e passed Verify run [45571794948](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/45571794948): Windows and Linux full test jobs succeeded; the Linux job built the production Docker image and passed runtime smoke.
- PR C code/test head 989f0520ae4d803e1ce628c72048742082df0603 passed Verify run [45575002866](https://github.com/dopf129-pixel/ai-business-assistant/actions/runs/45575002866): **5,588 passed** on Windows (281.55s) and Linux (62.66s), and Linux Docker build/runtime smoke passed. The first Windows attempt had one unrelated collision in a randomized callback-token assertion (5,587 other tests passed); rerunning the same job and SHA passed.
- This commit records verification facts only. It advances the PR C SHA; GitHub exact-head verification must pass again before declaring the branch ready. No data, live API, bot, merge, or deployment was used.

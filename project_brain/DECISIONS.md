# Architecture Decisions

## Decision 061 — unit price tariff and observation persistence

Date: 2026-10-27  
Topic: persist price tariff assumptions and observation evidence without creating another accounting store.

Keep `UnitPriceScenarioService` and active-store `TaxService` as the only forward calculation. Reuse tenant `ozon_assistant.db` and `PlanningWorkspaceRepository` as the single schema/migration/transaction owner for additive tariff and observation records; application services validate and orchestrate, while resolvers/comparisons remain pure. Manual tariff profiles are scoped to exact owner/store/product/offer/SKU/scheme/effective date and frozen plan revisions carry the exact profile revision/rate resolved for each price. A current-price fee point never implies a range. Observations are owner-triggered, read-only, completed-day evidence; no scheduler, historical price inference or Ozon price mutation is allowed. Additive migrations, strict allowlists, idempotency/CAS, quotas, frozen old v1/v2 plan readers and existing backup/restore are mandatory. See `DECISIONS_061.md` and `UNIT_PRICE_PROFIT_CONTRACT_Q03_2026-10-27.md`.

Reason: persistent planning evidence belongs to the existing tenant planning workspace, not financial accounting. One storage authority and the canonical forward engine preserve tenant isolation, tax/rounding contracts and backward compatibility.

Status: Contract adopted for the Q00–Q35 implementation; not yet implemented. Q06/Q15/Q26 and Q35 must provide migration, isolation, restore and exact-head CI evidence.

---

## Decision 060 — updater maintenance gate and bounded SQLite snapshot

Date: 2026-10-25
Topic: prevent startup/update overlap and bound backup waits.

The local updater holds the token-scoped startup/maintenance OS guard through stop verification, backup, fast-forward, dependency checks and offline health checks. The backup service can reuse that already-held guard without releasing it; the updater releases it only at the normal startup handoff or when the operation exits. SQLite online backup runs in a separate standard-library-only process with a hard parent deadline, so a locked database can be terminated and partial snapshots removed. Details: `DECISIONS_060.md`.

---

## Decision 059 — Bot startup and backup snapshot exclusion

Date: 2026-10-25
Topic: shared token-scoped startup/snapshot guard.

Canonical startup and backup use one transient operating-system guard. Backup holds it from lifecycle inspection through verified archive publication; startup holds it while obtaining the long-lived instance lock and publishing `STARTING`. Both fail closed when the other owns the guard. The guard does not change lifecycle metadata or stop an existing process. Details: `DECISIONS_059.md`.

---

## Decision 058

Date:

2026-10-25

Topic:

Safe process status and local runtime diagnosis

Decision:

- Local status reports polling lifecycle separately from offline environment validity; `RUNNING` remains tied to PTB updater/application readiness, never PID presence.
- Lifecycle may persist only one of the fixed startup/polling failure codes. Raw exceptions, credentials, environment contents, full checkout paths, and control secrets are not included in status or support output.
- Status displays whether the active process checkout matches the requested project root without printing either path or its fingerprint. Graceful stop requires that same checkout identity.
- Support build metadata may include only validated revision, start time, and `foreground`/`background` mode. Invalid fields normalize to `UNAVAILABLE`; source reachability remains part of report diagnostics, not the local healthcheck.

Reason:

Owners need to distinguish a missing/unready process from a local configuration problem and from an Ozon/report source gap without exposing secrets or mistaking local environment checks for live service readiness.

Status:

D05 implements and verifies the status, safe failure-code, checkout identity, and support metadata contracts with synthetic data. No production process or external API was used.

---

## Decision 057

Date:

2026-10-25

Topic:

Local fast-forward update preflight and target pinning

Decision:

- `update_bot.ps1 -CheckOnly` is read-only and evaluates only the local repository plus cached `origin/main`. It returns the exact current and target commit and explicitly says the cached ref may be stale.
- The supported update path is only `main` tracking the canonical `origin/main` remote; never accept an arbitrary branch, ref, remote URL, or shell text from a bot message/report.
- Before stopping the process, inspect dirty/untracked paths and incoming changes. Preserve only exact legacy `data/tasks.json`/`data/users.json` changes when the incoming target does not touch them; block all other dirty code/data and untracked overwrite conflicts.
- The mutating updater must perform an explicit fetch, then rerun preflight against and retain that immutable fetched SHA. It must not stash, reset, or clean local state.
- Lifecycle metadata stores only a one-way fingerprint of the normalized checkout path. Automatic stop requires a matching fingerprint; old active metadata without it and processes from another checkout fail closed. PID is never used to kill a process.
- The updater serializes through a non-blocking OS lock under that worktree's private Git directory. A successful normal update requires exact target revision plus `RUNNING` lifecycle readiness; `-NoStart` explicitly leaves the process stopped.

Reason:

The bot shares a local checkout with durable seller data. Pinning an approved origin commit and resolving every worktree conflict before lifecycle changes prevents an update from hiding or overwriting business state.

Status:

D03/D04 implement and verify read-only preflight plus mocked update orchestration. Local tests use synthetic repositories and injected boundaries. No live update has been run.

---

## Decision 056

Date:

2026-10-25

Topic:

Local business-data backup and isolated restore contract

Decision:

- Backup v1 is a local archive with two logical roots: project state and configured storage-root state. The manifest records only root-relative paths, sizes, SHA-256 checksums, format/version, app revision and UTC creation time.
- The backup command requires the token-bound bot lifecycle to report `STOPPED`; it does not stop or start the bot. SQLite uses its backup API and integrity check; JSON is parsed before the completed archive is atomically published.
- `.env`, keys, source code, Git, virtualenvs, diagnostics, logs, caches, temporary files and process-control metadata are excluded. Encrypted credentials may be present in the SQLite database; restoring them requires the original separately-held `OZON_CREDENTIAL_MASTER_KEY`.
- Restore v1 validates the archive and writes only to a new empty destination. It does not replace active storage, edit `.env`, connect to Ozon/Telegram, or claim cross-database transaction consistency.

Reason:

The application stores durable data across shared and tenant-specific roots and retains legacy paths that are not all redirected by `AI_ASSISTANT_STORAGE_ROOT`. Explicit roots and a stopped-process boundary make backup scope reviewable while keeping recovery isolated from the live store.

Status:

D00 inventory complete; D01–D02 implement and verify the contract with synthetic data only.

---

## Decision 055

Date:

2026-10-25

Topic:

Offline reconciliation of owner reports and saved canonical snapshots

Decision:

- Reconciliation is a local, read-only tool. It consumes one explicit report profile and the existing saved Period Profit JSON export; it does not call Ozon, start the bot, import report rows into persistent storage, or implement a second profit formula.
- Each report profile pins its sheet, header row, required columns, date basis, unit and amount semantics. An unknown workbook structure fails with a stable reason code instead of guessing a column.
- Period and the locally assigned store alias must match; the alias is a user-supplied guard, not a verified Ozon store identity. SKU-filtered evidence only compares with a canonical snapshot carrying the same SKU dimension. Missing or partial coverage stays evidence-required; an observed zero is distinct from no rows.
- Application revision is copied only from the saved export or supplied explicitly. When it is absent, it remains `UNAVAILABLE`; the current checkout revision is not assumed to be the revision that produced a previously saved bot result.
- The report profile aggregates signed `Сумма итого, руб.` values by `Дата начисления`. Repeated accrual IDs remain separate rows because the source export can contain several valid lines per ID; duplicate headers or malformed rows fail closed.
- The first supported profile is the Ozon accrual workbook. Additional report types require their own verified profile and tests.

Reason:

The existing Period Profit snapshot is the calculation authority. A local comparator can validate report evidence without changing accounting logic or exposing seller row identifiers, while explicit profiles prevent accidental comparison across different source schemas and date grains.

Status:

A02 implemented with a local CLI and isolated tests; exact-head CI and review remain pending.

---

## Decision 054

Date:

2026-10-21

Topic:

Cross-docking evidence in immutable saved plans

Decision:

- New saved-plan calculation version 2 stores the rate and allowlisted source evidence in the exact revision. Viewing, comparing, readiness and exporting use that frozen evidence and never query Ozon.
- Existing version 1 documents continue through an explicit compatibility adapter; their inputs and exports do not acquire current cross-docking evidence retroactively.
- An explicit source refresh may feed a new revision or copy after identity and CAS checks. It must not mutate an older revision.
- Sales-mix planning applies the historical per-supplied-unit rate to planned successful sales Q. This planning deduction does not alter the factual side of plan/fact comparison.
- Completeness of the collected 56-day window is separate from availability of a usable SKU rate. A complete window with no eligible supplied units may be saved as complete source evidence, but it has no numeric rate and cannot make a positive-Q sales mix complete.
- Plan/fact accepts legacy v1 and current v2 saved plans. For v2, the frozen rate can affect the plan-only profit projection; the factual quantity/revenue inputs and arithmetic bridge remain unchanged, and an unavailable positive-Q rate keeps planned profit unavailable.

Reason:

The calculation's source evidence must remain reproducible across restarts and source refreshes. Separating v1 and v2 prevents historical plans from changing silently, and keeping planned Q out of the actual comparison avoids mixing assumptions with recorded results.

Status:

Implemented and covered by X05 saved-plan, batch, sales-mix, comparison and export regressions.

---

## Decision 052

Date:

2026-10-20

Topic:

Cross-docking expense evidence and shared accrual classification

Decision:

- Keep Ozon accrual fee-category aliases in one shared classifier used by the experimental store report and cross-docking unit-cost evidence.
- Build the 56-day expense numerator from signed, classified leaf amounts on their finance accrual dates. Never reconstruct it from parent `total_amount`, tariffs, payout totals, or sales.
- Preserve direct SKU attribution for item-level fee leaves; treat seller/container leaves without a SKU as shared and use a store estimate only when complete cross-docking supply coverage exists.
- Any incomplete day, unknown fee type, malformed leaf, or conflicting accrual identity prevents publication of numeric evidence. Positive amounts reduce the signed expense total; do not apply `abs()` per operation.
- Keep this component pure and disconnected from current/scenario production calculators until the later bounded source/cache integration stages.

Reason:

The Ozon daily accrual endpoint mixes leaf service amounts with parent financial totals and exposes both SKU-linked and seller-level fee nodes. A shared classifier and signed leaf projection prevent category drift and double counting while preserving the distinction between exact SKU costs and shared store costs.

Status:

Implemented through X04 bounded collection, canonical current/scenario math and Telegram presentation. X05 immutable saved-scenario compatibility remains.

## Decision 053

Date:

2026-10-21

Topic:

Cross-docking evidence collection budgets and cache scope

Decision:

- Collect 56-day financial and supplied-unit evidence through the existing read-only Ozon client with a maximum of 64 HTTP attempts and 60 seconds per calculation slice; each endpoint operation is one attempt and shares the parent operation trace budget.
- Keep raw checkpoints and complete projections in bounded process-local memory only, keyed by tenant/store, exact date window and model version. Incomplete evidence is resumable but never published as a numeric unit rate; complete evidence has a 10-minute TTL and force refresh clears the matching checkpoint.
- Within one parent operation that refreshes multiple SKUs, invalidate the shared store/window evidence once; subsequent SKU projections in that operation reuse the completed result or continue its checkpoint instead of restarting the same collection.
- Reuse complete daily accrual pages already held by the request-local `PeriodProfitFinanceService` cache for the overlapping 28-day window. Do not launch a second pagination for each SKU.
- Keep Ozon reads lazy until an explicit calculation; application construction and imports perform no API calls. Do not persist raw API payloads or identifiers in diagnostics.

Reason:

The 56-day source can exceed one request budget and the unit-cost denominator is only valid when both financial and actual supplied-unit coverage are complete. Scoped continuation preserves bounded operation behavior without exposing partial averages or adding another persistence/job subsystem.

Status:

Bounded collection, calculator application and operation-scoped refresh behavior are implemented and covered by X03–X04 plus the R1–R3 review regression profile. Persistent scenario snapshots and historical-plan compatibility are covered by X05 and its follow-up review fixes.

## Decision 051

Date: 2026-10-20

Topic: Cross-docking supplied-unit identity and accepted quantity

Decision:

- Each cross-docking supply identifies one product/SKU, per the user's business rule.
- The supplied-unit denominator uses product-row `fact_quantity` from the matching accepted acceptance act, not planned/declared quantity, `approved_quantity`, summary totals, sales or order counts.
- Eligibility requires a completed order and completed nested cross-dock supply. For the verified single-supply order shape, use the order's `state_updated_date` as the completion day in `Europe/Moscow`; do not use act `created_date`, planned dates or deprecated `arrival_date`.
- A multi-supply order has no verified per-supply completion timestamp; its supplies must produce incomplete coverage and must not enter a supposedly complete window until their date is proven.

Reason:

Two user-provided read-only diagnostics include a full receipt (500 declared/fact) and a partial receipt (200 declared, 100 fact). The latter's single-supply order completion date matches the Ozon UI and the order's `state_updated_date`, while the act creation date is one day earlier. Summary quantities diverge from the product line. This evidence supports a narrowly scoped rule and explicit fail-closed behavior, not extrapolation to multiple nested supplies.

## Decision 019

Date: 2026-09-19

Topic: Selected-SKU request isolation and bounded identity evidence search

Decision:

- selected catalog scope lives in a request-local `ContextVar`, never in shared mutable
  service attributes;
- exact posting-offer recovery examines at most three deterministic posting numbers and
  accepts only one exact catalog offer from a usable posting as a final fallback;
- before detail probing, monthly realization evidence resolves exact
  `posting_number + finance SKU + offer_id` across the complete period;
- a realization SKU rewritten by Ozon may use `posting_number + offer_id` only
  when that posting is owned by exactly one finance SKU;
- identity recovery must not load an account-wide paged FBO snapshot; after cached
  finance/realization evidence it may use only bounded exact fallbacks;
- failure to calculate the optional comparison period omits comparison and never
  converts it to a zero or blocks an independently proven current-period result;
- selected-aware finance scope owns a unique `offer_id → product` index and enters
  canonical finance scoping directly instead of inheriting the store-wide one-to-many
  legacy offer index;
- batch evidence prefilters selected finance SKU candidates before any per-SKU network
  recovery; local explicit mappings remain authoritative candidates;
- absence or ambiguity remains fail-closed;
- proven identity and posting responses are reused only inside the current request;
- the final application layer alone owns previous-period comparison execution.

Reason:

The former path multiplied two previous-period passes by an unbounded serial FBO/FBS
probe for every posting and allowed concurrent callbacks to overwrite shared scope.

---


## Decision 001

Date:

2026-08-13


Topic:

Service architecture


Decision:


Проект строится как набор независимых сервисов.


Причина:


Упрощение тестирования и расширения.


---


## Decision 002


Topic:

Dependency Injection


Decision:


Все сервисы получают зависимости через constructor injection.


Причина:


Уменьшение связанности.


---


## Decision 003


Topic:

Task based execution


Decision:


Бизнес-логика выполняется через задачи и действия.


Причина:


Поддержка:


- истории
- статусов
- повторов
- контроля выполнения



---


## Decision 004


Topic:

AI development workflow


Decision:


Разработка ведётся через Project Brain.


Каждое изменение сопровождается:


- тестом
- документацией
- обновлением состояния проекта



---


## Decision 005


Date:

2026-08-14


Topic:

Feedback and Memory Loop


Decision:


Опыт выполнения задач сохраняется через цепочку:


Execution

↓

Feedback

↓

Memory


Причина:


Агент должен не только выполнять действия,
но и накапливать опыт для будущих решений.



Результат:


Добавлены:


- Feedback Service
- Memory Service
- Feedback → Memory integration
- сохранение опыта выполнения



---


## Decision 006


Date:

2026-08-14


Topic:

Memory-aware Planning


Decision:


Планирование должно учитывать предыдущий опыт агента.


Архитектура:


Memory

↓

Planning

↓

Action Generation


Причина:


Прошлый опыт должен улучшать будущие планы,
а не просто храниться как история.



Результат:


Добавлены:


- memory lookup
- memory context in planning
- memory-guided action generation



---



## Decision 007


Date:

2026-08-14


Topic:

Project Brain as project memory


Decision:


Состояние проекта должно храниться в документации и Git,
а не только в контексте текущего диалога.


Причина:


Предотвращение потери контекста и documentation drift.


Правило:


Каждый значимый этап разработки должен фиксироваться:


- CURRENT_STATE.md
- ROADMAP.md
- CHANGELOG.md
- DECISIONS.md


Статус:


Implemented

---

## Decision 044

Date:

2026-10-12

Topic:

Effective-Dated Seller Cost Confirmation and Atomic Table Import

Decision:

The first seller-entered cost is effective from a proposed, seller-visible date.
Prior periods remain without confirmed cost unless the seller separately confirms
that the initial value applies to the entire available history. A Telegram cost
change is not persisted before the seller confirms the displayed store, product,
amount and effective date.

Rules:

- individual first entry proposes the current date; an existing-cost change
  proposes the next calendar day so today's completed calculations are not silently
  rewritten;
- whole-history application is available only for products without an existing
  configured cost and requires choosing the option followed by a second explicit
  confirmation;
- the confirmation is bound to the active tenant/store scope and is rejected after
  a store switch;
- CSV exports an effective-date column; first-time blank dates are proposed as
  today, while a change to an existing cost requires an explicit date in the CSV;
- CSV is previewed with row identity, amount and dates and is never treated as
  consent by the upload itself;
- whole-history CSV application is restricted to first-time costs and requires a
  separate two-step confirmation;
- the batch and current cost projections are written in one tenant-local SQLite
  transaction; validation/conflict failure leaves every row unchanged;
- exact replay of an already-recorded batch is idempotent, while a different value
  for the same product and effective date is rejected;
- the mutable current-cost projection reflects the latest effective switch, even
  when an older dated batch is imported later;
- Decision 039's prohibition on assumed historical backfill remains in force.

Reason:

A current price is not proof of an earlier unit cost. Showing the proposed date and
requiring a separate seller action prevents accidental retroactive cost changes;
atomic table writes prevent mixed catalog cost timelines after a partial failure.

Status:

Implemented for Telegram single-SKU input and CSV table import. P02 regression
coverage passed; Windows Python 3.12 full suite passed (2,998 tests) in an
isolated copy. Live Ozon/Telegram behavior is not implied by the test result.

---

## Decision 042

Date:

2026-09-22

Topic:

Seller revocation of an incorrect historical SKU identity

Decision:

A seller-confirmed finance-SKU mapping must be reversible by the same seller-facing
Telegram surface. Revocation requires exactly two SKU values and succeeds only when
one is the active finance SKU and the other exactly matches its current catalog SKU.
The active projection is removed transactionally, while its complete non-secret
identity snapshot and revocation source are retained in a local audit table. Other
mappings, Ozon data, costs, and previously fetched financial evidence are unchanged.

The response must state that earlier reports produced through the revoked mapping
are invalid. Missing, mismatched, ambiguous, or concurrently changed mappings fail
closed without mutation.

Reason:

Seller confirmation is business evidence supplied by a human and can be mistaken.
An irreversible confirmation would allow a known error to continue contaminating
future selected-SKU reports. Exact-pair revocation corrects the active identity
projection without silently erasing what was previously asserted.

Status:

## Decision 041

Date:

2026-10-12

Topic:

Cross-Platform Task Store Locking and Durability Reporting

Decision:

Keep the existing JSON task store and its optimistic fingerprint, atomic
replace, and file-fsync contract. Use the operating system's non-blocking file
lock for writer exclusion: `fcntl.flock` on POSIX and `msvcrt.locking` on
Windows.

Rules:

- Both backends lock the same stable, empty `<tasks-file>.lock` coordination
  file; it is not deleted and its presence is not evidence of an active owner.
- If the platform has no supported OS lock backend, writes fail closed.
- Windows lock contention is reported as `TASK_FILE_WRITE_LOCKED`; closing the
  descriptor or exiting the process releases the OS lock.
- Atomic replace and syncing the data file remain required. The current
  directory-fsync mechanism is POSIX-only; Windows reports
  `TASK_DIRECTORY_FSYNC_UNSUPPORTED` as a post-commit durability warning and
  never claims that the directory entry was synced.
- Task storage schema, file location, and public task contract remain
  unchanged. No lock framework or recovery/deletion behavior is introduced.
- Windows shutdown uses the existing `stop_signals=None` runtime contract;
  POSIX continues to register SIGINT/SIGTERM.

Reason:

The supported local runtime is Windows 3.12, where `fcntl` is unavailable.
Failing all writes there prevents local task persistence. A minimal native OS
backend restores writer exclusion without replacing the task engine. Windows
does not provide the POSIX directory-fsync operation used by the current
implementation, so the committed write must surface that durability limit
instead of reporting an unsupported operation as successful.

Status:

Implemented; Windows Python 3.12 full verification completed with the 35
remaining financial test failures assigned to P02. Linux Python 3.11 CI is
configured and awaits a remote run on the implementation revision.

---

## Decision 043

Date:

2026-09-22

Topic:

Request-bound store tax authority and onboarding cost coverage

Decision:

Tax policy for Period Profit must be read during each calculation under the active
store tenant scope (`Telegram user + Ozon Client ID`). A tax-policy snapshot taken
while constructing a long-lived process is not authoritative. The same request-time
policy provider is used for ordinary Period Profit tax and final Return COGS tax
recomputation. Missing or malformed policy remains fail-closed.

The onboarding cost step must use the canonical seller-cost menu coverage rather
than unconditional copy. When that coverage proves `missing=0`, `/start` goes to
the main keyboard and does not ask the seller to configure cost again. Unavailable
coverage does not fabricate completion.

Reason:

One Telegram user can connect multiple Ozon stores with different tax policies,
and cost completion can change after onboarding. Both decisions therefore require
current tenant-bound evidence rather than process-start or hard-coded state.

Status:

Implemented

---

---


## Decision 008


Date:

2026-08-14


Topic:

AI Development Agent purpose


Decision:


AI Development Agent является внутренним инструментом
ускорения разработки AI Business Assistant.


Главный продукт проекта:


AI Business Assistant


AI Development Agent используется для:


- уменьшения ручных действий при разработке
- ускорения создания новых возможностей
- автоматизации тестирования
- поддержания Project Brain
- контроля документационного drift


Причина:


Основная ценность проекта заключается в создании
AI Business Assistant для управления бизнесом.


Автоматизация разработки необходима для ускорения
создания и улучшения основного продукта.


Архитектура:


AI Development Agent

↓

Project Brain

↓

Development Workflow

↓

AI Business Assistant


Статус:


Implemented



---



## Decision 009


Date:

2026-08-14


Topic:

Development Autopilot Direction


Decision:


AI Development Agent развивается как внутренний слой
автоматизации разработки AI Business Assistant.


Архитектура:


AI Development Agent

↓

Development Workflow

↓

AI Business Assistant



Причина:


Создание AI Business Assistant требует большого количества
повторяющихся действий разработки:


- анализ изменений
- обновление документации
- запуск тестов
- подготовка checkpoint


AI Development Agent должен уменьшать ручное участие разработчика
и ускорять развитие основного продукта.



Результат:


Добавлены в roadmap:


- Change impact analysis
- Documentation drift detection
- Automated development workflow
- Git checkpoint assistant



Следующий этап:


Development Autopilot v0.1



---



## Decision 010


Date:

2026-08-14


Topic:

Change Impact Analysis


Decision:


Перед изменением кода AI Development Agent
обязан анализировать влияние изменения
на архитектуру, тесты и документацию.


Архитектура:


File Change

↓

Impact Analyzer

↓

Affected Components

↓

Test Map

↓

Documentation Update



Причина:


Изменение одного сервиса может влиять
на несколько слоёв системы.


Анализ влияния должен уменьшить риск
регрессий и потери архитектурного контекста.



Результат:


Создаётся первый компонент Development Autopilot:


- Change Impact Analysis Service



---



## Decision 011


Date:

2026-08-18


Topic:

Documentation Automation Layer


Decision:


AI Development Agent получает отдельный слой
автоматизации управления документацией проекта.


Архитектура:


AI Development Agent

↓

Documentation Manager

↓

Project Brain


Причина:


Изменения в коде требуют синхронного обновления:

- CURRENT_STATE.md
- CHANGELOG.md
- TEST_MAP.md
- DECISIONS.md


Ручное обновление документации приводит
к риску documentation drift.


Правило:


CHANGELOG.md работает в режиме append only.


Исторические записи не изменяются
и не удаляются.


Результат:


Создаётся основа для:

- автоматического обновления Project Brain
- контроля документационного состояния
- уменьшения ручного участия разработчика


Следующий этап:


AssistantDocumentationManager

---

## Decision 012


Date:

2026-08-18


Topic:

Automated Development Workflow


Decision:


AI Development Agent получает слой
автоматизации полного цикла разработки.


Архитектура:


Change Detection

↓

Change Impact Analysis

↓

Test Execution

↓

Documentation Update

↓

Git Checkpoint



Причина:


Развитие AI Business Assistant требует
уменьшения ручных действий разработчика:


- анализ изменений
- запуск тестов
- обновление Project Brain
- подготовка checkpoint


Development Autopilot должен объединять
существующие инструменты в единый workflow.



Результат:


Создаётся основа:

- Automated Development Workflow
- автоматической проверки изменений
- подготовки Git checkpoint


Следующий этап:


AssistantDevelopmentWorkflowService


---

## Decision 013


Date:

2026-08-18


Topic:

Git Checkpoint Assistant


Decision:


AI Development Agent получает слой
подготовки Git checkpoint в рамках
Automated Development Workflow.


Архитектура:


Development Workflow

↓

Git Checkpoint Assistant

↓

Commit Preparation


Причина:


Завершение цикла разработки требует
контролируемой фиксации изменений.


Git Checkpoint Assistant должен:


- анализировать состояние изменений
- определять изменённые файлы
- подготавливать commit message
- подтверждать готовность checkpoint


Правило:


Git операции должны выполняться
контролируемо и прозрачно.


Автоматический commit без проверки
состояния проекта запрещён.


Результат:


Создаётся основа для:

- автоматической подготовки checkpoint
- безопасной фиксации изменений
- интеграции Git workflow в Development Autopilot


Следующий этап:


AssistantGitCheckpointService

---

## Decision 014


Date:

2026-08-18


Topic:

Development Autopilot Agent Integration


Decision:


AI Development Agent получает
единый управляющий слой,
который объединяет существующие
Development Autopilot сервисы.


Архитектура:


User Task

↓

AssistantDevelopmentAgent

↓

Development Workflow

↓

Service Pipeline

↓

Development Report



Причина:


Текущие сервисы реализуют отдельные
этапы разработки, но требуют
единого координатора.


Development Agent должен управлять
полным циклом:


- анализ изменения
- проверка тестов
- проверка документации
- подготовка checkpoint



Результат:


Создаётся первый слой
автономного Development Agent.


Следующий этап:


AssistantDevelopmentAgent

---

## Decision 015


Date:

2026-08-18


Topic:

Agent Managed Project Brain Synchronization


Decision:


AI Development Agent получает отдельный слой
управления Project Brain.


Архитектура:


AssistantDevelopmentAgent

↓

AssistantProjectBrainManager

↓

Project Brain


↓

- CHANGELOG.md
- CURRENT_STATE.md
- TEST_MAP.md
- DECISIONS.md



Причина:


Ручное обновление документации ограничивает
автономность Development Agent.


Project Brain должен обновляться
как часть автоматического development workflow.



Правило:


Критические архитектурные решения
фиксируются через DECISIONS.md.


Операционные изменения проекта
могут обновляться автоматически
через AssistantProjectBrainManager.



Результат:


Создаётся основа для:

- автоматической синхронизации документации
- уменьшения ручных действий разработчика
- автономного развития Project Brain



Следующий этап:


AssistantProjectBrainManager

---

## Decision 016


Date:

2026-08-18


Topic:

Agent Workflow Execution Loop


Decision:


AI Development Agent получает
исполняющий цикл workflow,
который связывает существующие
Development Autopilot сервисы.


Архитектура:


User Task

↓

AssistantDevelopmentAgent

↓

Development Workflow Execution

↓

Service Pipeline

↓

Development Report



Причина:


Наличие отдельных сервисов недостаточно
для автономной разработки.


Agent должен уметь координировать
выполнение последовательности действий.



Workflow включает:


- анализ изменений
- проверку состояния проекта
- синхронизацию Project Brain
- подготовку Git checkpoint



Правило:


Agent выполняет только
контролируемые операции.


Каждый этап workflow должен
возвращать проверяемый результат.



Результат:


Создаётся первый исполнительный цикл
Development Autopilot.


Historical Next Step:


Agent Workflow Integration


Status:

Superseded by Decision 017

---

## Decision 017


Date:

2026-08-19


Topic:

GPT GitHub Development Workflow


Decision:

Development Infrastructure
переориентируется с автономного
исполнения задач на поддержку
разработки AI Assistant через
GPT + GitHub workflow.


Architecture:


Developer

↓

GPT

↓

GitHub Repository

↓

Tests

↓

Project Brain Update

↓

Review


Rules:

- Project Brain является источником контекста проекта
- GPT должен изучать документацию перед изменениями
- Кодовые изменения должны сопровождаться тестами
- Документация обновляется вместе с функционалом
- Архитектурные решения фиксируются отдельно


Reason:

Использование внешнего GPT через GitHub
позволяет ускорить разработку основного
AI Assistant проекта без создания отдельного
автономного разработчика.


Result:

Development Infrastructure становится
инструментом ускорения разработки
AI Assistant.

---

## Decision 018

Date:

2026-08-28

Topic:

Product Decision Memory

Decision:

История бизнес-решений по товарам хранится отдельно от технической
`product_memory` и общей памяти задач.

Architecture:

ProductBusinessDecisionQueryService

↓

ProductDecisionHistoryService

↓

ProductDecisionHistoryStorageService

Rules:

- сохраняются только успешные решения;
- первая запись является базовой точкой;
- новая запись создаётся только при изменении типа решения или приоритета;
- история ограничена 50 записями на артикул;
- память не влияет на решение и не запускает действия;
- путь хранилища передаётся через dependency injection.

Reason:

Развитие рекомендаций требует наблюдаемой истории изменений, но смешивание
её с техническими метриками товара или task memory нарушило бы границы
ответственности существующих компонентов.

Status:

Implemented

---

## Decision 041

Date:

2026-09-22

Topic:

Seller confirmation of historical selected-SKU identity

Decision:

When Ozon finance and posting evidence proves sales under a historical SKU but
does not prove that SKU belongs to the currently selected catalog item, selected-SKU
Period Profit may ask the seller to confirm the identity in Telegram. A candidate
is eligible only when a sampled posting has exactly one finance-SKU owner and one
non-empty offer identifier. The candidate must be revalidated against fresh query
evidence when the confirmation button is pressed. A confirmed mapping is stored as
tenant-local identity evidence and the original calculation is retried.

The confirmation does not create monetary evidence, change costs, or authorize an
ambiguous match. Store-wide calculations remain unchanged. Missing, conflicting,
multi-offer, shared-posting, stale, or forged candidates remain fail-closed.

Reason:

Ozon can retain finance history under an old SKU/offer without exposing a
machine-verifiable current-catalog relation. Returning "no sales" hides that known
history, while automatic attribution could mix products or variants. Explicit,
evidence-bounded seller confirmation resolves the identity gap without weakening
financial integrity.

Status:

Implemented

## Decision 019

Date:

2026-08-28

Topic:

Manual Product Decision Feedback

Decision:

Пользовательская оценка рекомендации сохраняется как атрибут последнего
снимка решения, а не как новое бизнес-решение или выполненное действие.

Allowed signals:

- USEFUL
- NOT_RELEVANT

Rules:

- feedback доступен только при наличии сохранённого решения;
- повторная одинаковая оценка идемпотентна;
- неизвестные значения отклоняются;
- feedback не изменяет правила, confidence или priority;
- feedback не запускает автоматические действия.

Reason:

Для обучения требуется явный пользовательский сигнал, но влияние такого
сигнала на рекомендации допустимо только после накопления и проверки
исторических результатов.

Status:

Implemented

---

## Decision 041

Date:

2026-09-20

Topic:

Selected-SKU identity must not require account-wide posting enumeration

Decision:

Selected-SKU Period Profit resolves historical finance SKUs by querying Ozon's
related-SKU group for the exact selected current SKU once and intersecting that
proven group with finance SKUs observed in the requested period. The result is
request-locally cached for downstream recovery. Account-wide FBO list pagination
is forbidden in selected-SKU mode. If exact realization, seller-confirmed mapping,
or the reverse related-SKU group cannot prove identity, calculation fails closed.
Because Ozon relations may be directional, an empty reverse intersection may use
batch bisection over period finance SKUs. Only singleton responses containing the
exact selected current SKU prove a mapping; discovery has a hard 64-call budget.
Before related-SKU discovery, one posting per finance SKU may be checked through
the batched finance accrual-postings endpoint. A rewritten current catalog SKU is
accepted only when that exact posting has one finance-SKU owner.
If that evidence retains historical SKUs, selected mode may inspect one posting
detail per finance SKU (maximum 64, eight workers). Identity is proven only when
the posting has one finance-SKU owner and every non-empty product offer equals the
exact selected `offer_id`; FBO falls through to FBS only when no usable FBO rows
exist.

Reason:

FBO history size is unrelated to one selected SKU and reached hundreds of serial
HTTP pages in production. Querying the exact current SKU preserves variant identity
while bounding the network work independently of account posting volume.

Status:

Implemented

---

## Decision 020

Date:

2026-08-28

Topic:

Product Decision Outcome Correlation

Decision:

После feedback следующее изменение решения получает наблюдаемый outcome по
изменению уровня срочности.

Outcomes:

- PRIORITY_DECREASED
- PRIORITY_INCREASED
- DECISION_CHANGED

Rules:

- outcome создаётся только при наличии feedback у предыдущего решения;
- сравнивается приоритет предыдущего и нового решения;
- одинаковый приоритет считается нейтральной сменой решения;
- outcome не влияет на будущие решения;
- пользовательский интерфейс не утверждает причинную связь.

Reason:

Связь обратной связи с последующим состоянием создаёт основу для обучения,
но текущих данных недостаточно, чтобы считать изменение следствием принятой
рекомендации или действия пользователя.

Status:

Implemented

---

## Decision 021

Date:

2026-08-28

Topic:

Safe Product Action Proposals

Decision:

Следующий шаг по товарному решению формируется отдельным proposal-service и
остаётся read-only до появления отдельного подтверждённого workflow.

Rules:

- все proposals имеют execution_allowed=False;
- операционные проверки требуют ручного подтверждения;
- monitoring-only не считается обязательным действием;
- количество пополнения и изменение цены не рассчитываются без политики;
- proposal-service не зависит от Action Executor;
- Telegram отображает proposal, но не выполняет его.

Reason:

Ассистент должен давать конкретный следующий шаг, сохраняя границу между
рекомендацией и изменением реального бизнеса.

Status:

Implemented

---

## Decision 022

Date:

2026-08-28

Topic:

Product Action Proposal Confirmation

Decision:

Подтверждение или отклонение proposal сохраняет намерение пользователя в
последнем снимке решения, но не является разрешением на выполнение действия.

Rules:

- подтверждается только proposal, соответствующий последнему решению;
- устаревший proposal отклоняется;
- повторный одинаковый статус идемпотентен;
- monitoring-only не подтверждается как операционное действие;
- любой результат содержит executed=False и execution_allowed=False;
- Action Executor и внешние API отсутствуют в confirmation workflow.

Reason:

Это позволяет собрать управляемую очередь намерений и проверить UX до
появления политик количества, цены, полномочий и отдельного безопасного
исполнителя.

Status:

Implemented

---

## Decision 023

Date:

2026-08-28

Topic:

Confirmed Product Task Drafts

Decision:

Подтверждённый proposal создаёт отдельный постоянный черновик задачи,
привязанный к конкретному снимку решения. Черновик не является задачей
существующего исполнительного контура.

Rules:

- ключ черновика включает артикул, тип proposal и время снимка решения;
- повторное подтверждение не создаёт дубликат;
- отклонение закрывает соответствующий черновик;
- черновик не содержит придуманного количества или новой цены;
- execution_allowed=False и executed=False сохраняются всегда;
- ProductActionTaskDraftService не зависит от Action Executor и Ozon API.

Reason:

Отдельный read-only слой позволяет накапливать подтверждённые намерения и
проверять их качество до проектирования полномочий, бизнес-политик и
исполнительного workflow.

Status:

Implemented

---

## Decision 024

Date:

2026-08-28

Topic:

Product Task Draft Review Lifecycle

Decision:

Черновик автоматически устаревает, если его снимок решения или actionable
proposal больше не совпадает с текущим решением товара. Пользователь может
перевести черновик в терминальный архив.

States:

- DRAFT — актуальный черновик для дальнейшей подготовки;
- STALE — исходное решение изменилось;
- DISMISSED — пользователь отклонил proposal;
- ARCHIVED — пользователь завершил работу с черновиком.

Rules:

- reconcile выполняется только в read/decision pipeline;
- архивирование идемпотентно;
- ARCHIVED не открывается повторным подтверждением той же карточки;
- старые записи получают компактный draft_id без потери данных;
- любое изменение lifecycle возвращает executed=False;
- lifecycle не зависит от Action Executor и внешних API.

Reason:

Черновики должны оставаться проверяемой очередью намерений, а не бесконечно
активными рекомендациями после изменения исходных данных.

Status:

Implemented

---

## Decision 025

Date:

2026-08-28

Topic:

Product Draft Review Queue Prioritization

Decision:

Приоритет очереди проверки рассчитывается отдельным детерминированным
read-service и не сохраняется как новое бизнес-решение.

Scoring order:

- актуальность черновика;
- приоритет исходного решения товара;
- тип ручной проверки;
- при равном score более старый черновик показывается первым.

Rules:

- в очередь входят только DRAFT и STALE;
- DISMISSED и ARCHIVED исключаются;
- каждый элемент содержит score, категорию и коды причин;
- presentation переводит причины, но не меняет формулу;
- приоритизация не меняет lifecycle и всегда executed=False;
- сервис не зависит от Action Executor и Ozon API.

Reason:

Пользователю нужна ограниченная и объяснимая очередь проверки, при этом
техническая сортировка не должна становиться скрытым автоматическим решением.

Status:

Implemented

---

## Decision 026

Date:

2026-08-28

Topic:

Product Task Draft Detail and Audit Trail

Decision:

Каждый новый черновик хранит append-only журнал фактических lifecycle
переходов и доступен через отдельную read-only карточку Telegram.

Audited events:

- CREATED;
- REOPENED;
- MARKED_STALE;
- DISMISSED;
- ARCHIVED.

Rules:

- событие добавляется только при реальном изменении состояния;
- idempotent-команда не создаёт новое событие;
- событие хранит источник, время, старый и новый статус;
- старым записям не создаётся вымышленная история;
- карточка показывает source metrics, но не рассчитывает новое решение;
- каждое событие и detail-result сохраняют executed=False.

Reason:

До дальнейшего развития автономности пользователь должен иметь возможность
проверить происхождение черновика и каждый переход его состояния.

Status:

Implemented

---

## Decision 027

Date:

2026-08-28

Topic:

Product Task Draft Readiness Checklist

Decision:

Готовность к ручной проверке и готовность к исполнению являются разными
состояниями. Полный factual checklist не разрешает выполнение действия.

Rules:

- factual checks зависят от типа proposal;
- нулевое значение считается доступным фактом, None — отсутствующим;
- STALE, DISMISSED и ARCHIVED не готовы к актуальной ручной проверке;
- missing facts отображаются без экстраполяции;
- execution_ready всегда False;
- execution blockers включают неподключённый workflow и отсутствующие
  бизнес-политики количества, срока поставки, цены или целевой маржи;
- checklist не меняет decision, draft lifecycle или review score.

Reason:

Даже качественные входные данные не заменяют утверждённые бизнес-правила и
явно спроектированный исполнительный контур.

Status:

Implemented


---

## Decision 028

Date:

2026-08-30

Topic:

Unknown Advertising Financial Evidence

Decision:

Отсутствие подтверждённого значения рекламных расходов не эквивалентно
нулевым расходам.

Rules:

- `advertising_cost=None` означает отсутствие evidence и сохраняется как unknown;
- только явно переданный `advertising_cost=0` означает подтверждённый ноль;
- при unknown advertising `business_profit` и `margin_percent` не рассчитываются;
- revenue и gross profit могут оставаться доступными как отдельные факты;
- presentation не превращает unknown financial values в `0`;
- отсутствие advertising evidence не является ошибкой внешнего API и не
  запускает автоматическое получение/классификацию данных;
- никакое seller/business execution из этого состояния не разрешается.

Reason:

Оптимистичная подстановка нулевой рекламы завышает финансовый результат и
смешивает отсутствие evidence с фактическим нулём. Финансовые выводы должны
быть fail-closed и evidence-bound.

Status:

Implemented


---

## Decision 029

Date:

2026-08-30

Topic:

Finance Context Evidence Scope

Decision:

Finance Intelligence context built from StorePeriodProfitService must preserve
the scope of its source evidence and must not promote missing facts to zero.

Rules:

- any explicit error row blocks finance-context aggregation;
- gross_sales and gross_profit are required for every accepted period-profit row;
- malformed, non-finite, boolean or missing required values fail closed;
- explicit numeric zero remains a valid fact;
- FinanceContextProvider preserves its existing output shape;
- Finance Intelligence may classify its own direct derived/caller-provided
  result internally without requiring a new provider context field;
- derived expenses remain revenue minus period gross profit and are described
  only as expenses by available evidence;
- Finance Intelligence must not call PERIOD_GROSS_PROFIT accounting net profit
  or claim that the whole business is profitable;
- no tax, advertising, storage or returns expense is inferred or subtracted
  again in this context layer.

Reason:

The finance recommendation pipeline consumes period gross-profit evidence.
Without explicit scope and fail-closed validation, incomplete payloads can look
like zero-cost facts and seller-facing wording can overstate what the evidence
proves.

Status:

Implemented


---

## Decision 030

Date:

2026-08-30

Topic:

Stock Evidence Availability

Decision:

Отсутствие или неполнота evidence по остаткам не эквивалентна доказанному
`low_stock=False`.

Rules:

- `low_stock=True` создаётся только из конкретных валидных stock + sales facts;
- подтверждённый low-stock action context сохраняет существующую форму;
- при отсутствии dependencies, товаров, периода, stock metrics или sales facts
  action не создаётся и `low_stock=False` сопровождается
  `stock_evidence_available=False`;
- только полностью проверенный no-risk ассортимент получает
  `stock_evidence_available=True`;
- malformed, boolean, non-finite, negative и cross-product evidence fail closed;
- explicit zero sales остаётся валидным фактом;
- общий fallback не утверждает отсутствие критичных проблем при unavailable
  stock evidence;
- availability metadata не разрешает replenishment execution;
- historical AssistantEntryService mode без data dependencies сохраняет
  прежний hardcoded fallback; availability semantics применяются к реально
  подключённому stock data path.

Reason:

Ранее несколько failure/missing-data веток возвращали только
`low_stock=False`, смешивая “риск не найден” с “риск невозможно проверить”.
Это могло создавать ложное clean-state впечатление.

Status:

Implemented


---

## Decision 031

Date:

2026-08-30

Topic:

Sales Evidence Availability

Decision:

Настроенный Sales Intelligence data path не должен превращать отсутствующее,
malformed или partial comparison evidence в подтверждённое
`sales_down=False` или искусственные нулевые метрики.

Rules:

- подтверждённый decline сохраняет существующий `sales_down=True` +
  `sales_context` action payload без нового availability field;
- complete non-decline comparison получает
  `sales_evidence_available=True`;
- unavailable/partial configured sales evidence получает
  `sales_down=False` + `sales_evidence_available=False` и не создаёт sales action;
- missing/malformed `change_percent` не считается 0%;
- malformed profits / period / analytics / comparison payloads fail closed;
- SalesIntelligenceService требует valid revenue и gross_profit;
- business_profit и margin могут оставаться `None`;
- explicit numeric zero остаётся валидным фактом;
- generic fallback не утверждает clean business state при unavailable sales evidence;
- historical AssistantEntryService mode без data dependencies сохраняет старый
  hardcoded fallback;
- availability metadata не является execution authorization.

Reason:

Ранее отсутствующий revenue comparison по default превращался в 0%, а missing
Sales Intelligence metrics могли превращаться в 0. Это смешивало
“нет доказательств” с “стабильно/нулевое значение” и могло подавлять sales action
или создавать ложное clean-state впечатление.

Status:

Implemented

---

## Decision 032

Date:

2026-08-30

Topic:

Marketing Evidence Integrity

Decision:

Marketing recommendation/executor boundaries must not claim analysis or channel
checks without explicit supplied evidence.

Rules:

- `marketing_problem=True` alone is not actionable;
- actionable marketing recommendation requires
  `marketing_evidence_available=True` and non-empty `marketing_context`;
- executor accepts only explicit non-empty string evidence items;
- executor formats provided evidence and does not invent findings;
- missing/malformed evidence returns an error;
- persisted router execution therefore uses the existing FAILED lifecycle;
- evidence availability is not mutation/execution authorization;
- no hidden marketing API fetch or campaign mutation is introduced.

Reason:

The previous executor had no marketing data source but returned completed-looking
claims such as checked channels and found opportunities. That overclaimed runtime
evidence.

Status:

Implemented

---

## Decision 033

Date:

2026-08-30

Topic:

Finance Evidence Availability Propagation

Decision:

Assistant report/recommendation semantics must distinguish unavailable finance
evidence from a verified clean finance state without changing
FinanceContextProvider's established payload.

Rules:

- successful derived finance context marks `finance_evidence_available=True`;
- derived finance failure with non-null period evidence marks
  `finance_evidence_available=False`;
- absent period evidence does not invent a finance availability conclusion;
- explicit incoming finance_context remains authoritative and available;
- `finance_evidence_available=False` suppresses finance recommendation and
  clean-business fallback;
- legacy direct callers with finance_context and no availability metadata remain
  backward compatible;
- availability does not authorize execution.

Reason:

A fail-closed provider result was previously discarded by AssistantEntryService,
allowing verified-safe Sales/Stock evidence plus unavailable Finance evidence to
produce an unsupported “no critical problems” conclusion.

Status:

Implemented

---

## Decision 034

Date:

2026-08-30

Topic:

Business Planner Result Integrity

Decision:

AssistantBusinessPlannerService must preserve downstream failure semantics and
must not convert malformed or failing recommendation/planning/execution/task
results into a successful seller-facing plan.

Rules:

- each consumed boundary result must be a dictionary with exact boolean error;
- explicit error=True is preserved unchanged;
- recommendation success requires a recommendations list;
- planning success requires a plan list;
- Action Plan execution success requires list actions plus a non-boolean,
  non-negative integer count matching len(actions);
- task creation errors are not hidden when the optional task-service path is used;
- malformed boundary payloads fail closed with deterministic non-secret codes;
- general recommendations remain presentation-only and do not enter planning;
- no new executor, mutation, action type or execution permission is introduced.

Reason:

The Business Planner previously could wrap an already fail-closed Action Plan
execution result in a new error=False response, suppressing failure semantics and
presenting an execution-adjacent planning operation as successful.

Status:

Implemented

---

## Decision 035

Date:

2026-08-30

Topic:

Business Flow Result Integrity

Decision:

AssistantBusinessFlowService must preserve downstream failure semantics and must
not present malformed or failing intent/planner/task/execution results as
successful seller-facing operations.

Rules:

- every consumed downstream result must be a dictionary with exact boolean error;
- successful intent requires a non-empty string command;
- explicit downstream error=True remains failure and is not paired with success wording;
- successful current-action execution requires a non-empty message, valid optional
  action fields, boolean completion flag, and valid non-negative progress;
- successful planner output requires list actions and a non-boolean, non-negative
  integer count matching len(actions);
- task lifecycle/read results are validated before success presentation;
- skip validates its target before mutation and validates its post-skip read;
- if skip is already committed and a later read fails, the result reports that
  partial committed state rather than pretending rollback;
- continue validates both next-action lookup and pending-action persistence;
- malformed results use deterministic non-secret fail-closed codes;
- no new executor, action type, mutation path, retry, rollback, or execution
  permission is introduced.

Reason:

The Business Flow previously used optimistic defaults such as error=False and
“Действие выполнено” and could therefore suppress lower-layer failures even after
Action Plan and Business Planner result integrity had been hardened.

Status:

Implemented

---

## Decision 036

Date:

2026-09-03

Topic:

Permanent Read-Only Ozon Analyst Product Boundary

Decision:

AI Business Assistant is a seller-facing analyst and advisor, not an autonomous
executor of Ozon business mutations.

Rules:

- production Ozon integration is read-only from the assistant's product boundary;
- the assistant may analyze seller/business evidence, compare periods, detect
  anomalies, rank priorities, explain reasons, recommend actions and prepare
  non-executable drafts/checklists;
- the assistant must not change prices;
- the assistant must not change advertising budgets, bids or campaign state;
- the assistant must not create replenishment/stock mutations;
- the assistant must not mutate product-card content or other seller state;
- Product Decision confirmation remains stored advisory intent, not execution permission;
- Product Task Draft remains a review artifact and never becomes executable;
- no future package may add Ozon mutation merely by adding authorization or a new
  execution workflow; changing this product boundary requires an explicit product
  decision that supersedes this Decision;
- fail-closed validation must reject execution-adjacent success claims on
  read-only analytical surfaces.

Reason:

The intended product role is an analytical assistant for the seller. Operational
actions on Ozon remain under human control outside the assistant.

Status:

Implemented

---

## Decision 037

Date:

2026-09-03

Topic:

Account-Level Ozon Monetary Authority for Period Profit

Decision:

Period Profit must use the complete account-level Ozon daily accrual result as the
authoritative monetary total for revenue, net accrual and Ozon fee components.
SKU-level finance remains a product-attribution source for unit counts, product
revenue reconciliation, product cost and drill-down, but must not be summed as
the authoritative account monetary total.

Rules:

- production Period Profit reads one account-level finance result per day with
  `sku=None`;
- account-level `gross_sales`, `net_accrual`, commission, logistics, acquiring,
  other fees and fee breakdown are authoritative for the period monetary summary;
- SKU-level finance remains required for product sales counts and COGS attribution;
- summed SKU revenue must reconcile to account-level Ozon revenue within 0.01 RUB;
- revenue mismatch fails closed with
  `PERIOD_PROFIT_PRODUCT_REVENUE_COVERAGE_INCOMPLETE`;
- period tax is calculated from reconciled account-level revenue using the
  configured tax fraction;
- period profit is
  `account_net_accrual - product_cost - tax`;
- the difference between account-level net accrual and summed SKU-attributed
  net accrual is exposed as `ozon_account_reconciliation`;
- that reconciliation may contain account-level operations without SKU and may
  also correct SKU-level duplication from multi-SKU postings;
- account-level Ozon accrual inclusion does not by itself prove complete
  accounting classification of returns, advertising or storage;
- known Ozon account-level monetary operations already included in net accrual
  must never be subtracted a second time;
- accounting net-profit claim remains prohibited until non-Ozon accounting
  adjustments and component completeness are separately established;
- Decision 036 read-only boundary remains unchanged.

Reason:

SKU-filtered daily finance can omit account-level charges without SKU and can
duplicate a posting-level total when one posting contains multiple SKUs. Summing
SKU-level net accruals therefore cannot be the authoritative seller-account
profit source. The account-level Ozon accrual is the safer monetary authority,
while SKU evidence is still needed to prove product revenue coverage and COGS.

Status:

Implemented

---

## Decision 038

Date:

2026-09-03

Topic:

External Operating Expense Evidence and Coverage

Decision:

Period Profit may derive a profit view after seller-recorded expenses outside the
Ozon accrual stream only from explicit local expense rows plus explicit period
coverage evidence.

Rules:

- existing local `expenses` rows remain the source of seller-entered external
  operating expenses;
- expense rows are evidence only when date, category and finite non-negative
  amount are valid;
- a missing expense row is never equivalent to a zero expense;
- explicit `expense_coverage` intervals record seller confirmation that expense
  accounting is complete for those dates;
- coverage for a requested Period Profit interval is complete only when the union
  of confirmed intervals covers every calendar day in the request;
- an empty covered period is an explicit zero-expense fact;
- an empty uncovered period remains unknown;
- partial expense rows may produce an observed profit-after-entered-expenses
  metric, but that metric must be labelled incomplete;
- only complete coverage may produce a complete
  `profit_after_external_expenses` derived value;
- external expenses are outside Ozon account net accrual and therefore may be
  subtracted from the account-level Period Profit exactly once;
- Ozon advertising/storage/return operations already present inside account
  net accrual remain excluded from this external-expense repository to avoid
  double subtraction;
- comparison semantics remain based on the existing Period Profit summary until
  external-expense coverage is proven for both compared periods;
- external expense coverage does not resolve return COGS recovery uncertainty,
  historical cost basis, compensation timing, or other accounting adjustments;
- accounting net-profit claim remains prohibited;
- local expense/coverage persistence is seller evidence input and does not
  authorize or perform any Ozon mutation;
- Decision 036 and Decision 037 remain unchanged.

Reason:

A local expense table without an explicit completeness marker cannot distinguish
"seller had no external expense" from "seller has not entered the expense yet".
Treating both as zero would overstate profit. Explicit coverage intervals make
zero/complete semantics evidence-bound while allowing known partial expenses to
be shown without overstating completeness.

Status:

Implemented

---

## Decision 039

Date:

2026-09-03

Topic:

Versioned Historical Product Cost Evidence

Decision:

Historical product cost used for return COGS evidence must come only from explicit,
effective-dated seller cost versions. The mutable current `product_costs` row is
not historical evidence and must never be backfilled into prior periods by
assumption.

Rules:

- existing `product_costs` remains the current product-cost configuration used
  by existing current calculations;
- a separate append-only `product_cost_history` evidence table stores explicit
  cost versions;
- every historical cost version requires `product_id`, at least one seller/Ozon
  product identifier (`sku` or `offer_id`), finite non-negative cost,
  currency, source and explicit `effective_from` date;
- no migration or automatic backfill from existing current cost rows is allowed;
- a current-cost update without explicit historical evidence does not create a
  historical cost version;
- duplicate versions for the same `product_id + effective_from` are rejected
  rather than silently overwritten;
- historical lookup for a sale date selects the latest explicit version whose
  `effective_from` is not later than that sale date;
- when product identity cannot be resolved uniquely, historical cost evidence is
  ambiguous and remains unconfirmed;
- missing historical cost remains unknown and is never replaced by current cost,
  zero or an inferred earlier value;
- deleting/changing the mutable current cost does not erase append-only historical
  evidence;
- confirmed historical cost may strengthen Return COGS evidence but does not by
  itself authorize COGS recovery or change Period Profit;
- return COGS recovery still requires independent sale-period lineage and
  saleable/restored inventory evidence, with compensation treatment kept
  separate;
- Decision 036 read-only Ozon boundary, Decision 037 monetary authority and
  Decision 038 external-expense contract remain unchanged.

Reason:

A single mutable current cost cannot prove the unit cost that applied when an
earlier sale occurred. Using today's cost for a historical return would create an
accounting claim from an assumption. Explicit effective-dated versions preserve
what the seller actually confirmed, allow future cost changes to be represented,
and keep unknown historical periods fail-closed.

Status:

Implemented

---

## Decision 040

Date:

2026-09-03

Topic:

Explicit Return Inventory Recovery Evidence

Decision:

Saleable/restored inventory recovery for Return COGS must be based on explicit
return-level evidence. Current stock snapshots, stock deltas, or the Returns API
visual placement status are not sufficient by themselves to prove that a returned
unit restored saleable inventory value.

Rules:

- a separate append-only `return_inventory_recovery_history` evidence table
  stores explicit return-level recovery confirmations;
- every evidence row requires exact return_id, posting_number, SKU, positive
  quantity, explicit recovery state, confirmation date and source;
- allowed recovery states are `SALEABLE_RESTORED` and `NON_SALEABLE`;
- absence of a recovery row remains unknown and is never treated as saleable,
  non-saleable or zero-value recovery;
- duplicate `return_id + confirmed_on` versions are rejected rather than
  overwritten;
- all versions for one return_id must preserve posting_number + SKU identity;
  identity drift makes the evidence conflicting and unconfirmed;
- the latest explicit confirmation may describe the current known recovery state,
  but its confirmation date does not by itself establish the accounting period in
  which COGS recovery should be recognized;
- recorded recovery quantity must exactly match the candidate return quantity
  before that candidate may be considered saleable-restored;
- compensated returns remain outside automatic saleable-recovery treatment;
- current Ozon stock observation or a positive stock delta must never be used as
  automatic proof of return recovery because other stock movements can produce the
  same change;
- confirmed saleable inventory recovery may strengthen Return COGS evidence but
  does not by itself authorize Period Profit adjustment;
- period attribution, originating sale quantity consistency and compensation
  accounting must remain independently proven before any COGS reversal;
- Decision 036, Decision 037, Decision 038 and Decision 039 remain unchanged.

Reason:

A stock snapshot shows only current quantity and cannot prove which movement
created it. A return being present at a return location likewise does not prove
that it became saleable inventory. Explicit return-level recovery evidence avoids
turning correlated stock movement into an accounting fact and preserves
fail-closed behavior.

Status:

Implemented

---

## Decision 045

Date:

2026-10-14

Topic:

Price Planning Scenario Isolation

Decision:

The unit-price calculator is a transient, read-only planning scenario. Scenario inputs and computed estimates must remain separate from observed Ozon facts and persisted business settings.

Rules:

- scenario overrides are kept only in short-lived runtime state and never write seller price, product cost, expense evidence, tax policy, finance history or factual unit-economics results;
- snapshots and callbacks are scoped to the active user/store and exact catalog SKU; callback versions prevent stale messages from mutating the current scenario;
- price arithmetic stays in the pure scenario service and tax behavior delegates to the existing `TaxService`;
- the current commission estimate is FBO-only and is not represented as a guaranteed quote for a new price; FBS is not calculated by applying an FBO rate;
- source refresh is bounded and separate from local recomputation; unknown source values stay unknown until explicitly supplied as scenario assumptions.

Reason:

Price planning changes assumptions frequently and must not alter or overwrite the shop's factual accounting or settings. Keeping the scenario transient and read-only lets the seller compare alternatives without turning projections into recorded facts.

Status:

Implemented

---

## Decision 046

Date:

2026-10-19

Topic:

Local Telegram polling instance ownership and graceful stop

Decision:

- one process per configured Telegram bot token and local OS user is enforced by a held kernel file lock in user-private local state;
- the token is represented only by a one-way SHA-256 namespace fingerprint; plaintext token and bot credentials never enter lifecycle files or output;
- status distinguishes process lock ownership from PTB readiness; `RUNNING` requires both the Updater polling and application update processing to be active;
- local stop uses loopback IPC authenticated by random process generation and a short-lived secret, then delegates shutdown to PTB lifecycle callbacks;
- PID metadata is informational and is never used to kill, signal or identify an unrelated process;
- the existing composition contract remains: `build_application()` does not acquire locks, open sockets, run polling or access seller APIs;
- foreground launch stays the default; background launch is an explicit PowerShell option; stop waits for confirmation and never falls back to force termination.

Reason:

Duplicate polling from another console or checkout can create Telegram conflicts and
make the active bot unclear. A held kernel lock safely represents ownership despite
stale PID files, while generation-authenticated loopback IPC provides a narrow,
local graceful stop path without process-wide kill behavior or a new web server.

Status:

Implemented. PR #705 Verify `39175656753` passed full Windows/Linux suites (3,443 tests each) and production Docker smoke; independent architecture review remains pending.

---

## Decision 047

Date:

2026-10-19

Topic:

Durable seller planning workspace

Decision:

- saved planning documents are explicit user-owned recipes and historical projections, separate from factual seller accounting, confirmed cost, tax settings and the in-memory scenario editor;
- documents are stored in additive, versioned planning tables in the existing tenant SQLite database and are always scoped to the active owner and store;
- persisted data is an allowlisted projection; callback tickets, credentials, raw API objects and transient session internals are excluded;
- writes use transaction boundaries, idempotency keys and expected-revision compare-and-swap; an old save cannot overwrite a newer revision;
- opening a saved plan is historical and source-free; refreshing is explicit and only exact-identity manual assumptions may carry forward;
- users choose whether refreshed data appends a revision or becomes a separate copy; archive/restore are reversible and physical deletion requires confirmation;
- corrupt records and unknown future schema versions remain untouched and return controlled errors.

Reason:

Sellers need to resume and compare hypothetical price plans without turning those
assumptions into accounting facts or silently replacing a newer plan. Keeping the
durable recipe separate from transient calculations makes scope, freshness and
revision conflicts explicit while preserving existing tenant databases.

Status:

Implemented. PR #706 Verify `39175669828` passed full Windows/Linux suites (3,454 tests each) and production Docker smoke; independent architecture review remains pending.

---

## Decision 048

Date:

2026-10-19

Topic:

Aggregate seller planning for an explicitly entered sales mix

Decision:

- a sales-mix forecast includes only exact saved-plan SKU identities with manually entered successful-sale quantities; unknown and explicit zero are distinct;
- the existing canonical per-sale calculation supplies already-rounded monetary components, and period-level fixed expenses are subtracted once from the combined pre-tax result;
- the existing `TaxService` is called once for the aggregate only when every included row and tax policy is complete and compatible;
- incomplete plans may expose a labeled confirmed subtotal, but never a final group profit or margin;
- any sum of individual SKU advertising caps is an indicative sum, not an optimized group budget and not a guarantee of group margin;
- a user-confirmed preview appends a new owner/store-scoped planning revision with expected-revision CAS; factual seller records and Ozon are not written or queried.

Reason:

Applying tax separately to each SKU can disagree with the seller's aggregate tax,
especially where a minimum tax applies. An explicit sales-mix document keeps
quantities and additional plan expenses reviewable while preserving the
separation between hypothetical plans and store facts.

Status:

Implemented. PR #707 Verify `39175679778` passed full Windows/Linux suites (3,466 tests each) and production Docker smoke; independent architecture review remains pending.

---

## Decision 049

Date:

2026-10-19

Topic:

Historical planning comparison and report exports

Decision:

- comparison reads two saved revisions in the same authenticated owner/store scope and never refreshes Ozon sources;
- input differences remain useful when projections cannot be compared, but derived revenue/profit/margin deltas require a compatible period, exact SKU set, tax policy and calculation version;
- margin deltas are presented as percentage points, not as a relative percent change;
- plan, advertising cap, sales mix, plan/fact and plan-comparison exports are user-owned report projections, separate from strict support-diagnostic JSON;
- screen and export consume the same bounded snapshot; missing values stay nullable with status/reason and are never serialized as zero;
- exports reuse the existing serializer, size/formula guards, owner/store validation and Telegram document sender.

Reason:

Sellers need to compare historical planning choices without treating different
periods or calculation rules as one controlled experiment. Reusing the existing
snapshot/export boundaries keeps reports consistent with the visible view and
separates user business data from anonymized support diagnostics.

Status:

Implemented. PR #708 code-head Verify `39175690904` passed full Windows/Linux suites (3,497 tests each) and production Docker smoke. The current review handoff is documentation-only; check the latest PR #708 Verify before closing O01. Independent architecture review remains pending.

---

## Decision 050

Date:

2026-10-19

Topic:

Planning document state CAS and bounded sales-mix inputs

Decision:

- Keep payload `revision` as the history index and introduce a separate monotonic `state_revision` for metadata and payload mutations. All update/rename/archive/restore/delete writes require both expected values and perform atomic compare-and-swap.
- Initialize and migrate planning schema metadata inside one SQLite `BEGIN IMMEDIATE` transaction with a unique singleton row; preserve existing document and revision data.
- Align sales-mix validation limits across Telegram/service/persistence, preserve readable legacy inputs when unchanged, and reject new oversized quantities, periods, expenses, or aggregates before Decimal-to-float tax calculation.
- Preserve a confirmed sales mix during an update only when the exact product identity scope remains unchanged; composition changes require new explicit quantities/preview.

Reason:

Revision-only CAS does not protect destructive actions against metadata changes,
and an update must not silently discard confirmed planning assumptions. Separate
state versioning keeps history semantics intact, while bounded inputs protect the
existing float-based tax service without changing its contract.

Status:

Implemented with R1–R10 regressions. Targeted H–O profile passed (**259**), documentation checks passed (**3**), and exact code head `d057031364e6d934f258fec2efa385a045f6e3bf` passed Verify `39221770481` plus repeat `39221764654` on Windows/Linux, compile and production Docker smoke. An additional docs-only update requires its own exact-head Verify; independent second review remains pending. No merge/deploy was performed.

# Current Project State


Date:

2026-09-03



# Test Status


Verification model: SHA-bound.

Latest full-suite baseline confirmed:

2195 passed on `9ca4497dda61615076b8203d0404502630ab7e81`.

GitHub Actions push verification run #1105 completed successfully for this exact main SHA.

See `project_brain/VERIFICATION_STATUS.md`.



# Stabilization Checkpoint


Completed:


[x] Full test suite stabilization


[x] Action Generator contract restored


[x] Action Executor compatibility restored


[x] Action context preservation restored


[x] Priority preservation restored


[x] Memory features remain compatible with existing pipeline



Result:


63 passed



---



# Project Direction


## Main Product


AI Business Assistant



Цель проекта:


Создание бизнес-ассистента-аналитика,
который читает и анализирует данные Ozon,
сравнивает периоды, объясняет риски,
приоритизирует проблемы и рекомендует действия,
но не изменяет состояние Ozon и не выполняет business mutations.



## Internal Development System


AI Development Agent



Назначение:


AI Development Agent является внутренним инструментом,
который ускоряет создание и развитие AI Business Assistant.



Основные задачи:


- уменьшение ручных действий при разработке
- поддержание Project Brain
- контроль документационного drift
- автоматизация тестирования
- ускорение внесения изменений



Архитектурная связь:


AI Development Agent

↓

Development Workflow

↓

AI Business Assistant



---



# Completed Features


[x] Intent detection


[x] Task creation


[x] Task lifecycle


[x] Pause


[x] Resume


[x] Cancel


[x] History


[x] Context


[x] Action Router


[x] Sales Executor


[x] Stock Executor


[x] Marketing Executor


[x] Priority system


[x] Action dependencies


[x] Conditional actions


[x] SKIPPED state


[x] Skip reason


[x] History response formatting


[x] Sales Intelligence Service foundation


[x] Sales Intelligence Integration v1


[x] Sales Intelligence Data Flow v1 - Context Propagation


[x] Sales Intelligence Production Wiring v1


[x] Sales Intelligence Business Data Input v1


[x] Stock Intelligence Foundation v1


[x] Stock Intelligence Integration v1


[x] Stock Intelligence Context Propagation v1


[x] Stock Intelligence Production Wiring v1


[x] Stock Intelligence Business Data Input v1


[x] Finance Intelligence Foundation v1


[x] Finance Intelligence Executor Integration v1


[x] Finance Intelligence Context Propagation v1


[x] Finance Intelligence Production Wiring v1


[x] Finance Intelligence Business Data Input v1


[x] Product-Level Finance Metrics v1


[x] Product Unit Economics Foundation v1.1


[x] Product Unit Economics Query v1


[x] Tax Configuration Foundation v1


[x] Product Unit Economics Production Wiring v1


[x] Product Unit Economics Telegram UI v1



---



# FAILED Execution Handling


[x] Exception interception


[x] FAILED action status


[x] Error message storage


[x] Failed execution test


[x] FAILED history event


[x] Error history storage


[x] Retry action preparation


[x] Retry execution test


[x] Retry history tracking


[x] Retry policy service


[x] Retry decision logic


[x] Retry allowed flag


[x] Retry limit service


[x] Maximum retry attempts


[x] Retry limit validation


[x] Retry blocked history


[x] Retry block event storage



Result:


63 passed



---



# Smart Planning


[x] Multi-level dependencies


[x] Dependency validation


[x] Dependency cycle detection


[x] Replan request trigger


[x] Replanning service


[x] Replanning integration


[x] Replanning execution flow


[x] Automatic replanning engine


[x] Plan correction



Result:


63 passed



---



# Autonomous Business Assistant


Phase 3 foundation completed:


[x] Feedback service


[x] Feedback integration


[x] Automatic feedback collection


[x] Memory service


[x] Feedback → Memory connection


[x] Memory storage


[x] Memory lookup


[x] Memory context in planning


[x] Memory-guided action generation


[x] Full Memory Agent Loop


[x] Memory compatibility stabilization



Completed goal:


Переход от системы выполнения действий
к системе накопления опыта и использования памяти.



Next planned changes:


1. Поддерживать SHA-bound CI verification на каждом новом main


2. Считать kernel-backed task persistence hardening закрытым; поддерживать только regression/release evidence без новых абстракций без конкретной необходимости


3. Считать seller-facing Product Decision Learning Coverage Queue v493-v502 завершённой: использовать её только как read-only очередь сбора feedback/observation evidence, не как business-priority surface


4. Следующий product/operational пакет выбирать по фактическому repo gap после сверки main; не продолжать learning wrappers автоматически


5. Не подключать canonical user-action advisory/checklist chain к Telegram, пока exact persisted Product Decision verification не будет явно пронесён через production Telegram lineage; v831-v840 укрепляет verifier, v841-v850 guidance, v851-v860 checklist, v861-v870 completion evidence, но runtime-подключение по-прежнему не выполнено


6. Поддерживать operator-only persistence diagnostics и Project Brain drift cleanup


7. Не включать Product Decision / Product Task Draft execution без отдельной архитектуры и авторизации


---



# AI Development Agent Infrastructure


AI Development Agent является внутренним ускорителем
создания AI Business Assistant.



Completed:


[x] Project Brain


[x] Architecture documentation


[x] Development rules


[x] Roadmap


[x] Test map


[x] Architecture decisions log


[x] Changelog


[x] AI Development Manager


[x] Project status command


[x] Test runner command


[x] Context generator


[x] Project analyzer


[x] AI Development Manager v4


[x] Project scanner


[x] Test analyzer


[x] Documentation-driven planning


[x] Development planner


[x] Development cycle automation


[x] Change Impact Analysis Service


---



# Current Architecture Level


Stage:


Task Orchestration Engine

+

Smart Planning

+

Autonomous Business Assistant Foundation

+

Development Autopilot Layer



---



# Current Work Queue


NEXT:


AI Assistant Product Development



---



# Previous Completed Phase


TASK:


Phase 4 - Development Infrastructure



Completed goal:


Создана инфраструктура разработки,
которая ускоряет развитие AI Business Assistant
через GPT + GitHub workflow.



# Current Development Task


TASK:


AI Assistant Product Development


Current Goal:


Развитие возможностей основного продукта AI Business Assistant.



---



# Planned Features


[x] FAILED action state


[x] Executor error handling


[x] Error history


[x] Retry execution


[x] Retry execution history


[x] Retry policy


[x] Retry limit


[x] Retry blocked history


[x] Multi-level dependencies


[x] Dependency validation


[x] Automatic replanning


[x] Plan correction


[x] Feedback loop


[x] Memory system


[x] Change Impact Analysis


[x] Documentation Drift Detection


[x] Automated development workflow


[x] Git checkpoint assistant


[x] Long-running tasks


[x] Self-improvement cycle



## Phase 1

Executor Reliability


[x] Completed



## Phase 2

Smart Planning


[x] Completed



## Phase 3

Autonomous Business Assistant


[x] Feedback loop


[x] Memory system


[x] Long-running tasks


[x] Self-improvement cycle



## Phase 4

Development Autopilot Layer


[x] Project scanner


[x] Documentation system


[x] Test analyzer


[x] Change Impact Analysis


[x] Documentation Drift Detection


[x] Automated Development Workflow


[x] Git Checkpoint Assistant


[x] Project Brain Synchronization


[x] Vector memory


[x] Completed



---



# Metrics


Tests:

SHA-bound verification active.

Latest confirmed full-suite baseline:
1901 passed on `84d714909d5082958bf2bb21a30b7b097eb17955`.

Verification source:
GitHub Actions push run #709, exact SHA-bound main verification with canonical `test-report.json` artifact.



Architecture:


Task Orchestration Engine

+

Smart Planning

+

Autonomous Business Assistant Foundation

+

Development Autopilot Layer



Documentation:


Project Brain active



Development Manager:


Active
---

# Current Unit Economics Validation — 2026-08-25

Completed:

[x] Current seller price from Ozon Price API
[x] offer_id / internal Ozon SKU separation
[x] current commission calculation
[x] fresh logistics from Ozon finance accruals
[x] last mile separated from logistics
[x] acquiring average from fresh finance accruals
[x] product cost integration
[x] explicit tax policy integration
[x] USN Income 6% production configuration validated
[x] rubles + percent-of-price presentation
[x] Telegram production wiring
[x] safe None handling for missing mandatory data

Validated production example:

SKU: hook-2

Seller price: 96.00 RUB
Commission: 13.44 RUB
Logistics: 17.85 RUB
Last mile: 1.55 RUB
Acquiring: 1.30 RUB
Product cost: 21.00 RUB
Tax: 5.76 RUB
Calculated profit per unit: 35.10 RUB
Margin: 36.56%

Finance sample:
236 sales / 2 complete days

Historical note:

At this checkpoint returns / buyout losses were not yet included because cancelled
FBO postings could not be reliably separated into pre-shipment cancellations and
real customer non-buyouts.

Current repository state supersedes that old "Next" item: dedicated returns/buyout
analytics, returns-finance attribution, observed return impact, and authorized return
financial-evidence services now exist.

Important current limitation:

Financial return-operation evidence and returns/buyout analytics are not equivalent
to complete return economics. Do not treat the current evidence as proof that all
return costs/losses are fully modeled in unit economics.

---

# Product Decisions v3 — 2026-08-28

Completed:

[x] Returns-aware product decisions
[x] Russian decision card with source metrics
[x] Assortment-wide decision overview
[x] Priority ordering for product decisions
[x] Decision summary counts in Telegram
[x] Seller article plus action label on product buttons

Preserved:

- decision thresholds;
- manual product drill-down;
- no autonomous action execution.

---

# Product Decisions v4 — 2026-08-28

Completed:

[x] 10-minute successful decision cache
[x] Cache expiry and mutation protection
[x] No caching of errors or insufficient decisions
[x] Telegram assortment pagination
[x] Eight products per page
[x] Previous / next navigation callbacks

Preserved:

- existing decision rules and thresholds;
- seller article callbacks;
- no autonomous action execution.

---

# Product Decision Memory v1 — 2026-08-28

Completed:

[x] Persistent successful decision snapshots
[x] Change-only history without repeated duplicates
[x] Previous decision and priority context
[x] Bounded retention per seller article
[x] Atomic JSON persistence
[x] Telegram decision transition explanation

Preserved:

- ProductBusinessDecisionService rules;
- product_memory SQLite schema;
- task and user memory;
- data/users.json;
- no autonomous action execution.

---

# Product Decision Feedback v1 — 2026-08-28

Completed:

[x] Useful feedback signal
[x] Not-relevant feedback signal
[x] Feedback bound to the latest decision snapshot
[x] Idempotent repeated feedback
[x] Telegram feedback buttons
[x] Safe missing-history and invalid-feedback responses

Preserved:

- feedback does not change decision rules;
- feedback does not execute actions;
- existing decision history retention remains unchanged.

---

# Product Decision Outcome Correlation v1 — 2026-08-28

Completed:

[x] Prior feedback linked to the next changed decision
[x] Priority decrease observation
[x] Priority increase observation
[x] Same-priority decision change observation
[x] No inference without explicit feedback
[x] Non-causal Telegram wording

Preserved:

- observations do not alter decision rules;
- observations do not prove action causality;
- no autonomous action execution.

---

# Product Decision Learning Summary v1 — 2026-08-28

Completed:

[x] Assortment-wide learning summary
[x] Snapshot, feedback, and outcome counts
[x] Product-level latest decision history
[x] Russian decision and priority labels
[x] Feedback and observation details in history
[x] Telegram navigation from overview and product card

Preserved:

- no success-rate claim on limited data;
- no causal claim;
- no influence on decision rules;
- no autonomous action execution.

---

# Safe Product Action Proposals v1 — 2026-08-28

Completed:

[x] ProductDecisionActionProposalService
[x] Replenishment review proposal
[x] Unit-economics review proposal
[x] Margin review proposal
[x] Monitoring-only proposal
[x] Manual-confirmation boundary
[x] Telegram next-step presentation
[x] Assortment actionable-proposal count

Preserved:

- no replenishment quantity inference;
- no price-change inference;
- execution_allowed is always false;
- Action/Executor workflow is not invoked.

---

# Product Action Proposal Confirmation v1 — 2026-08-28

Completed:

[x] Confirm or dismiss actionable proposal
[x] Latest-decision stale proposal guard
[x] Idempotent stored proposal status
[x] Telegram confirmation controls and Russian status
[x] Explicit executed=False response

Preserved:

- confirmation is stored intent, not execution permission;
- monitoring-only has no confirmation buttons;
- no quantity or price draft is inferred;
- no external API mutation or Action Executor.

---

# Confirmed Product Task Drafts v1 — 2026-08-28

Completed:

[x] Persistent ProductActionTaskDraftService
[x] Idempotent draft per decision snapshot
[x] Draft dismissal on proposal rejection
[x] Draft summary in Telegram
[x] Draft status on product card
[x] Dedicated production storage and wiring

Preserved:

- drafts are not executable tasks;
- no replenishment quantity or price is inferred;
- executed_count is always zero;
- no existing Action Executor or Ozon mutation path is invoked.

---

# Product Task Draft Review Lifecycle v1 — 2026-08-28

Completed:

[x] Automatic stale detection against current decision snapshot
[x] DRAFT / STALE / DISMISSED / ARCHIVED states
[x] Compact identifiers for new and legacy drafts
[x] Idempotent terminal archive action
[x] Telegram lifecycle counts and archive controls
[x] Current-card guard against old drafts

Preserved:

- lifecycle transitions never execute tasks;
- archived drafts cannot be reopened implicitly;
- no quantity, price, Ozon mutation, or Action Executor connection.

---

# Product Draft Review Queue Prioritization v1 — 2026-08-28

Completed:

[x] Separate ProductTaskDraftReviewQueueService
[x] Deterministic review score and priority category
[x] Explainable reason codes
[x] DRAFT and STALE queue scope
[x] Oldest-first stable tie breaker
[x] Telegram priority counts, reasons, and icons
[x] Production composition wiring

Preserved:

- queue priority does not alter product decisions;
- priority is not persisted as learned truth;
- no lifecycle mutation, task execution, or Ozon API call.

---

# Product Task Draft Detail and Audit v1 — 2026-08-28

Completed:

[x] Dedicated Telegram draft detail card
[x] Source proposal, priority, profit, and margin context
[x] CREATED / REOPENED / MARKED_STALE / DISMISSED / ARCHIVED audit events
[x] Event source, timestamp, and status transition
[x] No duplicate events for idempotent commands
[x] Honest legacy-history fallback
[x] Terminal archived detail without action controls

Preserved:

- audit facts do not influence decisions or queue score;
- old history is never inferred;
- detail and audit paths cannot execute tasks or mutate Ozon.

---

# Product Task Draft Readiness Checklist v1 — 2026-08-28

Completed:

[x] Separate ProductTaskDraftReadinessService
[x] Proposal-specific factual requirements
[x] Review-ready / needs-data distinction
[x] Explicit missing-field output
[x] Proposal-specific execution policy blockers
[x] Detail-card readiness section
[x] Review-queue readiness counts and item labels
[x] Production composition wiring

Preserved:

- review_ready never implies execution_ready;
- execution_ready_count remains zero;
- missing values are not inferred;
- checklist does not mutate decisions, drafts, or Ozon.


---

# Product Decision Learning Coverage Queue v1 — 2026-08-30

Completed:

[x] Per-SKU learning coverage from persisted Product Decision history only
[x] NEEDS_USER_FEEDBACK / NO_DECISION_HISTORY / WAITING_FOR_LATER_OBSERVATION states
[x] Deterministic learning-attention rank with exact SKU tie-break
[x] Latest-feedback semantics without treating old outcomes as future observation
[x] Fail-closed malformed, duplicate and cross-SKU history handling
[x] Telegram navigation and seller wording
[x] No Product Decision query call while opening the queue
[x] Production DI of the pure coverage builder

Verified product baseline:

- PR #219 head run #61: success
- merged main SHA: `ef8b52ad34740d5cbb657988866ec01ebfe7191b`
- push run #62: success
- full suite: 1321 passed, 0 failed

Preserved:

- queue rank is not business priority;
- no causality, success-rate or profitability claim;
- no Product Decision rule update;
- no Product Task Draft execution;
- no Ozon mutation;
- `automatic_execution_allowed=False`;
- `executed=False`.


---

# Product Decision Learning Coverage Navigation v1 — 2026-08-30

Completed:

[x] State-specific inline navigation from the per-SKU learning coverage queue
[x] Existing `product_decision:<sku>` route reused; no new runtime route
[x] Top-10 navigation matches visible queue ordering
[x] Return path to the full Product Decisions screen
[x] Forged or malformed navigation fails closed
[x] Queue opening remains read-only and does not query Product Decisions
[x] No direct feedback callback is emitted from the queue

Preserved:

- seller explicitly opens a concrete Product Decision before feedback;
- no Product Decision rule change;
- no Product Task Draft execution;
- no Ozon mutation;
- no persistence or finance/mapping change;
- `automatic_execution_allowed=False`;
- `executed=False`.


---

# Store Period Default Composition Hardening — 2026-08-30

Completed:

[x] Removed duplicate StorePeriodRunnerService initialization
[x] Missing period profit dependency fails closed with an explicit error result
[x] StorePeriodSummaryService rejects malformed runner output
[x] Default summary path no longer raises AttributeError on missing profit service
[x] Existing constructor DI remains backward compatible

Preserved:

- no new data source or invented financial state;
- no change to profit formulas;
- no Product Decision or execution wiring;
- no Ozon mutation;
- no data/users.json change.


---

# Unknown Advertising Financial Evidence v1 — 2026-08-30

Completed:

[x] Production advertising defaults to unknown instead of implicit zero
[x] Explicit advertising_cost=0 remains a valid known zero
[x] Business profit and margin stay unknown without advertising evidence
[x] Revenue and gross profit remain independently available
[x] Advertising and business-profit dashboards render unknown as «—»
[x] Sales analysis preserves unknown profit metrics instead of optimistic zero
[x] Tax errors remain visible when advertising is unknown

Preserved:

- no advertising auto-fetch or heuristic classification;
- no financial double counting;
- no change to Ozon fee formulas;
- no Product Decision rule change;
- no seller/business execution or Ozon mutation;
- no data/users.json change.


---

# Finance Context Evidence Hardening v1 — 2026-08-30

Completed:

[x] FinanceContextProvider fails closed on malformed period payloads
[x] Missing gross_sales / gross_profit no longer normalize to zero
[x] Non-finite and boolean financial facts are rejected
[x] Explicit numeric zero remains valid evidence
[x] Finance context output shape remains backward compatible
[x] Finance Intelligence uses gross-result wording instead of accounting-profit claims
[x] Finance executor presentation uses evidence-scoped labels

Preserved:

- existing revenue / gross-profit arithmetic for complete evidence;
- no extra expense inference;
- no tax / advertising / returns double subtraction;
- no accounting net-profit claim;
- no Product Decision or task execution wiring;
- no Ozon mutation;
- no data/users.json change.


---

# Stock Evidence Availability Hardening v1 — 2026-08-30

Completed:

[x] Missing stock dependencies no longer imply verified safe stock
[x] Empty or partial assortment evidence is marked unavailable
[x] Complete no-risk evidence is distinguished from unavailable evidence
[x] Confirmed low-stock action context remains backward compatible
[x] Stock Intelligence rejects malformed/non-finite/boolean/negative evidence
[x] Cross-product stock/sales evidence fails closed
[x] Explicit zero sales remains valid NO_SALES evidence
[x] General fallback does not claim “no critical problems” when stock evidence is unavailable

Preserved:

- existing low-stock threshold behavior for complete evidence;
- no replenishment quantity inference;
- no Product Decision rule change;
- no new stock execution route;
- no Ozon mutation;
- no data/users.json change.


---

# Sales Evidence Availability Hardening v1 — 2026-08-30

Completed:

[x] Configured missing/partial sales evidence no longer becomes a clean no-decline result
[x] Missing or malformed revenue comparison does not normalize to 0%
[x] Confirmed sales-decline action context remains backward compatible
[x] Complete non-decline comparison is explicitly distinguishable from unavailable evidence
[x] Partial configured AssistantEntryService path suppresses sales action
[x] Legacy no-data AssistantEntryService fallback remains backward compatible
[x] Sales Intelligence rejects malformed action context before analytics
[x] Missing required revenue/gross-profit metrics fail closed
[x] Unknown business profit/margin remain None
[x] Explicit numeric zero remains valid
[x] Missing comparison change no longer produces a false “stable” insight
[x] Sales executor renders unknown metrics as «—»

Preserved:

- existing sales-decline threshold: revenue change < 0;
- no Product Decision rule change;
- no Product Task Draft execution;
- no new sales execution route;
- no Ozon mutation;
- no data/users.json change.


---

# Executor Error-Result Lifecycle Integrity v1 — 2026-08-30

Completed:

[x] Executor `error=True` results enter the existing FAILED lifecycle
[x] Direct router `execute()` result contract remains backward compatible
[x] Non-dict and malformed executor results fail closed
[x] Missing executor error message uses stable `EXECUTOR_RETURNED_ERROR`
[x] Failed action no longer reaches `complete_action()`
[x] Task remains ACTIVE after executor-returned failure
[x] Pending action is cleared through the existing failure owner
[x] Failure history/feedback use FAILED semantics
[x] Existing retry policy and retry preparation remain active
[x] Successful executor results preserve the DONE lifecycle
[x] Exact feature/docs branch push verification is now available
[x] Pull-request merge-ref evidence is distinguished from exact branch-head evidence

Preserved:

- no new executor or production runtime route;
- no Product Decision or Product Task Draft execution change;
- no Ozon mutation;
- no retry-limit change;
- no task persistence-format change;
- no data/users.json change.


---

# Marketing Evidence Integrity v1 — 2026-08-30

Completed:

[x] Unsupported marketing executor no longer invents checked-channel evidence
[x] Marketing recommendation requires explicit evidence availability and context
[x] Missing/malformed marketing evidence fails closed
[x] Persisted router run enters existing FAILED lifecycle on missing evidence

Preserved:

- no marketing API or campaign mutation;
- no Product Decision/Product Task Draft execution;
- no Ozon mutation;
- no data/users.json change.

---

# Finance Evidence Availability Propagation v1 — 2026-08-30

Completed:

[x] Derived finance context success is marked available
[x] Derived finance context failure with period evidence is marked unavailable
[x] Missing period evidence does not invent finance availability
[x] Explicit finance context remains authoritative and available
[x] Unavailable finance evidence suppresses finance recommendation
[x] Unavailable finance evidence prevents false clean-business fallback
[x] Legacy finance_context-only recommendation callers remain compatible

Preserved:

- FinanceContextProvider output shape;
- existing finance arithmetic;
- no fee double subtraction;
- no accounting net-profit claim;
- no Product Decision/Product Task Draft execution;
- no Ozon mutation;
- no data/users.json change.

---

# Business Planner Result Integrity v1 — 2026-08-30

Completed:

[x] downstream recommendation error propagation
[x] malformed recommendation result fail-closed
[x] downstream planning error propagation
[x] malformed planning result fail-closed
[x] Action Plan execution error propagation
[x] execution actions/count integrity validation
[x] optional task-creation result validation
[x] general-only recommendation remains non-actionable

Preserved:

- existing constructor dependency injection;
- existing valid plan/action ordering;
- no Product Decision/Product Task Draft execution;
- no Ozon mutation;
- no business-evidence inference.

---

# Business Flow Result Integrity v1 — 2026-08-30

Completed:

[x] malformed intent result fail-closed
[x] execution result validation before success presentation
[x] execution error message preservation without false completed wording
[x] cancel/pause/resume downstream failure propagation
[x] task status/history/details/next malformed-result guards
[x] skip pre-mutation next-action validation
[x] skip result validation and post-mutation partial-state reporting
[x] continue next-action and pending-action result validation
[x] planner error propagation and actions/count integrity validation

Preserved:

- existing constructor dependency injection;
- existing valid execute/task/planner response structure;
- no Product Decision/Product Task Draft execution;
- no Ozon mutation;
- no automatic rollback or retry;
- no business-evidence inference.

---

# Product Decision Learning Telegram Result Integrity v1 — 2026-08-31

Completed:

[x] Learning Summary requires dict + explicit real boolean `error`
[x] Successful summary counts are non-negative non-booleans and internally consistent
[x] Missing summary evidence cannot become zero through optimistic defaults
[x] Decision History requires a real list instead of treating `None` or malformed payloads as empty success
[x] History records must match the requested SKU and carry valid decision, priority, timestamp, feedback and outcome semantics
[x] Unknown feedback is not mislabeled as `NOT_RELEVANT`
[x] Legitimate all-zero summary remains read-only success
[x] Legitimate empty history remains read-only success
[x] Stable seller-facing failures do not expose internal exception text

Verified product baseline:

- entering main `9bfa6a03e50d5c36a874e2ef30088e94efdb104c`: push Verify #440, 1655 passed / 0 failed, digest `sha256:b34831e479e283a17391174e150bf43b07e084510ff82a25eea7269f15f0cd92`
- final feature `7976dbdebdda82660f9fc5bbc7ebffd804990f8f`: push Verify #442, 1666 passed / 0 failed, digest `sha256:95787b366dc1fef928b8ba8f8571bb6053172cd6775ba70c4181901f083965c1`
- PR #286 synthetic merge `44ec86f9587831f6560e3e5ca2bbb9819abd4c29`: Verify #443, 1666 passed / 0 failed, digest `sha256:a46757c2e1baec4ad175c7afc3fcaf2dac5b3b08140d2723fa60f30cc73e6356`
- squash main `d3e9e61e4fee3a9e3aa1f1e34f2e7a1da8cf931c`: push Verify #444, 1666 passed / 0 failed, digest `sha256:67af33c7c3c17dd68d0339edcf58e86fb934925ec2a318fd0615f3f0168fb77c`

Preserved:

- Product Decision rules and thresholds;
- persistence behavior and interaction semantics;
- Product Task Draft remains non-executable;
- no Action Executor connection;
- no business mutation authorization, quantity/price inference, or Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Telegram Analyze / Plan History Integrity v1 — 2026-08-31

Completed:

[x] assistant result validated before analyze/plan success-history persistence
[x] explicit assistant failure records no success history
[x] malformed assistant result fails closed before history side effects
[x] valid success records exactly one expected history event
[x] explicit history persistence failure is not hidden
[x] malformed/exceptional history persistence remains unknown; no rollback is fabricated
[x] exception text is sanitized

Verified product baseline:

- entering main `9c2f783710e125b183e8a314e1ac4c2eac1754f1`: #449, 1666 passed / 0 failed, digest `sha256:a292cffdbb1309e47f33c028062ce699fd1364f18f3db1007cf50e46295b51fa`
- final feature `dd6a5984026f591941fa0f2db62fc260a48f9e02`: #451, 1674 passed / 0 failed, digest `sha256:328c9cc03f7b0b8e292ceb1e42cc78895ba5f86bc32875916c4fc5a5d46ecd02`
- PR #288 synthetic merge `83a8863f79f3ad76d721d4f7fd9eee2ed28a2b20`: #452, 1674 passed / 0 failed, digest `sha256:3c38001164cc6a7eb1b9f2838356843aff9a546ce7f15c5048eed2966251da3c`
- squash main `1bd23e97a565e15b2c2ef6e2067278eacac6caa0`: #453, 1674 passed / 0 failed, digest `sha256:46778bcf50f95fbf335d2d03c2e64aedf648461ec980818c8348fa8d627fca26`
- no failed/cancelled intermediate production SHA occurred in v766-v773
- `externally_verified=False`


---

# Telegram History / Memory Read Integrity v1 — 2026-08-31

Completed:

[x] missing History service is unavailable, not empty success
[x] missing Memory service is unavailable, not empty success
[x] missing user context is failure, not zero/clean evidence
[x] History/Memory read exceptions are sanitized
[x] results require dict + real boolean error
[x] History success requires list; Memory success requires dict
[x] explicit downstream failure is preserved
[x] legitimate empty history and memory remain success

Verified product baseline:

- entering main `c889ff8614c589853b3a29b41caf739067672db0`: #457, 1674 passed / 0 failed, digest `sha256:8eac2e70c655e3c8d3974aa05efdbdfa53b47db31acb8f1a70bfc23684bcc0d6`
- final feature `f4b9b2b8c840a9b5245eb19bfe04430196bc565c`: #459, 1684 passed / 0 failed, digest `sha256:afaafbe46852fe59d83140d69ef0c891db5ebbaeeb55141d83d4b5578427a496`
- PR #290 synthetic merge `69d5928a49ab871fa845b25362fcd581173db484`: #460, 1684 passed / 0 failed, digest `sha256:039b2734f83708c1b48acb6706a16afc214af30fba459ac60afb77c9c50e648c`
- squash main `f432814d74ee4e175d291b69c79767d86d506e0a`: #461, 1684 passed / 0 failed, digest `sha256:e4a08c01b1fc1a83019ca8c947954ce0bf7321d4409e79687263dc8efa03d7b3`
- no failed/cancelled intermediate production SHA occurred in v774-v783
- `externally_verified=False`


---

# Telegram Context Preparation Integrity v1 — 2026-08-31

Completed:

[x] analyze/plan validate last_action context update before current_task update
[x] failed/malformed first context update stops assistant and history side effects
[x] current_task update result is validated independently
[x] failure after successful last_action reports partial committed context state
[x] malformed/exceptional second update remains unknown and does not fabricate rollback
[x] context exception text is sanitized
[x] internal TypeError is not retried
[x] valid preparation still invokes assistant once and history once
[x] optional no-service/no-user context behavior remains compatible

Verified product evidence:

- entering main `656ff93a0cba3194481b007c288f0eeadbaf1441`: push Verify #465, 1684 passed / 0 failed, digest `sha256:69bbe78f6231f4824e1d5fec9f46e09edea685e6ecba001ec75fca57f73e3ed8`
- cancelled intermediate `67e08c87de7564dc76c60fe2e9caebf05ba8f793`: push Verify #466, conclusion cancelled; test step completed 1693 passed / 0 failed; digest `sha256:0f6297bec68de51f7f461208d22f6d63d5f03e39bd8b5b4f39bb8edb9a9495eb`; cancelled evidence only, not green
- final feature `80f85b1b45e1e49279c334078c5991eac2757cc7`: push Verify #468, 1693 passed / 0 failed, digest `sha256:9da810f8425014178cd51fa58fd682582af85d11042998ff3c0c4df8be0e204d`
- PR #292 synthetic merge `978b6e0170693ac5d8d39471dd45983ab394c0c3`: Verify #469, 1693 passed / 0 failed, digest `sha256:0cb7f1a3be2f36c446597636103e4b8778072da5c5e1ffdd8a0abcc15603aaa8`
- squash main `a7748785341ccea0a459ec06c7de460213cec038`: push Verify #470, 1693 passed / 0 failed, digest `sha256:b1fee9bfe0ccdf6d154bd2a2a3786ecd5515fdc1b0ceb7f53dd87bcec9138259`
- `externally_verified=False`


---

# Product Task Draft Freshness Telegram Presentation Integrity v1 — 2026-08-31

Completed:

[x] malformed readiness/freshness metadata fails closed before presentation
[x] partial freshness count maps cannot invent missing categories as zero
[x] malformed optional evidence maps do not become seller-facing synthetic zeros
[x] invalid detail status/age/reasons/coverage/guidance fails closed with stable non-secret result
[x] unknown enum strings are not surfaced as business facts
[x] legitimate all-zero freshness counts remain success
[x] legitimate UNKNOWN freshness and evidence-limited guidance remain read-only success
[x] Product Task Draft remains non-executable

Verified product evidence:

- entering main `3f59d0d71f4ac5dea9e2b915d6b4e0a7fc7008c5`: push Verify #474, 1693 passed / 0 failed, digest `sha256:a334436fd6e357ab6c9948baf907d472e67331442860fdf8fa0c15d5a3afeff0`
- final feature `e0cbd9e4ba3e56600e81f76d7740ef381dbfb124`: push Verify #476, 1703 passed / 0 failed, digest `sha256:b35bb81059445bcc1ca089d5237874461b904ec7795d08db69c2d5383179349a`
- PR #294 synthetic merge `1fc456087126b0cc91e6b3354a6560477a989b4c`: Verify #477, 1703 passed / 0 failed, digest `sha256:f286f803fc87a2c4a65c4f32afb6d606df31635c5b1ad7be1b1aaae21cc0e231`
- squash main `701b5a31575a2e37d76da22af260c206d4a68b50`: push Verify #478, 1703 passed / 0 failed, digest `sha256:640190ca4afe1dad7c2aa6cc326b351064e44121cd539db488f7d7e5eddf8848`
- no failed/cancelled intermediate production SHA occurred in v793-v802
- `externally_verified=False`


---

# Telegram Adapter Runtime Exception Containment v1 — 2026-08-31

Completed:

[x] assistant dispatch exceptions are contained at the Telegram adapter boundary
[x] button-handler exceptions are contained without retry-after-exception
[x] internal TypeError is not retried with legacy arity
[x] legacy arity selection remains pre-call only
[x] keyboard-builder exceptions do not claim successful start
[x] internal exception text is not exposed to sellers

Verified product evidence:

- entering main `ad3692c46e31d4eceeef504e4b55d7cbaa829a09`: push Verify #482, 1703 passed / 0 failed
- cancelled duplicate branch run #483 remains cancelled evidence only
- failed intermediate `c3336160fccddbc25a9d8e2b1f7aeccccaa8be70`: push Verify #484, 1710 passed / 1 failed
- final feature `21776a8cdd61dd35e28a885b5c573a2db3b15c92`: push Verify #485, 1711 passed / 0 failed
- PR #296 synthetic merge `929a1bd4c8ace607ff0bf6c67924aa14ec84b612`: Verify #486, 1711 passed / 0 failed
- squash main `01300c69d1ab54731657ea741687cc728c9e5600`: push Verify #487, 1711 passed / 0 failed
- `externally_verified=False`

Preserved:

- no Product Decision/Product Task Draft execution
- no Ozon mutation
- no quantity or price inference
- `data/users.json` unchanged


---

# Post-Decision Observation Integrity v1 — 2026-09-01

Completed:

[x] malformed checklist and later-decision inputs fail closed
[x] checklist status requires explicit error=False and USER_REPORT evidence
[x] numeric identifiers are not coerced into canonical identities
[x] later decision requires explicit boolean error state
[x] explicit downstream decision failure remains failure
[x] decision type / priority / confidence are validated against canonical values
[x] reasons require a real list of non-empty strings
[x] valid observation remains observation-only and non-causal

Verified product evidence:

- entering main `6d06cca860fbc1b423db02f0166554c562e2b67c`: push Verify #492, 1711 passed / 0 failed, digest `sha256:365511645081a003af4df8d00daf2e78c865d0e81b066d40557ffc2724672064`
- final feature `68c42c5fe4331d776eefe828263dfb930e9c8cd7`: push Verify #494, 1721 passed / 0 failed, digest `sha256:45f9677ae94b941606bfd4ef99ace1722c100d265e7e4354e15e1d6e8823998f`
- PR #298 synthetic merge `ffee00d5b609aa8c0e2c547db0e587dd4be93b94`: Verify #495, 1721 passed / 0 failed, digest `sha256:c184f12cabf364705cc115c94fb8bf7a0d2911d1f66a6b93583c7b40e44bdd8f`
- squash main `cc485098da06834f31fcd09430d83bd96b96f1e1`: push Verify #496, 1721 passed / 0 failed, digest `sha256:9ad01f64be4b80f26bf79cdf8f8127339aa4e88453542d8b27a5b92eba7612c5`
- no failed intermediate production SHA occurred in v811-v820
- `externally_verified=False`

Preserved:

- no Product Decision recomputation or mutation
- no Product Task Draft execution
- no Action Executor connection
- no Ozon mutation
- `data/users.json` unchanged


---

# Task Persistence Operator Presentation Integrity v1 — 2026-09-01

Completed:

[x] operator operational/release/provenance presentation requires explicit error=False
[x] blockers, warnings and incident categories require real unique string lists
[x] operational counts/state/attention claims are internally consistent
[x] release-ready / incident / human-review claims are validated
[x] provenance revision and CI-binding metadata is structurally validated
[x] external-verification and execution/mutation overclaims fail closed
[x] valid operator messages remain read-only and non-sensitive

Verified product evidence:

- entering main `cc485098da06834f31fcd09430d83bd96b96f1e1`: push Verify #496, 1721 passed / 0 failed
- failed intermediate `41c289221c100ce4dc1462603b42349434f2f406`: push Verify #498, 1730 passed / 1 failed; failure was a new test wording expectation and remains failed evidence
- final feature `a0e977595238dd256e9ae0d54e68ac337b04bb91`: push Verify #499, 1731 passed / 0 failed, digest `sha256:173173c93a222338ef8efd942fcb4a9af425df2e9768d6530f2d957c7b2c1cc6`
- PR #299 synthetic merge `c77df0221826e27e444f3d68150419e4adf9bc8d`: Verify #500, 1731 passed / 0 failed, digest `sha256:8f80f8bf4a7c0a4c03a912bdd4adeead94198f10b4e262e776eb3f88292b2f95`
- squash main `c2f1bd3d26fc5e2be33d725b8ecd2898a7b1dbfa`: push Verify #501, 1731 passed / 0 failed, digest `sha256:30db2fb7e7f68ed1460aee79cafee957467eccfd0468bacaa1953816e0340d09`
- `externally_verified=False`

Preserved:

- task persistence ownership and storage format
- no automatic retry or lock deletion
- no business execution readiness
- no Product Decision/Product Task Draft execution
- no Ozon mutation
- `data/users.json` unchanged


---

# Product Decision Persistence Verification Integrity v831-v840 — 2026-09-01

Completed:

[x] Non-mapping persistence-verification application input fails closed

[x] Product Decision lineage IDs and SKU are not coerced from non-string identities

[x] Explicit persisted-preview error markers are structurally validated

[x] Canonical decision type, priority and confidence are required

[x] Reasons require a real non-empty list of non-empty strings

[x] Durable history snapshot semantics fail closed before verification success

[x] Recorded-at lineage requires an explicit string binding

[x] Valid verification remains read-only, non-executable and externally_verified=False

Verified exact main:

`a3aa88f351985e8519f754923880165f96fb29ad`

GitHub Actions push Verify #518: 1741 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring in this package;
- no Ozon mutation;
- `data/users.json` unchanged.


---

# Product Decision User Action Guidance Integrity v841-v850 — 2026-09-01

Completed:

[x] Guidance accepts only mapping-shaped verification input

[x] Verification/application IDs and SKU require canonical non-empty strings

[x] Explicit verifier error=False and verified status are required

[x] Non-empty verification mismatch evidence blocks seller guidance

[x] External-verification and execution/persistence overclaims fail closed

[x] Verified recorded-at is bound to the exact durable snapshot timestamp

[x] Priority and confidence use canonical enums

[x] Reasons require real non-empty string-list evidence

[x] Valid guidance carries exact verified lineage forward without enabling execution

Verified exact main:

`e793ca7ab241d54a12af8b3b402b1dc862652bf2`

GitHub Actions push Verify #534: 1751 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no persistence owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring for the newer user-action chain;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Checklist Integrity v851-v860 — 2026-09-01

Completed:

[x] Checklist accepts only mapping-shaped guidance input

[x] Guidance / verification / application IDs, SKU and verified-recorded-at require canonical non-empty strings

[x] Explicit guidance error=False, ready status and decision-persistence verification are required

[x] Verification remains bound to the persistence application ID

[x] External-verification and persistence/execution overclaims fail closed

[x] Decision/action pairing, priority, confidence, title and reasons are structurally validated

[x] Manual checklist steps require real non-empty strings and are never coercively stringified

[x] Valid checklist carries exact verified persistence lineage forward without enabling execution

Verified exact main:

`405fdea64008e21173e7851e8b370b63eae7ef73`

GitHub Actions push Verify #550: 1761 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no persistence owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring for the newer user-action chain;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Completion Evidence Integrity v861-v870 — 2026-09-01

Completed:

[x] Completion evidence accepts only mapping-shaped checklist input

[x] Checklist / guidance / verification / application IDs, SKU, item ID and verified-recorded-at require canonical strings

[x] Exact guidance → verification → application lineage is preserved

[x] Explicit checklist error=False, ready status and persisted-decision verification are required

[x] Non-string completion decisions are not coerced

[x] External-verification and persistence/execution overclaims fail closed

[x] Item count, completed count and checklist item structure are validated

[x] User-reported completion carries verified persistence lineage forward without enabling execution

Verified exact main:

`c788760babc8b0c6becb886f37937f20d5d09028`

GitHub Actions push Verify #567: 1771 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no persistence-owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring for the newer user-action chain;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Completion Persistence Integrity v871-v880 — 2026-09-01

Completed:

[x] Completion persistence accepts only mapping-shaped evidence input

[x] Exact completion → checklist → guidance → verification → application lineage is required

[x] Completion status, decision and user-reported boolean are mutually consistent

[x] Root and revision evidence IDs use canonical deterministic lineage

[x] Malformed storage containers and records fail closed

[x] Explicit save=False is not reported as durable success

[x] Successful persistence carries exact verified lineage and item/revision metadata forward

[x] Completion revisions preserve verified lineage without enabling execution

Verified exact main:

`834df2a9ded1c3e05731a9c249683d15b188c661`

GitHub Actions push Verify #584: 1781 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no persistence-owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring for the newer user-action chain;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Completion Revision Predecessor Integrity v881-v890 — 2026-09-01

Completed:

[x] Completion revision 2+ requires exactly one durable predecessor

[x] Duplicate predecessor IDs fail closed as ambiguous

[x] Predecessor exact verified lineage and user-owned safety state are validated

[x] Predecessor status/decision/report consistency is validated

[x] Revision 3+ requires canonical predecessor revision/root/previous-ID lineage

[x] Duplicate current revision IDs fail closed

[x] Valid root → revision 2 → revision 3 requires actual durable predecessor records

Verified exact main:

`73c349d50dad1a5562a09777df5a69f661869645`

GitHub Actions push Verify #599: 1791 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no persistence-owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Checklist Status Persistence Lineage Integrity v891-v900 — 2026-09-01

Completed:

[x] Checklist-status input and report collection shapes fail closed

[x] Exact checklist → guidance → verification → application lineage is required

[x] Matching persisted USER_REPORT receipts require canonical verified lineage

[x] Matching malformed receipts cannot degrade into NO_USER_REPORTS

[x] Completion revisions require real integers and canonical root/evidence/previous IDs

[x] Duplicate item+revision receipts fail closed as ambiguous

[x] Per-item persisted revision chains must be contiguous from revision 1

[x] Valid aggregate output carries verified persistence lineage while remaining non-executable

Verified exact main:

`3dec82f8aa93c1a35a699aa9270dcfd8e91c1f46`

GitHub Actions push Verify #616: 1801 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no persistence-owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Post-Decision Observation Lineage Integrity v901-v910 — 2026-09-01

Completed:

[x] Canonical checklist-status ID and exact checklist/guidance/verification/application lineage required

[x] Persisted Product Decision verification preserved into observation

[x] USER_REPORTED_COMPLETE requires exact item/reported/completed consistency

[x] Reported/completed item identities remain canonical and non-coercive

[x] Later Product Decision result remains explicit and SKU-bound

[x] Observation carries verified lineage while remaining read-only, non-causal and non-executable

Failed intermediate evidence retained:

`0896d8112971966aec9fb61c7a2250436f19d76a` / Verify #623 / 1804 passed / 7 failed.

Verified exact main:

`c7c864814ec609b0f2c58b4578a522b2e5e8dad1`

GitHub Actions push Verify #626: 1811 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no persistence-owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Post-Decision Outcome Lineage Integrity v911-v920 — 2026-09-01

Completed:

[x] Observation → outcome boundary requires exact persisted Product Decision lineage

[x] Complete USER_REPORT counts and item identities remain canonical

[x] Prior/later decision type, priority, confidence and reasons require canonical contracts

[x] Prior SKU must match observed SKU exactly

[x] Noncanonical MEDIUM priority is rejected

[x] Canonical NONE priority is supported for INSUFFICIENT_DATA outcomes

[x] Valid outcome remains non-causal, externally unverified and non-executable

Verified exact main:

`82867cd9efb6a0b4a187d72ca097ee6bda0c0f39`

GitHub Actions push Verify #634: 1821 passed / 0 failed.

Preserved:

- no Product Decision threshold/rule change;
- no persistence-owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Learning Summary Outcome Integrity v921-v930 — 2026-09-01

Completed:

[x] Non-list outcome collections fail closed

[x] Non-mapping/malformed outcome rows fail closed instead of disappearing

[x] Exact v911-v920 outcome lineage and persisted Product Decision verification required

[x] Complete USER_REPORT evidence remains exact through learning summary

[x] Unsafe or contradictory outcome classification blocks

[x] Duplicate outcome IDs cannot inflate descriptive learning counts

[x] Canonical NONE priority outcomes remain valid; MEDIUM remains rejected

[x] Only a real empty list can produce zero-observation success

Failed intermediate evidence retained:

`21051b20acdfc0036a15d875d01b488283791ff3` / Verify #640 / 1830 passed / 1 failed.

Verified exact main:

`b492b655030791d5e703c8aa607d2763d455e486`

GitHub Actions push Verify #643: 1831 passed / 0 failed.

Preserved:

- no Product Decision threshold/rule change;
- no persistence-owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Learning Evidence Quality Summary Integrity v931-v940 — 2026-09-01

Completed:

[x] Learning summary input and explicit success are validated

[x] Counts are exact integers and never string/missing coercions

[x] Outcome/priority/SKU aggregate maps must be canonical and mathematically consistent

[x] Outcome IDs are exact, unique, and count-bound

[x] Zero evidence requires truly empty aggregates

[x] Existing evidence-quality thresholds remain unchanged

Failed intermediate evidence retained:

`849b0d0e78e441f3080631419ecbc0ea192890ec` / Verify #649 / 1840 passed / 1 failed.

Verified exact main:

`9a504323b6b4bb0adb2a6d5a75507b4c0b6f19f9`

GitHub Actions push Verify #652: 1841 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision User Action Learning Confidence Evidence Integrity v941-v950 — 2026-09-01

Completed:

[x] Learning evidence-quality input and explicit success are validated

[x] Counts are exact integers and never string/missing coercions

[x] Quality name and score must match actual sample shape

[x] Outcome/priority/SKU aggregate maps remain mathematically consistent

[x] Outcome IDs remain exact, unique and count-bound

[x] Existing confidence thresholds remain unchanged

[x] Confidence output remains descriptive-only and non-executable

Verified exact main:

`0671c0a0b06c662e935b4dcbf00e4cad12e32175`

GitHub Actions push Verify #660: 1851 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no persistence-owner change;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram production wiring;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Action Proposal Result Integrity v951-v960 — 2026-09-01

Completed:

[x] Action proposal result must be a mapping

[x] Proposal safety booleans and automation prohibition are exact

[x] Proposal SKU / priority / decision type / reasons remain Product Decision-bound

[x] Proposal type and confirmation semantics are decision-bound

[x] Proposal exceptions fail closed without secret leakage

[x] Malformed proposal is not cached and cannot enter task-draft lifecycle

[x] Assortment query fails closed instead of counting malformed proposal state

[x] Telegram renders neutral failure without proposal controls

Verified exact main:

`7637177202c21d3f2894105e39137efd86855b8c`

GitHub Actions push Verify #668: 1861 passed / 0 failed.

Integration finding:

- verified Product Decision user-action guidance/checklist remains intentionally unwired from Telegram;
- current durable Product Decision history does not store exact persistence-application receipt lineage;
- do not synthesize lineage IDs or invoke persistence application as a read side effect.

Preserved:

- no Product Decision rule/threshold change;
- no new persistence owner;
- no Product Task Draft execution;
- no Action Executor connection;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision History Context Result Integrity v961-v970 — 2026-09-01

Completed:

[x] History record context is mapping-only and whitelisted

[x] History context cannot overwrite Product Decision identity/error fields

[x] Malformed or exceptional history context becomes explicit unknown/unavailable state

[x] Unknown history count remains None and is not coerced to zero

[x] Invalid history context is not cached

[x] Invalid history context cannot enter task-draft lifecycle

[x] Telegram latest history rejects malformed, cross-SKU and unknown-status records

[x] Telegram task draft attachment requires exact SKU/proposal/revision and non-execution safety

Verified exact main:

`10977368ac4179f1f7168943a38fcdbc01ecfd78`

GitHub Actions push Verify #677: 1871 passed / 0 failed.

Preserved failed evidence:

- `bfcc3551166431288f38ba0c06912133bed56818`: Verify #674, 1870 passed / 1 failed;
- failure was a production NameError in the new draft-copy path;
- final feature head `ab24a87c19072b5bbb3b9efd6b1630b513bf6645`: Verify #675, 1871 passed / 0 failed.

Preserved:

- no Product Decision rule/threshold change;
- no new persistence owner;
- no Product Task Draft execution;
- no Action Executor connection;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Unit Economics Returns Finance Impact Integrity v971-v980 — 2026-09-01

Completed:

[x] Returns impact requires explicit success/error contract

[x] Complete/classification/finance markers are exact booleans

[x] Required categories and counts are validated without zero coercion

[x] Observed/matched/event count consistency is enforced

[x] Invalid evidence cannot become known zero return cost

[x] Invalid evidence cannot become confirmed risk-adjusted profit

[x] Invalid evidence cannot remove returns from missing data

[x] Valid estimated and confirmed paths preserve prior numeric behavior

Verified exact main:

`db5ab92503f499dfe470402ffefc00b15b9c6e59`

GitHub Actions push Verify #686: 1881 passed / 0 failed.

Preserved failed evidence:

- `b4f0d33d163ee0a81d0252e466519169c55fd1f2`: Verify #683, 1880 passed / 1 failed;
- failure was a legacy cache fixture using a pre-contract minimal success shape;
- production validation remained strict;
- final feature `0a2ece03b60e019b264b5ecda8a010bca873e7bb`: Verify #684, 1881 passed / 0 failed.

Preserved:

- unknown finance values remain unknown;
- no Product Decision threshold/rule change;
- no new persistence owner;
- no Product Task Draft execution;
- no Action Executor connection;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Result Integrity v981-v990 — 2026-09-01

Completed:

[x] Product Decision service result must be a mapping

[x] Unexpected error/code injection is rejected

[x] Product ID and SKU are exact query-bound identity

[x] Decision type and priority pairing is canonical

[x] Confidence, reasons and missing-data contracts are validated

[x] Invalid decision cannot reach history/proposal/cache/draft lifecycle

[x] Invalid decision gets deterministic seller-safe Telegram failure

Verified exact main:

`5f0534bb72dba2471c3c339a69cd7041552dfb4a`

GitHub Actions push Verify #698: 1891 passed / 0 failed.

Cancelled intermediate evidence retained:

- `f21c1ca4b21b57a634a502ecb754e93fabb78e18`: Verify #693 cancelled;
- `689fd2b9db65861f8853251accb0f2a3e0cf86d8`: Verify #694 cancelled.

Failed intermediate evidence retained:

- `8a286947bdc5862834a05794e330d87ef370ffe7`: Verify #695, 1889 passed / 2 failed;
- failure source was a legacy freshness fixture with noncanonical empty reasons;
- final feature `8b90c11763622cc413802a488171738cf2332a1a`: Verify #696, 1891 passed / 0 failed.

Preserved:

- no Product Decision threshold/rule change;
- no new persistence owner;
- no Product Task Draft execution;
- no Action Executor connection;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Assortment Overview Integrity v991-v1000 — 2026-09-01

Completed:

[x] Overview decision rows require explicit success and unique SKU identity

[x] Decision type → priority pairs are canonical

[x] Decision counts are recomputed and exact

[x] Proposal counts are recomputed and exact

[x] Actionable count is recomputed from exact booleans

[x] Nested proposal execution remains prohibited

[x] Contradictory overview state cannot generate seller keyboard

[x] Valid mixed overview remains deterministic and non-mutating

Verified exact main:

`84d714909d5082958bf2bb21a30b7b097eb17955`

GitHub Actions push Verify #709: 1901 passed / 0 failed.

Preserved failed evidence:

- `3fe8ef0caa6b03a5dabbabae463cb0037a4c9ca5`: Verify #704, 1882 passed / 9 failed;
- `86b6e9063c1a9cfa500d4e0409ba6668623c5321`: Verify #705, 1892 passed / 9 failed;
- `0b2da626f71a45adf54f0f9f0dbfd8b5a8e75353`: Verify #706, 1898 passed / 3 failed.

Production validation was not weakened; legacy test fakes were aligned to the canonical producer contract.

Preserved:

- no Product Decision threshold/rule change;
- no new persistence owner;
- no Product Task Draft execution;
- no Action Executor connection;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Task Draft Lifecycle Result Integrity v1001-v1010 — 2026-09-01

Completed:

[x] Task-draft reconcile result requires an exact explicit mapping contract

[x] Lifecycle error/executed/execution_allowed markers are exact safety booleans

[x] stale_count is a non-negative exact integer and equals stale_drafts length

[x] Stale drafts remain exact-SKU and canonical proposal-bound

[x] Current Product Decision revision cannot be reported as stale

[x] Stale draft status is exactly STALE

[x] Stale drafts remain executed=False and execution_allowed=False

[x] Malformed/exceptional lifecycle result fails closed with deterministic non-secret code

[x] Invalid lifecycle result is not cached and assortment query fails closed

[x] Valid lifecycle is attached as a defensive copy

Verified exact main:

`288c6452703eee4082414d1ad36680b4ddf02caa`

GitHub Actions push Verify #717: 1911 passed / 0 failed.

Feature and integration evidence:

- final feature `12e4f1d4f38296b8f46680302478f377121644a8`: Verify #715, 1911 passed / 0 failed;
- PR #336 synthetic `005ac13b1fbb01bb6e95314d1f8c89b994ba85c6`: Verify #716, 1911 passed / 0 failed;
- no failed production SHA in this package.

Preserved:

- no Product Decision rule/threshold change;
- no new persistence owner;
- no Product Task Draft execution;
- no Action Executor connection;
- no Telegram user-action persistence wiring;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Unit Economics Result Integrity v1011-v1020 — 2026-09-01

Completed:

[x] Unit Economics query exceptions are sanitized before Product Decision generation

[x] Downstream `error` must be an exact boolean

[x] Explicit downstream `error=True` remains unknown economics, never zero

[x] Successful economics requires exact boolean `available`

[x] Malformed/duplicate/non-string `missing_fields` is rejected

[x] Boolean, NaN and infinity decision-finance values are rejected

[x] `available=False` cannot claim profit or margin

[x] Confirmed returns-adjusted profit requires complete returns finance evidence and known per-delivered-unit reserve

[x] Estimated returns profit requires exact estimate readiness plus required estimate evidence

[x] Invalid economics result fails closed with deterministic non-secret code and is not cached

Verified exact main:

`982dc4f58fec6172a4fa99475ae72800c107981f`

GitHub Actions push Verify #727: 1921 passed / 0 failed.

Failed evidence preserved:

- `c27b1fbfba804d36167855228f1881c08c4ef506`: Verify #723, 1917 passed / 4 failed;
- `1114863bdc5b23969fe8cf2d3c9166fe5e7cd523`: Verify #724, 1918 passed / 3 failed.

Final feature and integration evidence:

- final feature `fa9cd0e874347ba00320c8e9c36c85d0efb530a0`: Verify #725, 1921 passed / 0 failed;
- PR #338 synthetic `8014a74ae903863da672ee4b82f9fb565ad3d6cc`: Verify #726, 1921 passed / 0 failed;
- squash main `982dc4f58fec6172a4fa99475ae72800c107981f`: Verify #727, 1921 passed / 0 failed.

Preserved:

- no finance formula or fee subtraction changed;
- unknown finance remains unknown;
- no Product Decision threshold/rule change;
- no new persistence owner;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Operational Metrics Result Integrity v1021-v1030 — 2026-09-01

Completed:

[x] Sales source exceptions are sanitized before Product Decision generation

[x] Stock source exceptions are sanitized before Product Decision generation

[x] Non-mapping operational metrics fail closed

[x] Explicit metrics `error` marker must be boolean when present

[x] Explicit `error=True` remains unavailable/unknown data, never zero

[x] Sales velocity is finite, non-boolean, and non-negative

[x] Sales trend is canonical: GROWING / DECLINING / STABLE

[x] Stock quantity and days-of-stock are finite, non-boolean, and non-negative

[x] Stock priority semantics are canonical, including NO_SALES

[x] Existing `stock_priority` alias contract is preserved and contradictory aliases are rejected

[x] Malformed missing-data/evidence fields fail closed

[x] Invalid operational metrics result is not cached

Verified exact main:

`70466d338951b2b7cc2bb7c48a9d2c7ee2dc91df`

GitHub Actions push Verify #736: 1931 passed / 0 failed.

Failed evidence preserved:

- `678739dea2fa85af3f71933f048f9bfb193fdc62`: Verify #733, 1929 passed / 2 failed.

Final feature and integration evidence:

- final feature `6af041c39b86791821249058d0632070f2f68685`: Verify #734, 1931 passed / 0 failed;
- PR #340 synthetic `7e64fcd23df9fb405c8c422359e3703b6a720f56`: Verify #735, 1931 passed / 0 failed;
- squash main `70466d338951b2b7cc2bb7c48a9d2c7ee2dc91df`: Verify #736, 1931 passed / 0 failed.

Preserved:

- no Product Decision threshold/rule change;
- no finance formula change;
- unknown sales/stock values remain unknown;
- no new persistence owner;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Persistence Commit Receipt Integrity v1031-v1040 — 2026-09-01

Completed:

[x] Base Product Decision history writes no longer ignore storage save results

[x] Rejected/unknown saves cannot return a successful available history context

[x] Failed base writes are removed from in-memory state and retried from known state

[x] Durable persistence application requires explicit record_persistent() support

[x] In-memory-only history cannot issue a durable commit receipt

[x] Successful receipt requires saved=True and persistence_state=COMMITTED

[x] Receipt binds exact SKU, recorded_at, history count, and history context

[x] Product Decision persistence application requires the committed receipt before product_decision_persisted=True

[x] Product Decision persistence verification requires the same receipt before readback verification

[x] No persistence/application lineage is synthesized into history snapshots

Verified exact main:

`7d53fecac126973122270eacfdfc122e50ae3de3`

GitHub Actions push Verify #745: 1941 passed / 0 failed.

Failed evidence preserved:

- `14a0709209228310625dd91871e963a866ab6cc9`: Verify #742, 1940 passed / 1 failed.

Final feature and integration evidence:

- final feature `88372919c9275a51482703e59fe21d8c4d9c5682`: Verify #743, 1941 passed / 0 failed;
- PR #342 synthetic `7e54ca702706ad192eb70da63e351e96efdb31b5`: Verify #744, 1941 passed / 0 failed;
- squash main `7d53fecac126973122270eacfdfc122e50ae3de3`: Verify #745, 1941 passed / 0 failed.

Preserved:

- existing Product Decision History storage remains the persistence owner;
- no Telegram read path invokes persistence application;
- Telegram verified-guidance blocker remains open because application receipt lineage is not durably embedded in history snapshots;
- no Product Decision rule/threshold or finance formula change;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Durable Application Lineage v1041-v1050 — 2026-09-01

Completed:

[x] Persistence application constructs exact lineage before durable Product Decision write

[x] Existing Product Decision History owner validates the complete lineage chain

[x] Lineage binds application/readiness/authorization/eligibility/review/delta/preview IDs, draft_id and SKU

[x] Malformed and cross-SKU lineage is rejected before storage mutation

[x] Durable Product Decision snapshot stores the exact application lineage atomically

[x] COMMITTED persistence receipt returns the same lineage

[x] Persistence application rejects forged receipt lineage

[x] Persistence verification requires exact receipt lineage

[x] Persistence verification requires durable history snapshot lineage to match the exact application

[x] JSON storage restart preserves application lineage

[x] Feedback mutation preserves the snapshot lineage

[x] Restart readback verifies without execution or Ozon mutation

Verified exact main:

`19851b9d40827b3ca5e3889c3858ca32c5602f67`

GitHub Actions push Verify #754: 1951 passed / 0 failed.

Failed evidence preserved:

- `cfeb3528d5f902625819b6897db192bf794fddda`: Verify #751, 1915 passed / 36 failed.

Final feature and integration evidence:

- final feature `5e856591925d2288db871ac9632eab5ee7f7a649`: Verify #752, 1951 passed / 0 failed;
- PR #344 synthetic `13f8cb191c24eb0589cf4f5ba892d7b13b402bc5`: Verify #753, 1951 passed / 0 failed;
- squash main `19851b9d40827b3ca5e3889c3858ca32c5602f67`: Verify #754, 1951 passed / 0 failed.

Preserved:

- Product Decision History remains the only persistence owner;
- application lineage is written, never inferred after the fact;
- Telegram read path still does not invoke persistence application;
- Telegram guidance/checklist wiring is not yet enabled;
- no Product Decision rule/threshold or finance formula change;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Read-Only Persistence Verification v1051-v1060 — 2026-09-01

Completed:

[x] Product Decision History storage exposes explicit durable read receipt

[x] Corrupted JSON/non-list/mixed durable data is distinguishable from no history

[x] latest_persistent() reads storage directly rather than self.records

[x] In-memory-only history cannot become persistence proof

[x] Read-only verifier validates durable read receipt before business semantics

[x] Read-only verifier validates snapshot SKU, recorded_at, decision semantics and stored application lineage

[x] Missing/cross-SKU/broken-chain lineage fails closed

[x] Valid durable history produces canonical PRODUCT_DECISION_PERSISTENCE_VERIFIED payload

[x] Runtime verification ID is produced only after exact persisted application ID validates

[x] verify_latest() performs no save/application/execution/Ozon mutation

Verified exact main:

`b0bfdd5dd79349244ceaf64d1d4df9899211344a`

GitHub Actions push Verify #762: 1961 passed / 0 failed.

Feature and integration evidence:

- final feature `c0da07cbafeb1fe38001729eebca94648149d96b`: Verify #760, 1961 passed / 0 failed;
- PR #346 synthetic `0ccae174a2adfe5c650ca96bf7dcf90ceafaec80`: Verify #761, 1961 passed / 0 failed;
- squash main `b0bfdd5dd79349244ceaf64d1d4df9899211344a`: Verify #762, 1961 passed / 0 failed.

Preserved:

- Product Decision History remains the only persistence owner;
- no persisted application lineage is inferred;
- read-only verification never calls persistence application;
- Telegram guidance/checklist wiring is not yet enabled;
- no Product Decision rule/threshold or finance formula change;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Telegram Verified Product Decision Guidance / Checklist Wiring v1061-v1070 — 2026-09-02

Completed:

[x] Telegram production factory shares one Product Decision History instance between decision query and read-only persistence verifier

[x] Product Decision detail presentation invokes only `verify_latest(sku)`

[x] Telegram never invokes Product Decision persistence application as a read/presentation side effect

[x] Verified durable snapshot must match the currently displayed Product Decision by SKU, recorded_at, decision_type, priority, confidence and reasons

[x] Existing guidance builder is consumed only after canonical durable verification succeeds

[x] Existing checklist builder is consumed only after verified guidance passes safety validation

[x] Malformed/blocked/old/unverified durable state preserves the existing Product Decision card without a false verified claim

[x] Builder/verifier exceptions are contained and do not leak secret error details into Telegram

[x] Valid verified guidance is rendered as a manual checklist with automatic execution explicitly disabled

[x] No Telegram callback/button starts Product Decision execution, Product Task Draft execution or Ozon mutation

Verified exact main:

`dbec4ecfc5f38b31aeba5e86a6d0ad09c40d58bb`

GitHub Actions push Verify #771: 1971 passed / 0 failed.

Failed evidence preserved:

- `f449e7d738b56fb72f39e0836eb2ea3464b899a9`: Verify #768, 1970 passed / 1 failed.

Final feature and integration evidence:

- final feature `09abed3a9db1c1cf90a13d4393bb3771f09c964d`: Verify #769, 1971 passed / 0 failed;
- PR #348 synthetic `400bbfa95038edd3876a2ea0eb4b2e28db65fefb`: Verify #770, 1971 passed / 0 failed;
- squash main `dbec4ecfc5f38b31aeba5e86a6d0ad09c40d58bb`: Verify #771, 1971 passed / 0 failed.

Preserved:

- Product Decision History remains the sole persistence owner;
- read-only Telegram verification uses durable history and stored application lineage;
- no missing persistence/application IDs are inferred;
- no Product Decision rule/threshold or finance formula change;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Product Decision Telegram Query Exception Containment v1071-v1080 — 2026-09-02

Completed:

[x] Seller-facing Product Decision overview contains `query_all()` exceptions locally

[x] Seller-facing Product Decision detail contains `query(sku)` exceptions locally

[x] Query exceptions return deterministic `PRODUCT_DECISION_QUERY_FAILED`

[x] Overview and detail return seller-specific messages instead of generic Telegram dispatch failure

[x] Exception details are not exposed to the seller response

[x] Query failures are one-shot and are not retried

[x] Keyboard/feedback presentation is not invoked after query exceptions

[x] Explicit downstream `error=True` semantics remain unchanged

[x] Valid overview remains unchanged

[x] Valid detail remains unchanged and preserves defensive-copy behavior

Verified exact main:

`41473566a558bb09899f64d581010b72e4053fbd`

GitHub Actions push Verify #780: 1981 passed / 0 failed.

Failed evidence preserved:

- `31902d6e4f1302a5fe221e091b54bd5e2c4a8f3d`: Verify #777, 1980 passed / 1 failed.

Final feature and integration evidence:

- final feature `30da677a1db0fdca3cd4ac2b0928859e0b9b81a8`: Verify #778, 1981 passed / 0 failed;
- PR #350 synthetic `a0bbb0059c67c3d4e0583f2b13883f5dd3f8857e`: Verify #779, 1981 passed / 0 failed;
- squash main `41473566a558bb09899f64d581010b72e4053fbd`: Verify #780, 1981 passed / 0 failed.

Preserved:

- generic Telegram adapter exception containment remains the outer safety net;
- no retry or duplicate query call introduced;
- no persistence owner or persistence contract changed;
- Product Decision thresholds/rules unchanged;
- finance formulas unchanged;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Financial Telegram Query Exception Containment v1081-v1090 — 2026-09-02

Completed:

[x] Unit Economics product-list source exceptions are contained locally

[x] Returns Finance Impact product-list source exceptions are contained locally

[x] Unit Economics query exceptions are contained locally

[x] Returns Finance Impact query exceptions are contained locally

[x] Unit Economics formatter exceptions are contained locally

[x] Seller responses use deterministic finance-domain failure codes

[x] Internal exception details are not exposed

[x] Financial source/query calls are one-shot and are not retried

[x] Generic Telegram adapter containment remains the outer safety net

[x] Valid Unit Economics and Returns Finance Impact UI remains compatible

Verified exact main:

`0f484141713f2452f451e818caf600d113df6ad4`

GitHub Actions push Verify #788: 1991 passed / 0 failed.

Final feature and integration evidence:

- final feature `6cf579771939ceb765a996fa761a406175e003d3`: Verify #786, 1991 passed / 0 failed;
- PR #352 synthetic `69383b1fcfe87aab31dfb6bb29cd4f73bf051e13`: Verify #787, 1991 passed / 0 failed;
- squash main `0f484141713f2452f451e818caf600d113df6ad4`: Verify #788, 1991 passed / 0 failed.

Preserved:

- finance formulas and calculations unchanged;
- no retry or duplicate finance source/query call;
- no persistence change;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Tax Configuration Persistence & Result Integrity v1091-v1100 — 2026-09-02

Completed:

[x] Persisted tax configuration root must be a mapping

[x] Tax and minimum-tax rates reject booleans, non-numeric values, NaN/inf, negatives and values above 100%

[x] Explicit NONE mode preserves the zero-tax normalization contract

[x] Truncated or malformed persisted tax configuration fails closed as unconfigured instead of raising into startup

[x] Valid tax configuration is serialized before write

[x] Valid tax configuration is written to an fsynced temporary file and atomically replaces the target

[x] Failed atomic replace returns deterministic `TAX_CONFIGURATION_SAVE_FAILED`

[x] Failed write cleans temporary data and preserves the previous durable tax policy

[x] Production `create_telegram_core` survives malformed tax configuration and keeps tax unknown/unconfigured

[x] TaxService formulas and calculation branches are unchanged

Verified exact main:

`38e54ddc6d289f0f75121cc63efa0268ef2784f8`

GitHub Actions push Verify #796: 2001 passed / 0 failed.

Final feature and integration evidence:

- final feature `8cc003f6fa66eb499c67d7d3d74f90c0c75abecf`: Verify #794, 2001 passed / 0 failed;
- PR #354 synthetic `5167b644bc53edc27a40c7b15c7068e0c669d2fc`: Verify #795, 2001 passed / 0 failed;
- squash main `38e54ddc6d289f0f75121cc63efa0268ef2784f8`: Verify #796, 2001 passed / 0 failed.

Preserved:

- existing TaxConfigurationService remains the sole tax-config persistence owner;
- TaxService formulas/calculation semantics unchanged;
- no new retry or execution path;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Tax Calculation Input & Result Integrity v1101-v1110 — 2026-09-02

Completed:

[x] Unsupported tax mode is rejected before numeric conversion

[x] Missing tax mode preserves the explicit unconfigured contract

[x] Revenue and gross-profit inputs reject booleans, non-numeric values and NaN/inf

[x] Tax and minimum-tax rates reject booleans, non-numeric values, NaN/inf, negatives and values above 100%

[x] Explicit NONE mode preserves the existing zero-tax result

[x] Numeric-string compatibility remains supported

[x] Existing negative tax-base clipping remains unchanged

[x] Non-finite/overflow tax calculations fail closed instead of returning NaN/inf

[x] ProductUnitEconomicsProvider continues to map TaxService failures to unknown tax rather than inventing a value

[x] Existing tax formula branches and configured percentages remain unchanged

Verified exact main:

`1bc8cfc745a94c7bfe3442bf2c774947f79bce8b`

GitHub Actions push Verify #804: 2011 passed / 0 failed.

Final feature and integration evidence:

- final feature `85fc4b76baa725cbc586ca39e8454e30a70fb168`: Verify #802, 2011 passed / 0 failed;
- PR #356 synthetic `7d070c91d97e811491849475ddcd65552eadd1c7`: Verify #803, 2011 passed / 0 failed;
- squash main `1bc8cfc745a94c7bfe3442bf2c774947f79bce8b`: Verify #804, 2011 passed / 0 failed.

Preserved:

- TaxConfigurationService persistence contract unchanged;
- TaxService formula branches/percentages unchanged;
- no new retry or execution path;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Advertising & Expense Finite Result Integrity v1111-v1120 — 2026-09-02

Completed:

[x] Advertising cost rejects boolean and NaN/inf values

[x] Missing advertising remains explicit unknown; zero remains explicit configured zero

[x] Negative advertising retains the existing explicit rejection contract

[x] Campaign aggregation ignores malformed/non-finite/negative/bool rows under the existing tolerant list model

[x] Advertising aggregate overflow fails closed instead of returning infinity

[x] Other-expense aggregation ignores malformed/non-finite/negative/bool rows under the existing tolerant list model

[x] Other-expense aggregate overflow fails closed instead of returning infinity

[x] Single expense rejects boolean and NaN/inf values

[x] Existing numeric-string compatibility remains

[x] BusinessAnalyticsService does not emit business profit when advertising is invalid or other-expense aggregation overflows

Verified exact main:

`cb0148a1d6ad14b2e53f18ca948b66e8422da3c4`

GitHub Actions push Verify #812: 2021 passed / 0 failed.

Final feature and integration evidence:

- final feature `c45284c99d70a45b1bed2b5f62049a7bb5c40df6`: Verify #810, 2021 passed / 0 failed;
- PR #358 synthetic `8b8bcfda3b61518637637a05b1b60109a7907192`: Verify #811, 2021 passed / 0 failed;
- squash main `cb0148a1d6ad14b2e53f18ca948b66e8422da3c4`: Verify #812, 2021 passed / 0 failed.

Preserved:

- finance formulas unchanged;
- existing AdvertisingService/ExpenseService owners unchanged;
- no persistence contract change;
- no new retry or execution path;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Store Profit Aggregation Result Integrity v1121-v1130 — 2026-09-02

Completed:

[x] Store-profit input container is validated

[x] Non-mapping product-profit records fail closed

[x] sales_count rejects boolean, negative, fractional, non-numeric and non-finite values

[x] Financial aggregate fields reject boolean, non-numeric and NaN/inf values

[x] Aggregate overflow and non-finite margin fail closed

[x] Failed product-profit rows remain skipped

[x] Missing numeric fields retain existing zero defaults

[x] Numeric-string and loss-product compatibility remain

[x] BusinessAnalytics propagates store-profit failure before downstream finance calculations

[x] SalesIntelligence and AssistantSalesExecutor preserve the failure end-to-end

Verified exact main:

`87c95cf2eb139cd8782d8df79d43b2313939bba0`

GitHub Actions push Verify #820: 2031 passed / 0 failed.

Final feature and integration evidence:

- final feature `a888d3c4aa35aaba7526df186bfdbdd2902f9369`: Verify #818, 2031 passed / 0 failed;
- PR #360 synthetic `decce34f5a0cf348a4f9ab1ab80c50179d5e9d2b`: Verify #819, 2031 passed / 0 failed;
- squash main `87c95cf2eb139cd8782d8df79d43b2313939bba0`: Verify #820, 2031 passed / 0 failed.

Preserved:

- StoreProfitService success schema and missing-field zero defaults;
- aggregation formulas and margin formula unchanged;
- no persistence change;
- no new retry or execution path;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.


---

# Business Profit Calculation Result Integrity v1131-v1140 — 2026-09-02

Completed:

[x] Non-mapping store-profit/tax inputs fail closed

[x] Malformed store/tax error/configured markers fail closed

[x] Gross-sales/gross-profit inputs reject boolean, non-numeric and NaN/inf

[x] Advertising/other-expense inputs reject boolean, negative, non-numeric and NaN/inf

[x] Tax amount rejects boolean, negative, non-numeric and NaN/inf

[x] Unknown tax remains unknown rather than zero

[x] Existing tax-error message/presentation contract remains compatible

[x] Business-profit and margin overflow/non-finite results fail closed

[x] Valid numeric strings and existing formulas remain compatible

[x] New BUSINESS_PROFIT_* integrity failures propagate through BusinessAnalytics, SalesIntelligence and AssistantSalesExecutor

Verified exact main:

`189455bb5b44c47bbf5abf188d1b456dad14b1ba`

GitHub Actions push Verify #828: 2041 passed / 0 failed.

Final feature and integration evidence:

- final feature `98edb5b5500c25e53b77237016afe3a223360ab8`: Verify #826, 2041 passed / 0 failed;
- PR #362 synthetic `6e335e508c07903d6e4488f1aac40d28a9e4152f`: Verify #827, 2041 passed / 0 failed;
- squash main `189455bb5b44c47bbf5abf188d1b456dad14b1ba`: Verify #828, 2041 passed / 0 failed.

Preserved:

- business-profit/margin formulas unchanged;
- TaxService/tax formulas unchanged;
- no persistence change;
- no new retry or execution path;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Finance Period Aggregation Result Integrity v1141-v1150 — 2026-09-02

Completed:

[x] Daily finance source exceptions are contained as failed days with sanitized seller-safe evidence

[x] Non-mapping daily finance results fail closed instead of raising during aggregation

[x] Malformed explicit error markers fail the affected day

[x] Operations and sales counters reject boolean, negative, fractional, non-numeric and NaN/inf values

[x] Finance amount fields reject boolean, non-numeric and NaN/inf values

[x] Malformed or non-finite fee breakdown values fail the whole affected day

[x] Invalid days do not partially commit counters, amount totals or fee breakdown totals

[x] Partial periods retain only fully valid days and preserve the existing partial-success contract

[x] Aggregate amount/fee overflow fails closed with FINANCE_PERIOD_AGGREGATE_INVALID

[x] Valid numeric strings and signed fee values remain compatible

[x] StoreAnalytics finance path preserves contained source failures

Verified exact main:

`d1655adf6719e6000f996b4635253c6b99193ba3`

GitHub Actions push Verify #837: 2051 passed / 0 failed.

Final feature and integration evidence:

- failed intermediate `f54132ebf109240242a87037a81b1db5ed052d5b`: Verify #834, 2050 passed / 1 failed; test-only false positive remains failed evidence;
- final feature `52661a7c37068759d20797644943a3b9e5e5ebcc`: Verify #835, 2051 passed / 0 failed;
- PR #364 synthetic `ef001cc855661041bd3987604496d03e55acaf30`: Verify #836, 2051 passed / 0 failed;
- squash main `d1655adf6719e6000f996b4635253c6b99193ba3`: Verify #837, 2051 passed / 0 failed.

Preserved:

- FinanceAnalyticsService amount/fee formulas unchanged;
- existing partial-period success semantics unchanged;
- no persistence change;
- no new retry or execution path;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Period Profit Summary Input & Result Integrity v1151-v1160 — 2026-09-02

Completed:

[x] Daily FinanceService exceptions are contained as seller-safe period-profit failures

[x] Non-mapping daily finance results fail closed

[x] Malformed explicit daily error markers fail closed

[x] sales_count rejects boolean, negative, fractional, non-numeric and NaN/inf values

[x] Period-profit finance amount fields reject boolean, non-numeric and NaN/inf values

[x] fee_breakdown requires a mapping with finite numeric amounts

[x] Cost inputs reject boolean, negative, non-numeric and NaN/inf values

[x] Cost source exceptions are contained without leaking exception text

[x] Invalid tax-rate configuration fails closed instead of raising during service construction

[x] Product/day/period amount and fee aggregate overflow fails closed

[x] Valid numeric strings and signed fee values remain compatible

[x] PeriodProfitQueryService and AssistantPeriodProfitRuntimeService preserve integrity failures end-to-end

Verified exact main:

`0ca4d226f3f75e2b20035a87a13b1a10d6c71581`

GitHub Actions push Verify #849: 2061 passed / 0 failed.

Final feature and integration evidence:

- final feature `4ab53fe054504c633fbcd6fb708ccb7dc557eaa4`: Verify #847, 2061 passed / 0 failed;
- PR #367 synthetic `a9030acff2031b118c0c0600c008804c3d6ff08a`: Verify #848, 2061 passed / 0 failed;
- squash main `0ca4d226f3f75e2b20035a87a13b1a10d6c71581`: Verify #849, 2061 passed / 0 failed;
- no failed production SHA occurred in this package.

Preserved:

- period-profit formula `profit = net_accrual - product_cost - tax` unchanged;
- configured tax multiplication semantics unchanged;
- no persistence change;
- no new retry or execution path;
- Period Profit route remains read-only;
- no Product Decision/Product Task Draft execution;
- no Action Executor/Ozon mutation wiring;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Telegram Period Profit Analyst Wiring v1161-v1170 — 2026-09-03

Completed:

[x] Period-profit runtime wired into production Telegram core

[x] Telegram main menu exposes "💵 Прибыль за период"

[x] Today / 7 / 28 / 56 / 90-day read-only period menu

[x] Natural-language requests such as "прибыль за 28 дней"

[x] Direct analytical text is rendered as Telegram text instead of Python dict output

[x] Period-profit callback success requires read_only=True

[x] Period-profit callback success requires executed=False

[x] Runtime exceptions are contained with seller-safe failure

[x] Malformed or execution-adjacent callback results fail closed

[x] Existing partial-core test fixtures remain backward compatible

Verification:

- entering exact main `bb2e444b5a7ee6caa9cc4e39adccc5df64949835`: Verify #859, 2061 passed / 0 failed;
- failed intermediate `e7fce70c39f976e97bf78687621ace5125f9d30a`: Verify #866, 2069 passed / 2 failed;
- final feature `9c5d14f0220e5f13ee0a7d834855f7e07db58cab`: Verify #868, 2071 passed / 0 failed;
- PR #369 synthetic `04b20cc49a253bfb357626cf62a71b779a75112e`: Verify #869, 2071 passed / 0 failed;
- squash main `d06a5f8cc23814e3177f58f6182bef6fbceb0697`: Verify #870, 2071 passed / 0 failed.

Current product boundary:

- assistant is a read-only analyst/advisor;
- Ozon price, advertising budget/bid, stock/replenishment, product-card and other seller mutations are out of scope;
- recommendations, checklists and drafts do not grant execution permission;
- `data/users.json` unchanged by this package;
- `externally_verified=False`.

---

# Telegram Custom Period Date Input v1171-v1180 — 2026-09-03

Completed:

[x] Localized custom Period Profit input in `ДД.ММ.ГГГГ`

[x] Example `01.05.2026 - 03.09.2026` routes through production Period Profit

[x] Single-digit day/month input remains accepted

[x] En dash and em dash separators remain accepted

[x] Existing ISO `YYYY-MM-DD` input remains supported

[x] Localized dates normalize to ISO before the Period Profit query layer

[x] Invalid calendar dates fail closed without finance query

[x] Incomplete custom date input fails closed

[x] Missing-period help now shows seller-friendly localized date format

[x] Localized custom Period Profit bypasses the general execution flow

Verification:

- entering exact main `fa30bafeecfa9291175e7f1c4ac0ad2c078b4607`: Verify #881, 2071 passed / 0 failed;
- final feature `62b040e392514bc410b34d82eccb8e0385b9c548`: Verify #884, 2081 passed / 0 failed;
- PR #371 synthetic `b865b551289ba4592d8d32594323ea8a6dc64c61`: Verify #885, 2081 passed / 0 failed;
- squash main `05f94da42e21c5ad5f7d78cb7f55bb2d40730f77`: Verify #886, 2081 passed / 0 failed;
- no failed production SHA occurred in this package.

Preserved:

- Decision 036 read-only Ozon analyst boundary;
- no finance formula changes;
- no Product Decision/Product Task Draft execution;
- no Action Executor connection;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Tax Policy Production Availability v1181-v1190 — 2026-09-03

Completed:

[x] Restored repository production tax policy `USN_INCOME / 6%`

[x] Clean Telegram deployment receives configured tax policy

[x] Explicit environment tax fallback when persisted file is absent

[x] Environment fallback requires explicit `TAX_MODE`

[x] Missing policy remains unknown rather than zero

[x] Invalid environment policy fails closed

[x] Persisted policy has precedence over environment

[x] Malformed persisted policy does not silently fall back

[x] hook-2-like current economics calculates 6.00 ₽ tax at 100 ₽ tax base

[x] hook-2-like base net profit calculates to 35.83 ₽ before returns adjustment

Verification:

- entering exact main `8ca28c36249a052fdf83cfd5ab86a13d986cbb1c`: Verify #896, 2081 passed / 0 failed;
- final feature `1d0df2799fb87b57d916843a96a080389e2ac07b`: Verify #900, 2091 passed / 0 failed;
- PR #373 synthetic `a6493407f0bb915f366573404fcffd220e6757a1`: Verify #901, 2091 passed / 0 failed;
- squash main `9c9d379e36edf2123a466ad2b3cd1d000d81bae3`: Verify #902, 2091 passed / 0 failed;
- no failed production SHA occurred in this package.

Preserved:

- Decision 036 read-only analyst boundary;
- missing tax is never interpreted as zero;
- returns/non-buyout evidence remains separate;
- no Product Decision/Product Task Draft execution;
- no Ozon mutation;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Period Profit Returns Protobuf Timestamp Compatibility v1191-v1200 — 2026-09-03

Completed:

[x] Reproduced live Ozon protobuf Timestamp failure

[x] Identified Period Profit return-evidence path as source

[x] Date-only Returns API start normalized to RFC3339 UTC start-of-day

[x] Date-only Returns API end normalized to RFC3339 UTC end-of-day

[x] Existing full RFC3339 timestamps preserved

[x] Custom Period Profit ranges reach Returns API with valid timestamps

[x] Preset Period Profit ranges reach Returns API with valid timestamps

[x] Existing Returns filter/pagination/timeout contract preserved

[x] Return evidence remains read-only and non-financial

Verification:

- entering exact main `d3f32e2ca2e30192a59c4551cf5633dfa0941ec6`: Verify #912, 2091 passed / 0 failed;
- final feature `9e2c5b27a1df9f32c8e950766abc809ba93f7976`: Verify #918, 2101 passed / 0 failed;
- PR #375 synthetic `86bc4a07477e910fcaf56a1a1b908fa28a4a68f5`: Verify #919, 2101 passed / 0 failed;
- squash main `c1c3da7cb69d6ce2af550e57bc6c5e38a0bb8a89`: Verify #920, 2101 passed / 0 failed;
- no failed production SHA occurred.

Preserved:

- Decision 036;
- no Ozon mutation;
- no execution changes;
- no finance formula changes;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Period Profit Data Completeness Integrity v1201-v1210 — 2026-09-03

Completed:

[x] Persisted SQLite product tuples normalized for Period Profit

[x] False-success zero summary over zero usable products blocked

[x] Empty/malformed product sets fail with PERIOD_PROFIT_PRODUCTS_UNAVAILABLE

[x] Existing dict product contract preserved

[x] Returns evidence paginates beyond the 500-record first page

[x] Pagination advances via has_next + last_id

[x] Pagination bounded to 10 pages

[x] Complete return counts marked exact

[x] Incomplete return counts marked as lower bounds

[x] Telegram partial-return wording uses "как минимум N"

[x] Legacy READY return-evidence response compatibility preserved

Verification:

- entering exact main `5e8e74a78e2c5aa41ed59378c27a0f1ed7b55397`: Verify #930, 2101 passed / 0 failed;
- failed intermediate `e3d8b2ed1600e3759135bda4f62865ba38a43ae9`: Verify #935, 2103 passed / 2 failed;
- failed intermediate `49c02ae1790b7d395794932e7ac4fa95cbac1644`: Verify #936, 2109 passed / 2 failed;
- final feature `16c53622612b72bce2aa43fd97d5ff66d47466c3`: Verify #937, 2111 passed / 0 failed;
- PR #377 synthetic `f1593267f67339f2dd68d235056cdbc69960160a`: Verify #938, 2111 passed / 0 failed;
- squash main `7b2b570278c9cc71f3eb6dbb23b5554d41de07f7`: Verify #939, 2111 passed / 0 failed.

Preserved:

- Decision 036 read-only analyst boundary;
- no finance formula change;
- no return-cost inference;
- no Ozon mutation or execution changes;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Period Profit Tax Rate Unit Integrity v1211-v1220 — 2026-09-03

Completed:

[x] Live 600% Period Profit tax bug reproduced

[x] Production Period Profit now reads validated TaxConfigurationService policy

[x] USN Income 6.0% converts to 0.06 fraction

[x] NONE converts to zero fraction

[x] Unsupported USN Income Minus Expenses fails closed

[x] Non-finite/invalid tax percentages fail closed

[x] PeriodProfitSummaryService rejects tax multipliers above 1.0

[x] Seller live sample regression: tax 80 902.27 ₽, profit 310 701.55 ₽, margin 23.04%

Verification:

- entering exact main `590b068ef46f58e56509ac038759f465975c9a8a`: Verify #949, 2111 passed / 0 failed;
- failed `a7d5cead4c7c49907d6d045b54a3cec30d48efad`: Verify #953, 2110 passed / 1 failed;
- failed `ee463cd1000113998ae5b895da02334bb5a5f495`: Verify #954, 2120 passed / 1 failed;
- final feature `4c50429bc4c2f6515d80b497b85fe8c9663e24eb`: Verify #955, 2121 passed / 0 failed;
- PR #379 synthetic `68c0f7360dd93738377f7111f5f4732d0b4d48af`: Verify #956, 2121 passed / 0 failed;
- squash main `2f438bd6bb739938cee4fe56b83af8f4a563f942`: Verify #957, 2121 passed / 0 failed.

Preserved:

- Decision 036;
- read-only Period Profit;
- no Ozon mutation or execution changes;
- `data/users.json` unchanged;
- `externally_verified=False`.

Next seller-requested presentation work:
- add percent-of-revenue in parentheses for each Period Profit monetary line.

---

# Period Profit Revenue Share Presentation v1221-v1230 — 2026-09-03

Completed:

[x] Revenue line shows 100.00%

[x] Ozon net accrual shows share of revenue

[x] Commission / logistics / acquiring / other fees show share of revenue

[x] Product cost shows share of revenue

[x] Tax shows share of revenue

[x] Profit shows share of revenue

[x] Negative profit keeps negative share

[x] Zero revenue suppresses derived shares

[x] Existing comparison percentage meaning preserved

[x] Existing margin and scope warnings preserved

Verification:

- entering exact main `5cb69fed7bc44fcd5f66a8a004e625bee9993953`: Verify #967, 2121 passed / 0 failed;
- final feature `77994ccb67c060f7c01694ac65eea5c8aec24e1d`: Verify #970, 2131 passed / 0 failed;
- PR #381 synthetic `b9a72b875081d6f12fe7f5b50d4b0c6f6af13e89`: Verify #971, 2131 passed / 0 failed;
- squash main `08d0d0fa6860101921ead603ec4a00b95c9ee8bf`: Verify #972, 2131 passed / 0 failed.

Preserved:

- Decision 036;
- presentation-only change;
- no financial formula changes;
- no Ozon mutation or execution changes;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Finance Accrual Pagination & Read Session Integrity v1231-v1240 — 2026-09-03

Completed:

[x] Ozon accrual-by-day first request sends required empty last_id

[x] Finance accrual pages are read until cursor exhaustion

[x] Malformed page responses fail closed

[x] Repeated pagination cursors fail closed

[x] Page-cap exhaustion fails closed instead of returning partial finance as complete

[x] Target SKU evidence on later accrual pages is included

[x] Same calendar day is reused for multiple SKUs inside one read session

[x] Each Period Profit calculation starts a fresh finance read session

[x] Read-session failures are contained without leaking private exception text

Verification:

- entering exact main `400ca040d743dc7db93480605ebd62a7fe9b02f3`: Verify #984, 2131 passed / 0 failed;
- failed `8d159ed09410ed978bef6cfdb5719a67bc5491b1`: Verify #990, 2140 passed / 1 failed;
- final feature `ad215b8d86c547e740dcb3583e7b7f580e9fb823`: Verify #991, 2141 passed / 0 failed;
- PR #383 synthetic `4b1f8e48de3f92c6aecc590232697890c8814d08`: Verify #992, 2141 passed / 0 failed;
- squash main `e66125d5e2c737497762178bef86dd36a62721f3`: Verify #993, 2141 passed / 0 failed.

Preserved:

- Decision 036;
- read-only finance retrieval;
- no financial formula changes;
- no Ozon mutation or execution changes;
- `data/users.json` unchanged;
- `externally_verified=False`.

---

# Account-Level Ozon Profit Reconciliation v1241-v1250 — 2026-09-03

Completed:

[x] Decision 037 account-level Ozon monetary authority

[x] Account-level daily revenue/net accrual/fee totals drive Period Profit V2

[x] SKU-level finance remains COGS and product-revenue evidence

[x] Product revenue must reconcile to account revenue within 0.01 RUB

[x] Revenue coverage mismatch fails closed

[x] Account-minus-SKU net reconciliation is exposed

[x] Account-level charges without SKU are included once

[x] Multi-SKU posting-level net duplication is corrected by account total

[x] Account-level fee breakdown replaces summed SKU fee breakdown

[x] Mapped Ozon expenses remain evidence and are never deducted twice

Verification:

- entering exact main `0aa27a1267b9d54f1207455b05e32db843091d86`: Verify #1003, 2141 passed / 0 failed;
- final feature `a0e528f36b1b4721af0e8d0b419c414d20fabea6`: Verify #1010, 2151 passed / 0 failed;
- PR #385 synthetic `4a361a58d62e56c2e2aa4c608620ae86992ac05f`: Verify #1011, 2151 passed / 0 failed;
- squash main `a359e3d8e68784849caa659dec0123fb15dc6932`: Verify #1012, 2151 passed / 0 failed.

Preserved:

- Decision 036;
- read-only analytics;
- no Ozon mutation;
- no unsupported accounting-net-profit claim;
- `data/users.json` unchanged;
- `externally_verified=False`.

Next accounting gap:
- return-related COGS reversal / recovered-goods evidence;
- then non-Ozon overhead/taxes if the seller provides them.

---

# Return COGS Recovery Evidence v1251-v1260 — 2026-09-03

Completed:

[x] Nested Returns API product / status / compensation evidence preserved

[x] Customer-return units at return-place exposed as candidate recovery

[x] Candidate recovery value calculated from current configured product cost

[x] Compensated returns separated from COGS recovery candidates

[x] Unproven return statuses remain unresolved

[x] Missing product cost remains unknown, not zero

[x] Partial return sample cannot become complete recovery evidence

[x] Historical cost basis remains unconfirmed

[x] Originating sale-period lineage remains unconfirmed

[x] Saleable inventory recovery remains unconfirmed

[x] Period/accounting COGS recovery remains unconfirmed

[x] Candidate recovery never changes Period Profit

[x] Telegram and coverage expose candidate evidence and limitations

Verification:

- entering exact main `55942648266e9ca4fbb3d3380180c3a67bfc4c56`: Verify #1022, 2151 passed / 0 failed;
- failed `2339d8aa8da1ec43c3298be2da8506a1e6dd8b9b`: Verify #1033, 2159 passed / 2 failed;
- final feature `30f3edafd9d2af603f2277701cb13492a334dd30`: Verify #1038, 2161 passed / 0 failed;
- PR #387 synthetic `c5947439450297dabb353b3dfd125e3fc6417576`: Verify #1039, 2161 passed / 0 failed;
- squash main `d845c7183ef5a914853a15b788e18b0cebfd1c93`: Verify #1040, 2161 passed / 0 failed.

Preserved:

- Decision 036;
- Decision 037;
- account-level Ozon monetary authority;
- no automatic return COGS reversal;
- no accounting net-profit claim;
- `data/users.json` unchanged;
- `externally_verified=False`.

Next accounting priority:
- explicit seller-configured non-Ozon operating expenses;
- unknown external expense remains unknown, never zero.

---

# External Operating Expense Coverage v1261-v1270 — 2026-09-03

Completed:

[x] Decision 038 external operating expense evidence and coverage contract

[x] Existing local `expenses` rows retained as explicit seller-entered external expense evidence

[x] `expense_coverage` intervals added as explicit completeness confirmation

[x] Requested-period coverage is complete only when every calendar day is covered

[x] Empty uncovered period remains unknown, not zero

[x] Empty fully covered period becomes explicit confirmed 0 ₽ external expense

[x] Partial expense rows produce observed adjusted profit only

[x] Complete coverage permits complete profit-after-external-expenses adjustment

[x] Invalid expense dates fail closed

[x] Boolean, NaN and infinite expense amounts fail closed

[x] Period Profit Telegram text distinguishes base profit, entered expenses and coverage completeness

[x] Ozon advertising/storage/return charges already inside account net accrual are never subtracted again

[x] `confirm_expense_coverage.py` provides explicit local coverage confirmation

Derived formula:

`profit_after_external_expenses = period_profit - external_expenses`

The base Period Profit formula and Decision 037 account-level Ozon monetary authority remain unchanged.

Verification:

- entering exact docs-reconciled main `9a29e853727c82abdf75b1992c45c532bd45e3ef`: Verify #1050, 2161 passed / 0 failed;
- failed `55d8f189dc170cc524aa8798aea42b1b7ae6251c`: Verify #1054, 2150 passed / 11 failed;
- failed `9f32163739d849dfe3681a9de6358fb64db40100`: Verify #1055, 2150 passed / 11 failed;
- failed `e788e5110109eb678767313278580989b192f689`: Verify #1060, 2160 passed / 1 failed;
- cancelled intermediate SHAs carry no transferable success evidence;
- final feature `07f9a35eb238280e95b52bc14d18cc6aba735703`: Verify #1062, 2171 passed / 0 failed;
- PR #389 synthetic `77dd43cfeb36ebe0066f8747c6c51580083848a6`: Verify #1063, 2171 passed / 0 failed;
- squash main `875cc4a783a48eb9a9059b9e2e9ba85316fbdc0d`: Verify #1064, 2171 passed / 0 failed.

Preserved:

- Decision 036;
- Decision 037;
- Decision 038;
- account-level Ozon monetary authority;
- no double subtraction of Ozon expenses;
- no automatic return COGS reversal;
- no accounting net-profit claim;
- `data/users.json` unchanged;
- `externally_verified=False`.

Next accounting priority:
- prove return-related COGS recovery with stronger historical cost, sale-period lineage and saleable/restored inventory evidence;
- keep candidate recovery out of profit until that proof exists;
- then address taxes/accounting adjustments outside the configured tax policy and any uncovered external-expense periods.

---

# Return Sale-Period Lineage Evidence v1271-v1280 — 2026-09-03

Completed:

[x] Positive sale posting evidence extracted from Ozon daily finance

[x] Sale evidence reuses the Period Profit FinanceService read-session cache

[x] Return records matched to positive sale evidence by posting_number + SKU

[x] Same posting with a different SKU does not confirm lineage

[x] One unique positive sale-accrual date inside the selected period is matched lineage

[x] Multiple positive sale dates remain ambiguous

[x] Missing finance days keep lineage partial

[x] Malformed positive-sale evidence cannot become clean evidence

[x] Incomplete Returns pagination prevents aggregate sale-period confirmation

[x] Return COGS candidate records expose lineage status and matched accrual date

[x] Telegram explains confirmed or partial selected-period lineage

[x] Period Profit coverage exposes sale-lineage confirmation without changing profit

Preserved:

- `confirmed_cogs_recovery_amount=0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- `historical_cost_basis_confirmed=False`;
- `saleable_inventory_recovery_confirmed=False`;
- Decision 036;
- Decision 037;
- Decision 038;
- no Ozon mutation;
- no profit-formula change;
- no persistence-contract change;
- no double subtraction;
- `data/users.json` unchanged;
- `externally_verified=False`.

Verification:

- entering exact docs-reconciled main `356fa301a9025e15a5a9fbb94da706d10670416a`: Verify #1074, 2171 passed / 0 failed;
- failed `db2c6c0fa900720c303a8f8face32ef3eec3be11`: Verify #1081, 2170 passed / 1 failed;
- cancelled intermediate SHAs carry no transferable success evidence;
- final feature `e96fb63007647857045f226c9c41fd8157ae962e`: Verify #1083, 2185 passed / 0 failed;
- PR #391 synthetic `26d6ca0e9b2ef2b4a358cc6a517bd13bf152bffc`: Verify #1084, 2185 passed / 0 failed;
- squash main `5c0ed4bd40207e3f4bcce3770e89e71e163288b1`: Verify #1085, 2185 passed / 0 failed.

Next accounting priority:

- add evidence-bound historical product cost history applicable to originating sales without backfilling unknown history by assumption;
- separately prove saleable/restored inventory recovery;
- keep COGS reversal blocked until both are proven;
- then resolve compensation timing/accounting and remaining external tax/expense gaps.

---

# Historical Product Cost Evidence v1281-v1290 — 2026-09-03

Completed:

[x] Decision 039 versioned historical product cost evidence contract

[x] Separate append-only `product_cost_history` table

[x] Existing mutable `product_costs` current-cost contract preserved

[x] No automatic migration/backfill from current cost into history

[x] Explicit `effective_from` required for historical cost versions

[x] Duplicate `product_id + effective_from` versions rejected

[x] Historical lookup selects latest explicit version effective on sale date

[x] Identifier ambiguity remains unconfirmed

[x] Dates before first explicit version remain unknown

[x] `record_product_cost_history.py` added for explicit local evidence input

[x] Return COGS candidates resolve historical cost only after matched sale lineage

[x] Historical candidate value exposed without changing Period Profit

[x] Telegram distinguishes current-cost diagnostic value from historical-cost evidence

[x] Coverage exposes historical cost confirmation state

Preserved:

- `saleable_inventory_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- Decision 036;
- Decision 037;
- Decision 038;
- no Period Profit formula change;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- `data/users.json` unchanged;
- `externally_verified=False`.

Verification:

- entering exact docs-reconciled main `212df575cc60a809032954d425902fad86623956`: Verify #1095, 2185 passed / 0 failed;
- no failed production SHA occurred;
- cancelled intermediate SHAs carry no transferable success evidence;
- final feature `f3fcb80588f394eb05e5944ca2812ed59adf7649`: Verify #1103, 2195 passed / 0 failed;
- PR #393 synthetic `672e18f904768742917df9c808c48ec476d9fd3e`: Verify #1104, 2195 passed / 0 failed;
- squash main `9ca4497dda61615076b8203d0404502630ab7e81`: Verify #1105, 2195 passed / 0 failed.

Next accounting priority:

- prove saleable/restored inventory recovery after customer returns;
- distinguish saleable recovery, unresolved/non-saleable outcomes and compensation;
- prevent double counting between inventory recovery and Ozon compensation;
- keep automatic COGS reversal blocked until recovery-state evidence is complete.


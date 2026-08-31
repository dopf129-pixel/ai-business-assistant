# Current Project State


Date:

2026-08-31



# Test Status


Verification model: SHA-bound.

Latest full-suite baseline confirmed:

1655 passed on `1f6668640988125d09d757f68dc697fc861719d3`.

GitHub Actions push verification run #436 completed successfully for this exact main SHA.

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


Создание автономного бизнес-ассистента,
который помогает управлять бизнес-процессами,
анализировать данные,
создавать планы и выполнять действия.



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


5. Не подключать canonical user-action advisory/checklist chain к Telegram без exact persisted Product Decision verification lineage


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
1655 passed on `1f6668640988125d09d757f68dc697fc861719d3`.

Verification source:
GitHub Actions push run #436, exact SHA-bound main verification with canonical `test-report.json` artifact.



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

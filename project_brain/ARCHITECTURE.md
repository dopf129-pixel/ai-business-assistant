# AI Assistant Architecture

## Project

AI Business Assistant.

The system combines task orchestration, business intelligence, product-level decision support, manual review workflows and controlled execution infrastructure.

## Core Assistant Flow

User

↓

AssistantCoreService

↓

AssistantOrchestratorV2Service

↓

AssistantEntryService

↓

AssistantMainFlowService

↓

AssistantOrchestratorBusinessService

↓

AssistantBusinessFlowService

↓

AssistantBusinessPlannerService

↓

AssistantActionPlanExecutorService

↓

AssistantActionExecutionService

↓

AssistantActionRouterService

↓

Business Executors

The existing Action / Executor pipeline is an execution subsystem. Product Decision task drafts described below do **not** enter this pipeline.

## Intelligence Layers

The product contains separate intelligence services for sales, stock, finance, returns and product unit economics. Prepared business facts are passed into higher-level decision services through explicit service boundaries and dependency injection.

## Product Business Decision Flow

Prepared Sales / Stock / Unit Economics / Returns Facts

↓

ProductBusinessDecisionQueryService

↓

ProductBusinessDecisionService

↓

ProductDecisionHistoryService

↓

ProductDecisionActionProposalService

↓

Manual Action Proposal

The decision path is read-oriented. It must not mutate marketplace state.

## Product Decision Memory and Feedback

Successful product decisions may be persisted as history snapshots. Manual feedback and later decision changes are observational signals only. They do not rewrite decision rules and must not be presented as proof of causality.

## Safe Product Action Proposal Flow

Product Business Decision

↓

ProductDecisionActionProposalService

↓

Manual Confirmation Boundary

Rules:

- `execution_allowed=False`;
- no replenishment quantity is inferred;
- no price mutation is inferred;
- no Action Executor dependency;
- no external mutation is performed.

## Product Task Draft Flow

Confirmed Proposal + Latest Decision Snapshot

↓

ProductActionTaskDraftService

↓

Persistent Product Task Draft

↓

ProductTaskDraftReviewQueueService

↓

ProductTaskDraftReadinessService

↓

Manual Review UI

Drafts are review artifacts, not executable Assistant tasks. Draft lifecycle statuses and audit events describe stored review state only.

## Draft Lifecycle and Audit

`ProductActionTaskDraftService` owns draft lifecycle reconciliation and audit events.

Supported lifecycle concepts include current draft, stale draft, dismissed draft and terminal archived draft. Idempotent commands must not create duplicate lifecycle events. Legacy records with unavailable history are reported honestly rather than reconstructed.

## Draft Review Queue

`ProductTaskDraftReviewQueueService` provides deterministic read-time prioritization of reviewable drafts. Queue score and reason codes are not persisted as learned truth and are not passed into any executor.

## Draft Readiness

`ProductTaskDraftReadinessService` evaluates whether a draft has the factual data required for manual review.

Review readiness and execution readiness are separate concepts. The execution side remains a hard false boundary.

## Draft Data Freshness Guards

Autonomous Assistant v8 adds a separate read-only `ProductTaskDraftFreshnessService`.

Flow:

Product Task Draft Snapshot

↓

ProductTaskDraftFreshnessService

↓

`FRESH` / `STALE` / `UNKNOWN`

↓

ProductTaskDraftReadinessService

↓

Review Ready or Needs Data / Refresh

Freshness rules:

- `decision_recorded_at` is the persisted timestamp of the decision snapshot, not proof of marketplace source freshness;
- sales freshness uses `sales_source_recorded_at` only when that timestamp is actually supplied by the source contract;
- stock freshness uses `stock_source_recorded_at` only when supplied;
- unit-economics freshness uses `unit_economics_source_recorded_at` only when supplied;
- missing or invalid timestamps are `UNKNOWN`;
- timestamps in the future are `UNKNOWN`;
- timestamps older than the configured maximum age are `STALE`;
- request time, cache time, draft creation time and draft update time must never be substituted for missing source timestamps.

Freshness evaluation is proposal-aware:

- `REVIEW_REPLENISHMENT` checks the decision snapshot plus sales and stock freshness;
- `REVIEW_UNIT_ECONOMICS` checks the decision snapshot plus unit-economics freshness;
- `REVIEW_MARGIN` checks the decision snapshot plus unit-economics freshness;
- unknown proposal types are handled conservatively.

Production wiring is owned by `product_business_decision_factory.py`. The default readiness service receives the default freshness service through dependency injection. Explicit custom freshness and explicit readiness-service overrides remain supported.

## Telegram Presentation Boundary

`AssistantButtonHandlerService` continues to produce the underlying draft/readiness structures.

`AssistantTelegramAdapter` enriches only the presentation of draft list/detail callbacks with freshness information:

- queue counts for fresh / stale / unknown data;
- draft-detail freshness status;
- decision-snapshot age when known;
- Russian human-readable freshness reasons.

This keeps freshness display logic out of the large button-handler business flow and preserves other callbacks unchanged.

## Execution Safety Boundary

For the Product Decision / Proposal / Draft / Freshness path:

- `execution_ready=False`;
- `executed=False`;
- `execution_allowed=False` on proposal/draft contracts remains unchanged;
- Product Task Drafts are not converted into `AssistantTaskService` tasks;
- Product Task Drafts do not enter Action Generator / Action Execution / Action Router;
- no mutating Ozon API call is connected.

A future execution policy, if ever added, requires a separate business and architecture decision.

## Project Brain

Project architecture, current state, roadmap, test map, decisions and changelog are maintained in `project_brain/` and Git. Significant changes require tests and documentation synchronization before merge.

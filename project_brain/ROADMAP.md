# Project Roadmap


## Current Stage


AI Assistant Product Development


---


# Completed


[x] Intent System


[x] Task Lifecycle


[x] Pause / Resume


[x] Cancel


[x] Action Router


[x] Executors


[x] Priority System


[x] Dependencies


[x] Conditions


[x] Skip Handling


[x] History System


[x] FAILED execution handling


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


[x] Feedback → Memory integration


[x] Memory-driven planning


[x] Memory-guided action generation


[x] Sales Intelligence Workflow v1


[x] Stock Intelligence Foundation v1



---


## Phase 1

Executor Reliability


Tasks:


[x] FAILED action state


[x] Executor error handling


[x] Error history


[x] Retry execution


[x] Retry execution history


[x] Retry policy


[x] Retry limit


[x] Retry blocked history



---


## Phase 2

Smart Planning


Tasks:


[x] Multi-level dependencies


[x] Dependency validation


[x] Automatic replanning


[x] Plan correction



---


# Phase 3

Autonomous Business Assistant


Tasks:


[x] Feedback loop


[x] Memory system


[x] Feedback → Memory connection


[x] Memory-aware planning


[x] Memory-aware action generation


[x] Long-running tasks


[x] Self-improvement cycle

Project Brain appendix: `SELF_IMPROVEMENT_CYCLE.md`



---


# Phase 4

Development Autopilot Layer


Goal:


Минимизировать ручное участие разработчика
при создании и улучшении AI Business Assistant.



Purpose:


AI Development Agent является внутренним инструментом,
ускоряющим разработку основного продукта.


Tasks:


[x] Project scanner


[x] Documentation system


[x] Test analyzer


[x] Change impact analysis


[x] Documentation drift detection


[x] Automated development workflow


[x] Git checkpoint assistant


[x] Vector memory

Project Brain appendix: `VECTOR_MEMORY.md`



---


# Product Intelligence Roadmap


Completed foundation and safety work:


[x] Stock Intelligence Integration v1


[x] Finance Intelligence


[x] Cross-Domain Business Decisions


[x] Recommendation Evolution v1 — Assortment Overview


[x] Recommendation Evolution v2 — Cache and Pagination


[x] Memory / Learning v1 — Decision Change History


[x] Memory / Learning v2 — Manual Feedback Signals


[x] Memory / Learning v3 — Outcome Correlation


[x] Memory / Learning v4 — Learning Summary

[x] Memory / Learning v5 — Learning Health Surface

[x] Memory / Learning v6 — Per-SKU Learning Coverage Queue

[x] Memory / Learning v7 — Coverage Queue Navigation

[x] Autonomous Assistant v1 — Safe Action Proposals

[x] Autonomous Assistant v2 — Confirmation Workflow

[x] Autonomous Assistant v3 — Confirmed Task Drafts

[x] Autonomous Assistant v4 — Task Draft Review Lifecycle

[x] Autonomous Assistant v5 — Review Queue Prioritization

[x] Autonomous Assistant v6 — Draft Detail and Audit Trail

[x] Autonomous Assistant v7 — Draft Readiness Checklist

[x] Autonomous Assistant v8 — Draft Data Freshness Guards

[x] Autonomous Assistant v9 — Freshness Evidence Contract

[x] Autonomous Assistant v10 — Freshness Evidence Propagation

[x] Autonomous Assistant v11 — Sales Freshness Period Evidence

[x] Autonomous Assistant v12 — Stock Freshness Observation Evidence

[x] Autonomous Assistant v13 — Freshness Coverage Summary

[x] Autonomous Assistant v14 — Freshness Refresh Guidance

[x] Freshness evidence authorization/application safety boundaries

[x] Freshness write protocol and adapter admission boundaries without enabling actual business mutation

[x] Freshness operational readiness, diagnostics and snapshot-provider boundaries

[x] Opt-in read-only freshness production composition

[x] Durable long-running task persistence/recovery hardening

[x] Terminal task/action lifecycle reconciliation

[x] Store Period Default Composition Hardening

[x] Unknown Advertising Financial Evidence

[x] Finance Context Evidence Hardening

[x] Stock Evidence Availability Hardening

[x] Sales Evidence Availability Hardening

[x] Marketing Evidence Integrity

[x] Finance Evidence Availability Propagation

[x] Executor Error-Result Lifecycle Integrity

[x] Exact Branch SHA Verification

[x] Recommendation Context Integrity

[x] Action Plan Result Integrity

[x] Business Planner Result Integrity

[x] Business Flow Result Integrity

[x] Top-Level Result Integrity

[x] Entry/Core Result Integrity

[x] Context Provider Result Integrity

[x] User Context Result Integrity

[x] User Storage Load Integrity

[x] User Storage Atomic Write Integrity

[x] User Context Pre-Commit Rollback Integrity

[x] Existing User Record Integrity

[x] Memory Persistence Result Integrity

[x] Telegram Memory Clear Integrity

[x] History Clear Integrity

[x] Telegram TypeError Retry Integrity

[x] Telegram User Admission Integrity

[x] Telegram Command Result Integrity

[x] Telegram Adapter Downstream Result Integrity

[x] Product Decision Telegram Result Integrity

[x] Financial Telegram Result Integrity

[x] Product Task Draft Telegram Result Integrity

[x] Product Decision Interaction Persistence Integrity

[x] Product Decision Learning Telegram Result Integrity

[x] Telegram Analyze / Plan History Integrity

[x] Telegram History / Memory Read Integrity

[x] Telegram Context Preparation Integrity

[x] Product Task Draft Freshness Telegram Presentation Integrity

[x] Telegram Adapter Runtime Exception Containment

[x] Post-Decision Observation Integrity

[x] Task Persistence Operator Presentation Integrity

[x] Product Decision Persistence Verification Integrity

[x] Product Decision User Action Guidance Integrity

[x] Product Decision User Action Checklist Integrity

[x] Product Decision User Action Completion Evidence Integrity

[x] Product Decision User Action Completion Persistence Integrity

[x] Product Decision User Action Completion Revision Predecessor Integrity\n\n[x] Product Decision User Action Checklist Status Persistence Lineage Integrity\n\n[x] Product Decision User Action Post-Decision Observation Lineage Integrity\n\n[x] Product Decision User Action Post-Decision Outcome Lineage Integrity\n\n[x] Product Decision User Action Learning Summary Outcome Integrity\n\n[x] Product Decision User Action Learning Evidence Quality Summary Integrity\n\n[x] Product Decision User Action Learning Confidence Evidence Integrity\n\n[x] Product Decision Action Proposal Result Integrity\n\n[x] Product Decision History Context Result Integrity\n\n[x] Unit Economics Returns Finance Impact Integrity\n\n[x] Product Decision Result Integrity\n\n[x] Product Decision Assortment Overview Integrity

Project Brain appendices include `AUTONOMOUS_ASSISTANT_V8_FRESHNESS.md`, `FRESHNESS_EVIDENCE_CONTRACT.md`, `FRESHNESS_EVIDENCE_PROPAGATION.md`, `SALES_FRESHNESS_PERIOD_EVIDENCE.md`, `STOCK_FRESHNESS_OBSERVATION_EVIDENCE.md`, `FRESHNESS_COVERAGE_SUMMARY.md`, `FRESHNESS_REFRESH_GUIDANCE.md`, `TASK_PERSISTENCE_INTEGRITY_V1.md`, `TASK_LIFECYCLE_COMPLETION_INTEGRITY_V1.md`, `EXECUTOR_ERROR_RESULT_LIFECYCLE_INTEGRITY_V1.md`, `EXACT_BRANCH_SHA_VERIFICATION_V1.md`, `RECOMMENDATION_CONTEXT_INTEGRITY_V1.md`, and `ACTION_PLAN_RESULT_INTEGRITY_V1.md`.


Current hardening queue:


1. Keep exact branch-SHA and exact merged-main GitHub Actions verification green; treat pull-request merge-ref runs as separate integration evidence.

2. Treat kernel-backed task-persistence hardening as closed after release closure v463-v472; add more persistence layers only for a concrete discovered failure or product need.

3. Treat Product Decision Learning Health and the per-SKU Learning Coverage Queue as completed seller-facing read-only learning surfaces.

4. Select the next package from a concrete current repo/product/operational gap; do not extend the learning, evidence, or lifecycle chain only to advance stage numbering.

5. Treat Product Decision verified user-action guidance/checklist Telegram wiring as closed after v1061-v1070; any further work must come from a concrete seller/operator or reliability gap rather than extending the lineage chain.

6. Keep workflow-run/test-manifest provenance development-side and explicit; no production runtime GitHub fetch.

7. Keep persistence diagnostics default-deny unless explicit operator IDs are configured.

8. Continue Project Brain drift cleanup when it changes product/safety interpretation.

9. Keep the product permanently read-only toward Ozon business state: analysis, comparison, prioritization, recommendations and non-executable drafts are allowed; price, advertising, replenishment, product-card and other Ozon mutations are out of scope.


Current checkpoint: `project_brain/CURRENT_CHECKPOINT_V1261_V1270.md`.

Current verified checkpoint: `CURRENT_CHECKPOINT_V1261_V1270.md`


## Current integration blocker

- No remaining blocker in the Product Decision verified-guidance Telegram lineage: durable lineage, read-only persistence verification, and verified guidance/checklist presentation are production-wired and exact-main verified.
- Old or malformed snapshots remain fail-closed and do not receive a verified claim.
- Business execution remains intentionally blocked pending separate architecture and authorization.


[x] Product Decision Task Draft Lifecycle Result Integrity


[x] Product Decision Unit Economics Result Integrity


[x] Product Decision Operational Metrics Result Integrity


[x] Product Decision Persistence Commit Receipt Integrity


[x] Product Decision Durable Application Lineage


[x] Product Decision Read-Only Persistence Verification


[x] Telegram Verified Product Decision Guidance / Checklist Wiring


[x] Product Decision Telegram Query Exception Containment


[x] Financial Telegram Query Exception Containment


[x] Tax Configuration Persistence & Result Integrity


[x] Tax Calculation Input & Result Integrity


[x] Advertising & Expense Finite Result Integrity


[x] Store Profit Aggregation Result Integrity


[x] Business Profit Calculation Result Integrity


[x] Finance Period Aggregation Result Integrity

[x] Period Profit Summary Input & Result Integrity

[x] Telegram Period Profit Analyst Wiring

Next seller-facing analyst priorities:
- daily attention summary;
- period sales/profit comparison;
- stock and out-of-stock risk;
- advertising-efficiency analysis from read-only evidence;
- returns/non-buyout impact;
- explainable SKU prioritization.

[x] Telegram Custom Period Date Input

[x] Tax Policy Production Availability

Next seller-facing analyst priority:
- distinguish known base unit profit from unavailable return-adjusted profit in Telegram;
- never present incomplete returns evidence as zero cost;
- keep both values explicitly scoped and read-only.

[x] Period Profit Returns Protobuf Timestamp Compatibility

[x] Period Profit Data Completeness Integrity

Next seller-facing analyst priority:
- validate live Period Profit totals after local redeploy;
- distinguish known base unit profit from unavailable return-adjusted profit;
- continue read-only daily attention and operational analytics.

[x] Period Profit Tax Rate Unit Integrity

Next seller-facing analyst priority:
- add percent-of-revenue in parentheses for each Period Profit monetary line;
- revenue = 100%;
- when revenue is zero, suppress percentage rather than inventing it;
- keep amount values and read-only semantics unchanged.

[x] Period Profit Revenue Share Presentation

[x] Finance Accrual Pagination & Read Session Integrity

[x] Account-Level Ozon Profit Reconciliation

Next seller-facing accounting priority:
- return-related COGS reversal / recovered-goods evidence;
- preserve account-level Ozon monetary authority;
- do not subtract mapped Ozon expenses twice;
- keep accounting-net-profit claim blocked until external/non-Ozon adjustments are known.

[x] Return COGS Recovery Evidence

Next seller-facing accounting priority:
- explicit non-Ozon operating expense evidence;
- support period-scoped recurring and one-off expenses;
- never treat missing expense configuration as zero;
- keep accounting-net-profit claim blocked until external expense coverage is explicit.

[x] External Operating Expense Coverage

Next seller-facing accounting priority:
- strengthen return-related COGS recovery evidence beyond candidate current-cost estimates;
- require historical cost basis, originating sale-period lineage and saleable/restored inventory evidence before any COGS reversal;
- keep `confirmed_cogs_recovery_amount=0` and profit adjustment blocked until that proof exists;
- then address taxes/accounting adjustments outside the configured policy and uncovered external-expense periods;
- preserve Decision 036 read-only Ozon boundary and Decision 037/038 no-double-counting contracts.


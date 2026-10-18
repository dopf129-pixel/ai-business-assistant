# Project Roadmap

## Активная программа planning workspace — 19.10.2026

- A–G и предыдущая периодная аналитика находятся в merged `main` `722f368526c278b701cbfd69f3dbb9a474d52386` через PR #702; main Verify `39165543772` successful. Старые статусы PR ниже — исторические checkpoint, не текущая очередь слияния.
- Исполняемое ТЗ: `LUNA_PLANNING_WORKSPACE_TASK_2026-10-19.md`, реализация H–N и O00 завершена на `codex/planning-workspace-20261019`; O00 targeted acceptance — **249 passed**. PR #705–#708 опубликованы стеком. Их Verify runs прошли Windows/Linux full suites (3,443 / 3,454 / 3,466 / 3,497 tests на соответствующих code heads) и Docker smoke. Review packet включён в PR #708; актуальный exact-head Verify и дальнейший независимый review отслеживаются там. Full local pytest не повторять после документированного ACL/shared-storage инцидента; merge/deploy/live bot не выполнялись.
- H: управляемый запуск/status/stop своего экземпляра. I: отдельная библиотека saved planning documents. J: допустимая рекламная нагрузка. K: экономика вручную заданных успешных продаж с общим налогом. L: сопоставимый план/факт. M: готовность и последовательное заполнение. N: сравнение вариантов и выгрузки. O: сквозная приёмка и independent review handoff.
- 36 этапов, зависимости, conservative defaults, числовые примеры, isolation/CAS/tax/budget contracts и журнал `LUNA_PLANNING_WORKSPACE_PROGRESS_2026-10-19.md`. Основание: `PLANNING_WORKSPACE_AUDIT_2026-10-19.md`.
- H добавляет локальное управление единственным polling экземпляром по token fingerprint и штатную остановку; `build_application()` и Ozon read-only не меняются. I добавляет tenant-scoped saved plans; J — проверяемый рекламный предел; K — economics mix с одним общим налогом. L сверяет выбранный план с canonical фактом и маркирует несовместимую прибыль; M добавляет readiness projection и точечное исправление; N сравнивает revisions и использует общий export sender. Локальные проверки не заменяют exact-head CI. Слияние, развёртывание и запуск реального бота запрещены.

## Активная программа разработки — 17.10.2026

- Владелец запустил A–G из `LUNA_LONG_RUN_PRODUCT_TASK_2026-10-17.md`. Текущий checkpoint и результаты: `LUNA_LONG_RUN_PROGRESS_2026-10-17.md`.
- A00–A04 and B00–B04 VERIFIED. Exact PR #698 foundation SHA `be76a4f8e4c7d78160e0d1047515651993062d54` passed Windows/full-verification CI run `39059951770`; exact B-head CI is tracked by PR #698. C00–C05 VERIFIED on code SHA `07b9d595df32b11b736aaa2dc13c822df7f52ec4`; Verify runs `39063730904` and `39063717597` passed Windows and full-verification, including full pytest and Docker smoke. Acceptance docs head `292c4cb83d4499045ae200862c2b3132905e409e` passed Windows/full-verification runs `39064061444` and `39064066060`. PR #699 is ready for review and stacked on #698.
- PR #697 остаётся открытым основанием; новые PR будут явно stacked. Merge/deploy не выполняются.
- B00 добавил bounded public read-only query выбранных товаров. B01 добавил stable row projections, source evidence, scoped snapshots, coverage и page reads; B02 добавил snapshot-only filters/sorting. B03/B04 добавили Telegram overview, explicit catalog groups, stale-safe callbacks, guarded transition к калькулятору цены и приёмку границ. 93 целевых tests passed; расширенный товарный regression — 1 018 passed, 12 локально ACL-deselected.

## Подготовлено следующее большое ТЗ — 17.10.2026

- `LUNA_LONG_RUN_PRODUCT_TASK_2026-10-17.md`: обязательные модули A–G, 32 этапа. A–E exact-head acceptance recorded; PR #701 code SHA `47cfa2527b2f963d2604511c76d1a41b6e6201f0` passed Windows/Linux 3 389 tests and Docker build/runtime smoke (Verify `39066587245`); docs head `f598d300164916434de27a5180bb033d8a9f4293` passed Verify `39066774774`. F00–F03 and G00 verified locally; G00 profile **54 passed, 1 ACL-bound `tmp_path` test deselected**. Exact-head CI for F–G is next. PR #700/#701 remain open for review.
- A: проверка базы, общий budget и scoped transient snapshots. B: bounded обзор выбранных товаров с filters/coverage. C: пакетный план цен разных SKU. D: чувствительность и матрица. E: CSV/JSON из точных снимков. F: обезличенная диагностика и версия процесса. G00: сквозные пользовательские пути локально VERIFIED; G01: full CI/Docker; G02: независимый review handoff.
- Основание — `LONG_RUN_PRODUCT_AUDIT_2026-10-17.md`; переиспользовать решения/forward calculator/TaxService и реализованную аналитику периодов. Новые данные Ozon, прогноз спроса, persistent saved scenarios, merge/deploy в пакет не входят.
- PR #697 при подготовке открыт и не слит. Разрешены явно зависимые ветки от проверенного head; перед стартом revalidate фактический main/PR. Сохранять локальные данные и не добавлять весь предыдущий diff повторно в новые PR.

## Ближайший продуктовый пакет — 15.10.2026

- Завершено: P00–P08 в PR #694, SKU-калькулятор в PR #695 и целевая маржа/варианты цены в PR #696. Последний PR слит в main `c55434327f50134324a5ca58e2f084854b809832`; его дерево совпадает с reviewed head `fc15b9c`. Исторические очереди ниже не открывают заново завершённые пакеты.
- Владелец выбрал следующий пакет по результатам аудита. Основание — `NEXT_DEVELOPMENT_AUDIT_2026-10-15.md`: три воспроизведённые проблемы сравнения и конкретные пробелы объяснения фактической прибыли.
- Исполняемое ТЗ: `LUNA_STORE_ANALYTICS_DEVELOPMENT_TASK_2026-10-15.md`, N00–N08 завершены. N06 добавил scoped Telegram-экраны без повторных запросов; N07 проверил cache interleavings и общие operation budgets. После исправления устаревшей assertion final code SHA `05bac9b5be203970f0d40b930fe8cc1b6036415d` прошёл full suite на Windows/Linux (**3 268 passed** каждый), compileall и Docker build/runtime smoke. Architecture review выполнен, открытых findings нет. PR #697 остаётся открытым и не слит для независимого review.
- Сохранить действующие finance/TaxService/final Return COGS/coverage contracts. Новые Ozon API, платные источники, аллокация account costs по SKU, постоянные сценарии и Ozon mutations не входят в пакет. Перед merge нужны meaningful regressions и полный CI нового SHA.


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

[x] Product Decision User Action Completion Revision Predecessor Integrity

[x] Product Decision User Action Checklist Status Persistence Lineage Integrity

[x] Product Decision User Action Post-Decision Observation Lineage Integrity

[x] Product Decision User Action Post-Decision Outcome Lineage Integrity

[x] Product Decision User Action Learning Summary Outcome Integrity

[x] Product Decision User Action Learning Evidence Quality Summary Integrity

[x] Product Decision User Action Learning Confidence Evidence Integrity

[x] Product Decision Action Proposal Result Integrity

[x] Product Decision History Context Result Integrity

[x] Unit Economics Returns Finance Impact Integrity

[x] Product Decision Result Integrity

[x] Product Decision Assortment Overview Integrity

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


Current checkpoint: `project_brain/CURRENT_CHECKPOINT_V1301_V1310.md`.

Current verified checkpoint: `CURRENT_CHECKPOINT_V1301_V1310.md`


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

[x] Return Sale-Period Lineage Evidence

Next seller-facing accounting priority:
- add versioned historical product cost evidence with explicit effective dates;
- do not backfill unknown historical cost from the current configured value;
- separately prove that returned units restore saleable inventory value or equivalent accounting value;
- keep `confirmed_cogs_recovery_amount=0` and profit adjustment blocked until historical cost and inventory recovery are proven;
- preserve Decision 036 read-only boundary and Decision 037/038 accounting ownership.

[x] Historical Product Cost Evidence

Next seller-facing accounting priority:
- prove saleable/restored inventory recovery for returned units;
- distinguish restored saleable value from unresolved/non-saleable return outcomes;
- keep compensation accounting separate and prevent double counting;
- keep `confirmed_cogs_recovery_amount=0` until recovery-state evidence is complete;
- preserve Decision 036 read-only boundary and Decision 037/038/039 accounting contracts.

[x] Return Inventory Recovery Evidence

Next seller-facing accounting priority:
- establish recovery accounting-period attribution for explicitly saleable-restored returns;
- prove originating-sale quantity consistency before any COGS reversal;
- keep compensation accounting separate and prevent double counting;
- keep `confirmed_cogs_recovery_amount=0` until remaining accounting attribution is complete;
- preserve Decision 036/037/038/039/040 contracts.

[x] Originating Sale Quantity Evidence

Next seller-facing accounting priority:
- establish explicit recovery accounting-period attribution for saleable-restored returns;
- define explicit compensation accounting treatment and double-count prevention independently from inventory recovery;
- consume/promote originating-sale quantity evidence only after those independent accounting facts are bound;
- keep `confirmed_cogs_recovery_amount=0` and profit adjustment blocked until the complete accounting gate is explicit;
- preserve Decision 036/037/038/039/040 contracts and introduce a new decision only if accounting semantics or persistence ownership changes.

## Модуль C — пакетное планирование цен

- C00/C01 VERIFIED locally; domain portion of C02 implemented and verified. One catalog snapshot feeds up to 10 exact SKU rows; source work inherits one parent budget and cache freshness. Row statuses preserve incomplete, stale, unsupported and failed facts.
- Local assumptions and target edits are pure snapshot recalculations. Shared ad rate has explicit preview/confirmation; refresh reuses the batch identity and preserves manual assumptions/provenance. Telegram runtime, result table and guarded handoff remain in progress.
- Focused C00/C01/domain C02 suite: 75 passed; compileall and diff-check passed. Follow exact stage records in `LUNA_LONG_RUN_PROGRESS_2026-10-17.md`.
# 2026-10-17 — пакетный план цены

- [x] C00–C05: пакетный read-only план для 2–10 точных SKU, общая граница источников, локальные допущения, построчные результаты и проверенный переход готового кандидата в одиночный калькулятор.
- [ ] Получить полный CI для нового exact head перед закрытием модуля C.
- [x] D00–D03: локальная таблица чувствительности по цене, себестоимости и рекламной доле; PR #700 exact-head CI зелёный.
- [x] E00: явный безопасный контракт документов Telegram; прежняя выгрузка себестоимости сохранена.
- [x] E01: versioned CSV/JSON serializers с формульной безопасностью и пределом размера без усечения.
- [x] E02–E04: CSV/JSON из точных snapshots для периода, обзора товаров, пакетного плана и чувствительности; полный scope, фильтры/сортировка, public callback → document transport, ноль повторных источников.
- [x] F00–F02 verified locally: bounded operation summary, cached completeness diagnostics, allowlisted support JSON, and read-only running-process version.
- [x] F03: diagnostic privacy, retry/timeout, cancellation, freshness and failed-document acceptance regressions.
- [x] G00: end-to-end public Telegram acceptance; source queries remain snapshot-bound.
- [x] G01: exact code head CI for F/G green on Windows/Linux and Docker; local full-suite ACL limitation documented.
- [x] G02: dependency-ordered architecture review handoff prepared; independent reviewer approval is pending. No merge/deploy.

## Planning workspace H–O (active)

- H: local single-instance Telegram lifecycle is implemented and PR #705 full Windows/Linux + Docker verification passed.
- I: durable, tenant-scoped saved price plans are implemented, including revisions and explicit source refresh; PR #706 full Windows/Linux + Docker verification passed.
- Next dependency: J adds a bounded advertising-rate solver; K uses saved plans to calculate economics for an explicit sales mix. Continue through L–N and only close O after current-head Windows/Linux and Docker checks.

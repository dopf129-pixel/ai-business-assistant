# Test Map

## Current Status

Latest full repository regression suite: **329 passed** on 2026-08-29.

## Core Assistant and Execution

Coverage includes intent handling, task lifecycle, pause/resume/cancel, dependency validation, conditions, action generation, execution routing, FAILED handling, retry policy, history, feedback, memory, replanning and end-to-end assistant flows.

Representative tests:

- `tests/test_task_*.py`
- `tests/test_action_*.py`
- `tests/test_dependency_*.py`
- `tests/test_replanning_*.py`
- `tests/test_retry_*.py`
- `tests/test_feedback_*.py`
- `tests/test_memory_*.py`
- root-level `test_assistant_*.py`

## Development Autopilot / Project Brain

Coverage includes change-impact analysis, documentation drift, development workflow, Git checkpoint preparation and Project Brain management.

Representative tests:

- `tests/test_change_impact.py`
- `tests/test_documentation_drift.py`
- `tests/test_documentation_manager.py`
- `tests/test_development_workflow.py`
- `tests/test_git_checkpoint.py`
- `tests/test_project_brain_manager.py`

## Sales Intelligence

Coverage includes Sales Intelligence service behavior, executor integration, context propagation, production wiring and prepared business-data input.

Tests:

- `tests/test_sales_intelligence_service.py`
- `tests/test_sales_intelligence_executor_integration.py`
- `tests/test_sales_intelligence_context_propagation.py`
- `tests/test_sales_intelligence_production_wiring.py`
- `tests/test_sales_intelligence_business_data_input.py`

## Stock Intelligence

Coverage includes stock metrics, sales velocity, days of stock, priority classification, executor integration, context propagation, production wiring and prepared stock data.

Tests:

- `tests/test_stock_intelligence_service.py`
- `tests/test_stock_intelligence_executor_integration.py`
- `tests/test_stock_intelligence_context_propagation.py`
- `tests/test_stock_intelligence_production_wiring.py`
- `tests/test_stock_intelligence_business_data_input.py`

## Finance Intelligence

Coverage includes finance normalization, product-level finance metrics, executor integration, context propagation, production wiring and prepared finance data.

Tests:

- `tests/test_finance_intelligence_service.py`
- `tests/test_finance_intelligence_executor_integration.py`
- `tests/test_finance_intelligence_context_propagation.py`
- `tests/test_finance_intelligence_production_wiring.py`
- `tests/test_finance_intelligence_business_data_input.py`
- `tests/test_product_level_finance_metrics.py`

## Returns and Finance Attribution

Coverage includes buyout/returns facts, analytics, query services, observed returns impact and finance attribution.

Tests:

- `tests/test_returns_buyout_facts_source.py`
- `tests/test_returns_buyout_analytics_service.py`
- `tests/test_returns_buyout_query_service.py`
- `tests/test_returns_finance_attribution_facts_source.py`
- `tests/test_returns_finance_attribution_analytics_service.py`
- `tests/test_returns_finance_attribution_query_service.py`
- `tests/test_observed_returns_impact_production_wiring.py`
- `tests/test_product_returns_finance_impact_query_service.py`

## Product Unit Economics

Coverage includes unit economics calculation, tax configuration, current economics sources, offer/SKU lookup, query caching, production wiring, Telegram presentation and observed returns integration.

Tests:

- `tests/test_product_unit_economics.py`
- `tests/test_product_unit_economics_query.py`
- `tests/test_product_unit_economics_query_cache.py`
- `tests/test_product_unit_economics_production_wiring.py`
- `tests/test_product_unit_economics_telegram_ui.py`
- `tests/test_current_product_economics_source.py`
- `tests/test_current_unit_economics_*.py`
- `tests/test_unit_economics_offer_id_lookup.py`
- `tests/test_unit_economics_observed_returns.py`
- `tests/test_tax_configuration_foundation.py`

## Product Business Decisions

Coverage includes decision inputs, decision rules, returns-aware decisions, assortment queries, cache behavior, pagination, production wiring and Telegram product-decision UI.

Tests:

- `tests/test_product_decision_input_provider.py`
- `tests/test_product_business_decision_service.py`
- `tests/test_product_business_decision_query_service.py`
- `tests/test_product_business_decision_production_wiring.py`
- `tests/test_product_business_decision_telegram_ui.py`

## Product Decision Memory / Feedback / Learning

Coverage includes decision history, change-only snapshots, manual feedback, outcome correlation, learning summaries and safe action proposal generation.

Tests:

- `tests/test_product_decision_history_service.py`
- `tests/test_product_decision_action_proposal_service.py`
- product-decision query/UI tests above.

## Product Action Proposal Confirmation

Coverage includes confirm/dismiss intent, stale-proposal guard, idempotency, non-execution contract and production wiring.

Tests:

- `tests/test_product_action_proposal_confirmation_service.py`
- `tests/test_product_business_decision_production_wiring.py`
- `tests/test_product_business_decision_telegram_ui.py`

Expected safety contract:

- confirmation stores intent only;
- `executed=False`;
- no Action Executor dependency;
- no external mutation.

## Confirmed Product Task Drafts

Coverage includes draft persistence, one-draft-per-decision-snapshot behavior, dismissal, lifecycle reconciliation, audit events, archive behavior, detail UI and review queue behavior.

Tests:

- `tests/test_product_action_task_draft_service.py`
- `tests/test_product_task_draft_review_queue_service.py`
- product-decision production/UI tests.

Expected safety contract:

- drafts are not executable Assistant tasks;
- no quantity or price inference;
- no external mutation;
- execution counts remain zero.

## Product Task Draft Readiness Checklist v1

Service:

- `ProductTaskDraftReadinessService`

Tests:

- `tests/test_product_task_draft_readiness_service.py`
- `tests/test_product_action_task_draft_service.py`
- `tests/test_product_business_decision_production_wiring.py`
- `tests/test_product_business_decision_telegram_ui.py`

Coverage:

- proposal-specific factual requirements;
- explicit missing fields;
- DRAFT lifecycle requirement;
- separate review readiness and execution readiness;
- proposal-specific execution policy blockers;
- `execution_ready=False` and `executed=False`.

## Autonomous Assistant v8 — Draft Data Freshness Guards

Services / boundaries:

- `ProductTaskDraftFreshnessService`
- `ProductTaskDraftReadinessService`
- `product_business_decision_factory.py`
- `AssistantTelegramAdapter`

Tests:

- `tests/test_product_task_draft_freshness_service.py`
- `tests/test_product_task_draft_freshness_production_wiring.py`
- `tests/test_product_task_draft_freshness_telegram.py`
- `tests/test_product_task_draft_readiness_service.py` as legacy-readiness regression coverage.

Coverage:

- `FRESH`, `STALE`, `UNKNOWN` statuses;
- real `decision_recorded_at` age calculation;
- absent or invalid timestamps remain `UNKNOWN`;
- future timestamps remain `UNKNOWN`;
- stale decision snapshot detection;
- proposal-aware required sources;
- replenishment checks sales + stock only;
- unit-economics and margin reviews check unit-economics only;
- conservative behavior for unknown proposal types;
- unknown/stale freshness blocks manual review when guard is connected;
- legacy readiness remains unchanged without an injected freshness guard;
- default freshness wiring in production factory;
- custom freshness-service DI;
- explicit readiness-service override preservation;
- Telegram queue freshness counts;
- Telegram detail status, decision-snapshot age and Russian reasons;
- non-draft Telegram callbacks remain unchanged;
- `execution_ready=False` and `executed=False` remain invariant.

Targeted implementation verification before the full regression run:

- freshness/readiness/Telegram targeted checks: **18 passed**.

Full repository regression after implementation:

- **329 passed**.

## Freshness Contract Limitation

Current sales, stock and unit-economics prepared-source contracts do not expose reliable source timestamps in production. Tests require the system to return `UNKNOWN` rather than fabricate freshness from request time, cache time, draft creation time or update time.

## Development Rule

Every completed feature must have tests, be represented in this map, update `CURRENT_STATE.md` and `CHANGELOG.md`, and update architecture documentation when the structure or service boundaries materially change.

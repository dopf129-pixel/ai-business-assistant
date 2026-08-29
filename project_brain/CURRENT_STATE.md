# Current Project State

Date: 2026-08-29

## Test Status

Full repository regression suite: **329 passed**.

Targeted Autonomous Assistant v8 verification performed during implementation:

- freshness/readiness guard checks;
- legacy readiness regression checks;
- Telegram freshness presentation checks;
- production DI/wiring coverage added.

## Current Product Direction

Main product: **AI Business Assistant**.

Current development stream: Product Intelligence → Business Data → Product Business Decision Service → Action Proposal → Human Confirmation → Product Task Draft → Review Queue → Readiness Checklist → Data Freshness Guards.

The Product Decision / Draft workflow remains deliberately separated from the existing Action Executor and from mutating Ozon API operations.

## Completed Product Intelligence / Autonomous Assistant Stages

- Product Unit Economics foundation, query, production wiring and Telegram UI;
- returns-aware Product Decisions and assortment overview;
- Product Decision cache and pagination;
- Product Decision history, feedback, outcome correlation and learning summary;
- Autonomous Assistant v1 — Safe Action Proposals;
- Autonomous Assistant v2 — Confirmation Workflow;
- Autonomous Assistant v3 — Confirmed Task Drafts;
- Autonomous Assistant v4 — Task Draft Review Lifecycle;
- Autonomous Assistant v5 — Review Queue Prioritization;
- Autonomous Assistant v6 — Draft Detail and Audit Trail;
- Autonomous Assistant v7 — Draft Readiness Checklist;
- Autonomous Assistant v8 — Draft Data Freshness Guards.

## Autonomous Assistant v8 — Draft Data Freshness Guards

Completed:

- separate read-only `ProductTaskDraftFreshnessService`;
- freshness statuses `FRESH`, `STALE`, `UNKNOWN`;
- `decision_recorded_at` is used only as the persisted decision-snapshot timestamp;
- sales, stock and unit-economics source freshness stays `UNKNOWN` unless a reliable source timestamp is actually provided;
- future timestamps are treated as `UNKNOWN`, not as fresh;
- freshness evaluation is proposal-aware:
  - `REVIEW_REPLENISHMENT` requires sales and stock freshness;
  - `REVIEW_UNIT_ECONOMICS` requires unit-economics freshness;
  - `REVIEW_MARGIN` requires unit-economics freshness;
- unknown proposal types are evaluated conservatively;
- `ProductTaskDraftReadinessService` requires `FRESH` data when the freshness guard is connected;
- legacy readiness behavior is preserved when no freshness service is injected;
- production factory supports default freshness wiring, custom freshness injection and explicit readiness override;
- Telegram review queue shows fresh/stale/unknown counts;
- Telegram draft detail shows freshness status, decision-snapshot age and Russian reason text.

Important current limitation:

The existing prepared sales, stock and unit-economics source contracts do not currently expose reliable source timestamps. Therefore production drafts that require those timestamps are honestly reported as `UNKNOWN` until such timestamps are propagated by the source layer. Request time, cache time, draft creation time and draft update time must not be used as substitutes.

## Safety Boundary

The draft workflow remains non-executable:

- `execution_ready=False`;
- `executed=False`;
- proposal/draft `execution_allowed=False` remains unchanged;
- no connection to the existing Action Executor;
- no mutating Ozon API calls;
- no inferred replenishment quantity;
- no inferred price mutation.

`data/users.json` is unchanged.

## Current Verification

Latest full suite result supplied from the repository checkout on 2026-08-29:

**329 passed**.

## Next

Autonomous Assistant v8 is complete. The next module must be selected only after comparing the roadmap with the implemented code; no execution-policy stage is assumed automatically.

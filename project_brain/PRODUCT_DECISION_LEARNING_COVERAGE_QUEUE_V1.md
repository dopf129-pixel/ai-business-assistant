# Product Decision Learning Coverage Queue V1

Date: 2026-08-30  
Stages: v493-v502  
Architecture Review Required: Yes

## Goal

Give the seller a deterministic per-SKU queue showing where Product Decision learning evidence needs attention next.

This is a feedback-coverage queue, not a business-priority queue.

## Data source

The production callback uses only:

- current product identities from `product_service.load_products()`;
- persisted decision records from `ProductDecisionHistoryService.history(sku)`.

It deliberately does **not** call `ProductBusinessDecisionQueryService.query()`.

Opening the queue therefore does not create a new Product Decision snapshot.

## v493 — Coverage states

Each SKU receives exactly one current learning-coverage state:

- `NEEDS_USER_FEEDBACK`;
- `NO_DECISION_HISTORY`;
- `WAITING_FOR_LATER_OBSERVATION`.

## v494 — Deterministic learning attention

The queue sorts by learning-evidence actionability only:

1. current persisted decision needs explicit feedback;
2. no persisted decision history exists;
3. latest decision already has feedback, so a future decision observation is needed.

Tie-breaker is exact SKU lexical order.

This rank is not seller/business priority.

## v495 — Latest feedback semantics

If the latest persisted decision already has feedback, the state is:

`WAITING_FOR_LATER_OBSERVATION`.

Older outcome evidence does not satisfy the need for a future observation after the latest feedback.

The queue does not interpret the absence of a later record as “no decision change”.

## v496 — Current missing feedback

If the latest persisted decision has no feedback, it remains:

`NEEDS_USER_FEEDBACK`

even when older feedback/outcome evidence exists.

The queue focuses on the current learning gap.

## v497 — Fail-closed history identity

The pure contract rejects:

- duplicate SKUs;
- empty SKU identity;
- malformed history rows;
- records whose SKU does not match the requested SKU;
- unknown feedback/outcome values.

No fuzzy identity matching is used.

## v498 — No business scoring

Mandatory safety fields:

- `business_priority_claimed=False`;
- `causal_claim_allowed=False`;
- `success_rate_claim_allowed=False`;
- `profitability_claim_allowed=False`;
- `decision_rule_update_allowed=False`;
- `automatic_execution_allowed=False`;
- `executed=False`.

The queue contains no profit score, success score or causal ranking.

## v499 — Read-only Telegram callback

New callback:

`product_decision_learning_coverage`

The handler:

1. loads product identities;
2. reads persisted history for each SKU;
3. calls the pure coverage builder;
4. formats the top learning-attention items.

It never calls the Product Decision query method while building the queue.

## v500 — Conditional navigation

The Product Decisions menu adds:

`🧭 Что оценить дальше`

only when:

- decision history exists;
- the coverage builder was explicitly injected.

The handler constructor uses a final optional DI argument for backward compatibility.

## v501 — Seller wording

The screen shows counts for:

- needing feedback;
- no decision history;
- waiting for later observation.

It explicitly states:

- this is a learning-evidence queue;
- it is not a business-priority queue;
- it does not evaluate profitability;
- it does not execute actions.

## v502 — Production composition

`create_telegram_assistant()` injects the canonical pure coverage builder.

No new persistence service is added.

No Product Decision rule or threshold changes.

No Ozon mutation.

No task execution.

No `data/users.json` changes.

## Important observation semantics

The existing history service creates a new snapshot when the Product Decision signature changes.

Therefore the queue must not interpret “no later snapshot yet” as evidence that the decision stayed unchanged.

The only safe wording is that a future observation is not yet available for the latest feedback.

## Relationship to canonical user-action advisory chain

This queue uses persisted legacy Product Decision history facts only.

It is not a substitute for the newer canonical user-action checklist/completion/advisory chain.

That chain remains disconnected from production Telegram until exact Product Decision persistence-verification lineage is available.

## Verification

Focused regressions cover:

1. learning-attention ordering;
2. deterministic SKU tie-break;
3. latest feedback waiting semantics;
4. current missing-feedback semantics;
5. malformed/duplicate/cross-SKU rejection;
6. no business/causal/success/profit claims;
7. no decision-query call;
8. conditional navigation;
9. seller wording;
10. forged business-priority rejection;
11. production DI.

Full GitHub Actions verification is required before merge.

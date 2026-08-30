# Product Decision Learning Coverage Navigation V1

Date: 2026-08-30  
Stages: v503-v508  
Architecture Review Required: No

## Gap

The seller-facing Learning Coverage Queue already identifies the next SKUs needing learning attention, but the screen had no direct navigation to those products.

## Change

The existing Telegram queue now attaches a bounded inline keyboard for the visible top 10 items.

State-specific labels are used:

- `NEEDS_USER_FEEDBACK` → open the current decision for evaluation;
- `NO_DECISION_HISTORY` → open the decision;
- `WAITING_FOR_LATER_OBSERVATION` → re-open/check the decision.

All SKU buttons reuse the existing `product_decision:<sku>` callback.

The queue also provides a return button to `product_decisions`.

## Safety

Opening the coverage queue remains read-only:

- it still does not call Product Decision `query()`;
- it does not record feedback;
- it does not create execution permission;
- it does not mutate Ozon;
- it does not change Product Decision rules.

No direct `product_decision_feedback:...` callbacks are emitted from the queue. The seller explicitly opens a concrete decision before using the existing feedback controls.

The handler validates generated callbacks against the exact already-validated queue SKUs and fails closed on forged navigation.

## Verification

Focused tests cover routing, labels, no-query semantics, forged callback rejection, malformed items, top-10 bounds, and read-only invariants.

Full GitHub Actions verification is required before merge.

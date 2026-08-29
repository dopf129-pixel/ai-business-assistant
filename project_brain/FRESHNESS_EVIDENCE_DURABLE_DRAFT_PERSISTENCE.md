# Freshness Evidence Durable Draft Persistence v1

## Goal

Persist v29 allowlisted freshness evidence into the existing Product Task draft storage after a valid v28 readiness chain.

## Design

`ProductTaskFreshnessEvidenceDraftPersistenceService` receives the existing draft storage through constructor injection. It loads records, requires exactly one matching `draft_id + sku`, applies the v29 mutation to a copy, and writes the record set only when freshness evidence actually changes.

The existing `ProductActionTaskDraftStorageService` remains the durable boundary and uses its dedicated `data/product_action_task_drafts.json` path with atomic replacement. `data/users.json` is not used.

## Safety

- only the six freshness evidence fields can change;
- ambiguous or missing drafts are blocked;
- invalid readiness/evidence never reaches storage save;
- repeated identical application is a durable no-op with no second write;
- write failure returns `persisted=False`;
- Product Decision recomputation/mutation remains disabled;
- Ozon mutation and legacy Action Executor are not invoked;
- `execution_allowed`, `execution_ready`, and `executed` remain false.

Targeted adapter pytest: `8 passed in 0.05s`.

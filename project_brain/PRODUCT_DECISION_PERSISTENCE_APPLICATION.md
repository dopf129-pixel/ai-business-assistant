# Product Decision Persistence Application v1

## Goal

Persist an explicitly authorized and v40-ready Product Decision preview into the existing Product Decision history while keeping all execution paths manual and disabled.

## Application service

`ProductDecisionPersistenceApplicationService(history_service)` uses constructor injection and accepts:

- the v40 persistence application readiness artifact;
- the original full recompute preview decision.

The service validates the v40 readiness ID and safety flags, requires persistence permission, checks the full preview SKU, and verifies all stable decision fields (`decision_type`, `priority`, `confidence`, `reasons`) against the authorized compact preview before calling the existing history service.

The full preview is recorded rather than the compact review view so Product Decision history can retain available business metrics such as stock, sales velocity, profit, margin, and economics basis.

## Existing history semantics

`ProductDecisionHistoryService` records a new snapshot only when its existing signature (`decision_type`, `priority`) changes. v41 preserves that contract. If the existing latest history snapshot has the same signature, v41 blocks before the write with `DECISION_HISTORY_SIGNATURE_UNCHANGED` rather than claiming persistence for a confidence/reasons-only change that history would deduplicate.

## Success

`PRODUCT_DECISION_PERSISTENCE_APPLIED` means the existing history service accepted the record call and returned an available history context.

The result marks:

- `persistent=True`;
- `product_decision_persisted=True`;
- `decision_persistence_application_started=True`;
- `decision_persistence_application_completed=True`.

Durable read-back verification is intentionally a separate next stage.

## Safety boundary

This state mutation is limited to Product Decision history.

- no Ozon mutation;
- no legacy Action Executor;
- no automatic business action execution;
- `product_decision_mutated=False` for the in-memory decision object;
- `ozon_mutation_called=False`;
- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

Business actions remain user-executed.

Focused minimal-checkout smoke validation: `7 passed in 0.04s`.

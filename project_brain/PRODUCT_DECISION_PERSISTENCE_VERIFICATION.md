# Product Decision Persistence Verification v1

## Goal

Independently read back the latest Product Decision history snapshot after v41 and verify that the durable record matches the authorized persisted Product Decision.

## Verification service

`ProductDecisionPersistenceVerificationService(history_service)` uses constructor injection and accepts the successful v41 persistence application artifact.

The service validates the complete application → readiness → authorization → eligibility → review → delta → recompute-preview lineage before reading history.

It requires the v41 application to be completed and persisted while all Product Decision execution boundaries remain disabled.

## Durable read-back

The verifier calls only `history_service.latest(sku)` and performs no write.

It requires the latest history snapshot `recorded_at` to match the `decision_recorded_at` returned by the v41 history context. This prevents verification of an unrelated later or older snapshot.

It compares the persisted preview with the history snapshot across all fields currently stored by `ProductDecisionHistoryService`:

- sku;
- product_id;
- decision_type;
- priority;
- confidence;
- reasons;
- sales_velocity;
- current_stock;
- days_of_stock;
- decision_profit_per_unit → history `profit_per_unit`;
- decision_margin_percent → history `margin_percent`;
- economics_basis.

Any mismatch fails closed and reports `mismatched_fields`.

## Success

`PRODUCT_DECISION_PERSISTENCE_VERIFIED` means the exact v41 record was read back and matched the expected Product Decision snapshot.

## Safety boundary

- no history write;
- no storage write;
- no Ozon mutation;
- no legacy Action Executor;
- no automatic business action execution;
- `execution_allowed=False`;
- `execution_ready=False`;
- `executed=False`.

Business actions remain user-executed.

Focused in-memory validation: `8 checks passed`.

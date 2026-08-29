# Product Decision User Action Guidance v1

## Goal

Turn a verified persisted Product Decision into a clear manual action checklist for the user.

The contract accepts only a successful v42 durable persistence verification and validates the verification/application lineage and execution safety boundary.

## Guidance

Supported decision types map to manual guidance:

- REPLENISH_HIGH_PRIORITY / REPLENISH_NORMAL → review replenishment;
- INVESTIGATE_LOW_PROFIT → review unit economics;
- WATCH_LOW_MARGIN → review margin;
- HOLD_STOCK → monitor only.

The guidance does not infer a replenishment quantity, a new price, or any other business value that is not already supported by the decision evidence.

## Execution boundary

Every successful and blocked result preserves:

- user_execution_required=True;
- automatic_execution_prohibited=True;
- ozon_mutation_called=False;
- execution_allowed=False;
- execution_ready=False;
- executed=False.

No Action Executor or mutating Ozon API is invoked. The user performs any business action manually.

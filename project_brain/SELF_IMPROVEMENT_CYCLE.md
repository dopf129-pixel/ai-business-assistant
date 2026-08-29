# Self-improvement Cycle v1

## Goal

Close the existing learning loop without introducing a second planning or memory architecture.

## Existing capabilities

The project already had the individual parts of the loop:

- execution feedback can be recorded by `AssistantFeedbackService`;
- feedback can be stored by `AssistantMemoryService`;
- `AssistantPlanningService` can read matching memory;
- `AssistantActionGeneratorService` can attach matching memory to generated actions.

The missing production link was dependency injection: the Telegram production factory created the planning and action-generation services without the shared memory instance that receives feedback.

## v1 contract

`create_telegram_core()` now wires one shared `AssistantMemoryService` into:

- `AssistantFeedbackService`;
- `AssistantPlanningService`;
- `AssistantActionGeneratorService`.

This creates the explicit loop:

`feedback -> memory -> next plan / next generated action`

Learning remains exact-action scoped through the existing `recall(action)` behavior. Unrelated actions do not receive unrelated memory.

## Scope boundary

This stage changes dependency wiring only. It does not alter recommendation algorithms, retry policy, replanning policy, task execution semantics, Product Decision execution, or Ozon mutation behavior.

Memory is context for later planning/action generation; it does not authorize execution.

## Validation

`tests/test_self_improvement_cycle.py` validates:

1. shared production memory wiring;
2. feedback becoming visible to a subsequent plan;
3. feedback becoming visible to subsequent action generation;
4. isolation of unrelated action memory.

Targeted self-improvement tests passed.

Full repository validation reported by the project owner:

`392 passed`

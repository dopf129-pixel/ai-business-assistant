# Period Profit Assistant Entry Route v1

`AssistantEntryService` now accepts an optional `period_profit_runtime_service`.

Explicit profit requests are offered to that narrow read-only runtime first. If it returns a result, the general business planner/orchestrator is bypassed. If it returns `None`, the existing assistant flow continues unchanged.

This isolates financial query handling from action planning and prevents a read-only profit question from being interpreted as an executable business action.

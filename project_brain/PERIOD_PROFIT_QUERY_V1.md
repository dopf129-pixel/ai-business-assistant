# Period Profit Query v1

Read-only orchestration for user-facing profit questions.

Flow:

1. Normalize a preset or custom period.
2. Load the product set through injected product provider.
3. Calculate scoped Period Profit Summary v1.
4. Optionally calculate the immediately previous comparable period and comparison.
5. Return Russian user-facing text plus structured summary/comparison.

The service is constructor-injected and introduces no Ozon mutation, Product Decision mutation, Action Executor usage, or automatic execution. `read_only=True` and `executed=False` are explicit outputs.

Because this is a new service, Architecture Review Required applies.

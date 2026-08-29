# Period Profit Assistant Runtime v1

Adds a narrow read-only assistant route for explicit profit questions.

Supported text forms include:

- profit for today;
- 7/28/56/90 day periods;
- custom ranges with two ISO dates;
- explicit `period_profit:<CODE>` callbacks.

Non-profit text returns `None` so the existing assistant flow can continue unchanged. Ambiguous profit requests ask for a period instead of guessing.

The runtime delegates only to `PeriodProfitQueryService`; it introduces no Ozon mutation, Product Decision mutation, Action Executor use, or automatic execution. New service => Architecture Review Required.

# Period Profit Return Evidence Response v1

The user-facing period-profit response now explains Ozon return evidence without changing the calculated profit.

If return records are observed, the response reports their count and explicitly says their monetary impact is not yet included. If no return records are returned, the response reports that fact but still keeps return adjustments outside the profit formula.

This distinction prevents two unsafe conclusions:

- observed return records are not automatically converted into a monetary loss;
- absence of returned records does not change the contractual `returns_included=False` state.

No Ozon mutation, Product Decision mutation, or automatic execution is introduced.

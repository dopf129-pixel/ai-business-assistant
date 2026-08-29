# Period Profit Return Evidence Query v1

`PeriodProfitQueryService` now accepts an optional return-evidence service and exposes its read-only result alongside the period-profit summary.

Production wiring injects `PeriodProfitReturnEvidenceService(OzonClient())`, so standard period-profit queries can confirm whether Ozon return records exist for the requested period.

The evidence does not change the period profit amount and does not flip `returns_included`. If return evidence is unavailable, the query blocks instead of silently presenting a result with unknown return evidence.

Safety remains explicit:

- no return monetary impact is inferred;
- `returns_profit_adjustment_allowed=False`;
- no Ozon mutation;
- no Product Decision mutation;
- no automatic execution.

Review classification: Architecture Review Required because an existing query contract and production wiring are extended.

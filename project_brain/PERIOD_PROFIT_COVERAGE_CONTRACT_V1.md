# Period Profit Coverage Contract v1

Adds an explicit read-only coverage artifact for period-profit results.

Tracked components:

- Ozon fee components;
- returns;
- advertising;
- storage.

The artifact distinguishes included and missing components and reports `PARTIAL` or `COMPLETE` only relative to this tracked set. Even `COMPLETE` does not authorize an accounting net-profit claim: `accounting_net_profit_claim_allowed=False` remains fixed because additional accounting adjustments may exist outside this product contract.

`PeriodProfitQueryService` now exposes this coverage artifact alongside the summary and comparison so UI/assistant layers can communicate data limitations without inferring unsupported costs.

No Ozon mutation, Product Decision mutation, Action Executor use, or automatic execution path is introduced.

Review classification: Architecture Review Required because the query service response contract is extended.

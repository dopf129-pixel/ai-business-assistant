# Q10 acceptance: advertising scenarios and compensation thresholds

Date: 2026-10-27  
Implementation branch: `codex/price-profit-per-unit-implementation-20261027`  
Stage: Q10 — advertising modes and rounded per-unit-profit compensation thresholds.

## Accepted behavior

- Candidate comparison accepts one explicit advertising basis: SAME_DRR on seller revenue, a separate DRR for each price, or a manually provided total advertising spend divided by the explicitly stated number of successful sales. The original scenario is preserved while the user edits candidate assumptions.
- All rows use `UnitPriceScenarioService`; the manual total-spend denominator is `SUCCESSFUL_UNITS`, and cost per successful unit is rounded to currency precision. Derived candidate DRR is an equivalent scenario input and is not presented as an observed Ozon rate.
- For each calculable candidate, a bounded solver finds the largest DRR on a 0–100% grid with 0.01 percentage-point resolution at which the rounded canonical per-unit profit is at least the baseline and strictly greater than the baseline. It verifies the boundary and next tick with direct canonical forward calls. Tax regimes whose tax depends on advertising expense remain inside that forward calculation.
- A threshold that cannot be reached even at 0% DRR is returned as `NOT_REACHABLE`. Unknown tariffs, invalid inputs, and incomplete forward results remain unavailable rather than becoming zero. The solver limits work to 64 evaluations per candidate and 1,024 per comparison.
- Applying a selected candidate only changes the local scenario after a direct forward comparison confirms the exact rounded profit. No Ozon mutation or additional source/API read was introduced.
- These are controlled scenarios. They do not estimate price elasticity, guarantee conversion growth, forecast campaign efficiency, or establish causal changes in sales or advertising spend.

## Verification

- Focused isolated Windows/Python 3.12.10 profile — **112 passed in 1.70s** across target planning, scenario Telegram runtime, ad-cap service and canonical scenario calculation.
- Linked Q04–Q10 isolated profile — **390 passed in 7.90s** across 22 tariff, planning, scenario, source and consumer test files.
- Five protected tracked owner-data JSON SHA-256 hashes matched before and after the linked profile. A new temporary storage root and pytest basetemp were used. Dotenv and pytest plugin autoload were disabled; credential-named environment variables were removed without reading or printing their values. No owner database, ignored runtime data, `.env`, live bot or Ozon/Telegram API was used.
- Four changed Python modules passed `py_compile`. Diff whitespace validation is recorded in the Q10 progress journal after documentation updates.

## Architecture and limits

Q10 adds a pure bounded compensation solver and extends the existing comparison result and Telegram flow. `UnitPriceScenarioService` remains the only forward financial engine; tariff comparison continues to use the frozen snapshot. The threshold is limited to the supported DRR grid and the monotonicity check probes domain boundaries. It is not a demand forecast or production outcome. Classification: **Architecture Review Required**. Full repository pytest and exact-head CI remain scheduled for Q33–Q35; no merge, deploy or real bot run was performed.

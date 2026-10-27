# Q12 acceptance — target price across tariff segments

Date: 2026-10-27
Implementation branch: `codex/price-profit-per-unit-implementation-20261027`
Stage: Q12 — minimum target-margin price with frozen tariff bands.

## Accepted behavior

- The existing single-rate target solver remains unchanged when no tariff resolution is requested; its previous 128-forward-call contract is preserved.
- When tariff resolution is requested, the solver validates the frozen snapshot against the exact owner/store/product/offer/SKU and current seller-price identity. It enforces the shared maximum of 20 tariff rules before searching.
- Candidate prices are partitioned at every frozen band start and end using integer kopecks. Each covered interval has one resolvable rate/profile. Gaps, conflicts, expired profiles and unavailable sources remain unavailable; no neighboring rate or zero commission is substituted.
- A legacy saved-plan commission without a frozen profile is usable only at its exact saved price. It is never extrapolated to another price.
- Target search visits covered intervals in ascending price order. Within each interval it uses five ordered canonical forward probes, refuses an observed true-to-false target reversal, then narrows only a false/true bracket inside that same interval. It does not run the old binary search across tariff jumps.
- Each found price is recalculated directly through `UnitPriceScenarioService`; the preceding kopeck inside its covered interval is directly checked. An unverified result or exhausted evaluation budget cannot be applied.
- A result states the minimum only among calculated tariff intervals and lists unresolved price ranges. It does not claim a global minimum when coverage is partial. A fully covered tariff still does not claim a global optimum outside the calculator's supported price domain.
- The Telegram target-margin flow resolves and freezes the tariff once, displays coverage limitations, and applies the chosen price/rate only after existing direct validation. No Ozon API requests or price mutations were added.

## Verification

- Focused isolated Windows/Python 3.12.10 profile (`test_unit_price_target_planning_service.py`, `test_unit_price_scenario_telegram_runtime.py`, `test_unit_price_tariff_snapshot_adapter.py`): **115 passed in 1.65s**.
- Linked isolated Q04–Q12 profile across 21 tariff, planning, saved-plan, scenario, source and Telegram test modules: **404 passed in 7.97s**.
- Regressions cover the synthetic 11%→22% tariff jump, a goal reachable both before and after the jump, a later-only feasible segment, explicit gaps and profile conflicts, point-only/legacy exact-price behavior, unavailable source, the 20-rule ceiling and 1,024-forward-call budget, observed non-monotonicity, candidate revalidation and Telegram apply.
- The linked test run used a new `%TEMP%` pytest root. Dotenv and pytest plugin autoload were disabled; credential-named environment variables were removed without printing their values. No Ozon/Telegram API, network, live bot, owner database or ignored runtime store was used. The five protected tracked JSON files remained clean against HEAD.
- `git diff --check` passed. Full repository pytest, exact-head CI and independent architecture review remain Q33–Q35.

## Architecture and limits

Q12 extends the existing `UnitPriceTargetPlanningService` and Telegram calculator route. `UnitPriceScenarioService`/`TaxService` remain the only forward financial engine; the tariff adapter and search perform local resolution only. The change modifies an existing service contract and user-facing result semantics: **Architecture Review Required**. Merge, deployment and real-bot execution were not performed.

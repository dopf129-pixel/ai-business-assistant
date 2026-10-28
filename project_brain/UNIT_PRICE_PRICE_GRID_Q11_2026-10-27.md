# Q11 acceptance — bounded seller-price grid

Date: 2026-10-27  
Implementation branch: `codex/price-profit-per-unit-implementation-20261027`  
Stage: Q11 — bounded candidate grid, tariff boundaries and paginated Telegram result.

## Accepted behavior

- The user enters a seller-price interval as `start; end; step`. Prices are validated at currency precision; the requested end is included even when the step does not land on it.
- Every frozen tariff band contributes its in-range lower/upper price and the adjacent cent where present. The actual sorted and deduplicated candidates are retained in `price_grid.searched_prices` and displayed as pages of 10.
- The grid refuses more than 200 candidates or more than 20 tariff rules. It does not truncate and continue with a misleading subset. The result labels the highest calculated profit as the maximum on the tested grid only, never a global optimum.
- Each candidate uses the frozen tariff snapshot and canonical `UnitPriceScenarioService`. Missing/unknown tariffs remain unavailable and are never replaced by a zero commission or zero profit. The result rows omit repeated full forward payloads to keep the stored grid compact.
- Advertising compensation thresholds are skipped for grid rows. When the owner chooses one price, the existing apply path rechecks the candidate through canonical forward and computes its bounded compensation thresholds against the same baseline before updating only local scenario assumptions.
- Pagination remains available for reading a stale result. Applying a price is disabled when source freshness is no longer valid. Price-grid callbacks remain below Telegram's 64-byte callback-data limit in tested scenarios.
- No network calls or seller-price mutations were added per candidate.

## Verification

- Focused isolated Windows/Python 3.12.10 profile (`tests/test_unit_price_target_planning_service.py`, `tests/test_unit_price_scenario_telegram_runtime.py`, `tests/test_unit_price_tariff_snapshot_adapter.py`): **104 passed in 1.55s**.
- Linked Q04–Q11 tariff/planning/scenario/source/consumer profile over 22 test modules: **398 passed in 8.05s**.
- The profile covers boundary and adjacent-cent insertion, requested end inclusion, exact 200-point limit, 20-rule aggregate limit, refusal without truncation, rejection of tampered metadata that omits candidates, unknown tariff behavior, forward-call budget, compact rows, page navigation, stale read-only pagination, selected-row application, and source/profile read counts.
- Three modified Python modules passed in-memory compilation. `git diff --check` passed.
- All five protected tracked JSON files are git-clean against HEAD. Their LF-normalized SHA-256 matches Git objects; raw worktree bytes use CRLF. Test storage and pytest basetemp were newly created under `%TEMP%`, dotenv and plugin autoload were disabled, credential-named process variables were removed without printing values. No owner database, ignored runtime data, `.env`, Ozon/Telegram API, network or live bot was used.

## Architecture and limits

Q11 extends the existing `UnitPriceTargetPlanningService` result contract and the current calculator's Telegram keyboard/runtime. It does not introduce another finance formula, persistence owner or network dependency. It can identify only the best candidate among the exact grid points tested. Classification: **Architecture Review Required**. Q11 is verified locally; full repository pytest, exact-head CI and independent review remain scheduled for Q33–Q35. Merge, deployment and real-bot execution were not performed.

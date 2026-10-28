# Q07 acceptance — Telegram input and confirmation for manual commission

Date: 2026-10-27
Implementation branch: `codex/price-profit-per-unit-implementation-20261027`
Task: `LUNA_PRICE_PROFIT_PER_UNIT_TASK_2026-10-26.md`

## Implemented

- The existing FBO unit-price scenario exposes a manual-commission action. The route is wired through the normal `AssistantTelegramAdapter` and `AssistantButtonHandlerService` composition.
- Input accepts one exact seller-price point or up to 20 inclusive, non-overlapping commission bands. Prices are converted to integer kopecks; decimal comma/dot and a first-line effective date are accepted. Unsupported or malformed input stays in the input stage and never writes a profile.
- Preview shows the SKU, FBO scheme, seller-price basis, start date, bands and manual-source label. The user can explicitly save persistently, apply only to this in-memory scenario, edit, refresh the existing Ozon snapshot, or cancel.
- Persistent create/update uses `PlanningWorkspaceRepository` with Q06 tenant checks, identity allowlist, revisions, compare-and-swap, idempotency, quotas and history. Session-only profiles remain in bounded process memory for at most one hour and are retrieved only for the same active owner/store/scenario identity.
- Draft tickets bind owner, store, product, offer, SKU, FBO scheme, scenario id/version and TTL. Starting a replacement draft invalidates the previous ticket. A stale/replayed callback fails closed; only the explicit persistent confirmation reaches storage.

## Verification

Isolated Windows/Python 3.12.10 interpreter, fresh TEMP storage and pytest `--basetemp`, dotenv disabled, no network, no live Ozon/Telegram API and no real bot process.

```text
tests/test_unit_price_tariff_input_parser.py
tests/test_telegram_unit_price_tariff_profile_runtime.py
tests/test_planning_workspace_tariff_profiles.py
tests/test_unit_price_scenario_telegram_runtime.py
tests/test_planning_workspace_repository.py
tests/test_saved_planning_plan_telegram_flow.py
199 passed in 4.47s
```

`py_compile` passed for all changed Python modules. `git diff --check` passed. No protected tracked owner-data file was included in the implementation diff; test storage was directed to a fresh TEMP directory.

## Boundaries and next step

Q07 only captures and confirms a manual profile. It does not yet change the active commission in the calculator. Q08 must resolve the persistent or session-only profile against the exact seller price/date and include the resolved profile revision, rate and provenance in captured/frozen saved-plan revisions. Old plan formats must remain readable and must not be silently recalculated.

No actual bot, external API, merge or deployment was performed.

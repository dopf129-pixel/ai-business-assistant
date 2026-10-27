# Unit-price observation result (Q19)

Date: 2026-10-27
Status: VERIFIED

## Implemented

- Added pure `UnitPriceObservationResultService`. It accepts only Q18-normalized FBO evidence, binds it to the exact saved scenario identity and seller price, and produces the existing repository result envelope (schema version 1).
- A model is available only with a confirmed positive successful-unit denominator, a complete Performance CPC amount, a complete ANALYTICS or FINANCE unit source, and matching date window, timezone and source date basis. Mixed-price windows and mismatched identities/prices/bases remain incomparable. Missing evidence remains insufficient or source-unavailable; profit is never zero-filled.
- The model obtains CPC per successful unit through the existing bounded parser, rounds that amount to canonical cents, and calls the existing `UnitPriceScenarioService` for the actual unit-profit/tax calculation. The weighted CPC numerator and successful-unit denominator remain visible; observed profit remains `None`.
- `profit_per_unit` and `scenario_profit_per_unit` are populated only with `evidence_basis=MODELLED_FROM_OBSERVED_INPUTS`; the result warns that advertising is CPC-only, the owner-declared price does not prove historical per-sale price, and no causal demand/ad-efficiency claim is made. Finance window totals remain context and are not deducted a second time.
- No current supported source provides verified per-sale seller price/event time or a complete successful-unit cohort. Therefore current Q17/Q18 collection cannot produce `CANONICAL_FACT_COMPARABLE`, nor does it currently satisfy the model denominator gate. A correct current-store outcome remains `INSUFFICIENT_DATA`/`INCOMPARABLE` until later supported evidence supplies that denominator. Caller-supplied canonical labels are ignored.
- No repository schema, database migration, Ozon request, Telegram flow or live behavior changed in Q19. Q20 will connect the result evaluator to the observation workflow.

## Verification

Windows, Python 3.12.10, isolated temporary storage and pytest basetemp; dotenv/plugin autoload disabled and provider/credential environment variables removed. No `.env`, live API, production database, tracked owner data or bot process was used.

Final linked Q16–Q19 profile: **189 passed in 4.10s** across 12 modules, including the new result service regressions, Q18 normalizer, Q17 collector, observation repository, production source wiring, finance and Performance scoped/source/budget tests. `py_compile` for the new service and test passed.

Regressions cover canonical calculator parity, result repository-schema validation, untrusted canonical-label rejection, exact identity and seller-price matching, missing successful-unit denominator, mixed-price windows and incompatible date bases. Full pytest/exact-head CI remains scheduled for Q33–Q35.

## Architecture and next step

Classification: **Architecture Review Required** because Q19 adds an application service that composes normalized observation evidence with the existing canonical unit calculator. It remains pure and introduces no new storage or network layer. No new architectural decision was needed; Decision 061 and the Q03 contracts remain unchanged.

Next: Q20 — connect preview/start, collection, result persistence/reopen, notes and finish through the existing Telegram observation flow, preserving owner/store/SKU binding and read-only Ozon access.

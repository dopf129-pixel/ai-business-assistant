# Period Profit Return COGS final chain binding

Production basis: `57cb131769fe2f7fff4a0181be59172657f374d0`.

## Decision

A canonical committed status and a true commit boolean are necessary but are no longer sufficient by themselves for seller-facing final application. Before Period Profit is recomputed, every durable commit row must be bound back to the exact accounting-recognition row and exact profit-application authorization row that authorized that commit.

The final service therefore validates the complete `recognition → authorization → commit` chain again at the application boundary. This is defense in depth against synthetic, malformed, stale, or partially copied evidence objects reaching the final read-only calculation.

## Exact binding contract

For every commit record, production requires:

- a positive unique `recognition_history_id`;
- a positive unique `authorization_history_id`;
- an existing recognition row with the same recognition history ID;
- an existing authorization row with the same authorization history ID;
- exact `return_id / posting_number / sku` identity equality across recognition, authorization, and commit;
- the authorization row to reference the same recognition history ID;
- exact recovery-accounting-date equality across all three rows;
- RUB currency at recognition, authorization, and commit;
- committed amount equality with both the recognized amount and the authorized amount.

Recognition rows must themselves remain canonical ready/confirmed records with `COGS_RECOVERY_RECOGNIZED`. Authorization rows must remain canonical ready/confirmed records with `PROFIT_APPLICATION_AUTHORIZED` and `application_already_applied=False`.

## Coverage contract

Final application also requires complete set coverage. The set of recognition history IDs represented by durable commits must exactly equal the set of supplied recognition records. The set of authorization history IDs represented by durable commits must exactly equal the set of supplied authorization records.

Extra recognition or authorization evidence is therefore not ignored, and a missing durable commit cannot be hidden by matching the aggregate amount only.

## Monetary application

Only after the exact chain is bound does the service compare the committed total with `return_cogs_profit_application_eligible_amount`. If the totals differ, final application remains unavailable.

The existing tax-policy recomputation then runs over the already bound committed amount. No new amount is inferred. No missing amount is converted to zero. No `quantity × guessed unit cost` derivation is introduced.

A successful result exposes `return_cogs_final_application_chain_bound=True` both at the top level and inside evidence. The flag is emitted only after the cross-stage binding and coverage checks pass.

## Failure semantics

The final application fails closed for, among other cases:

- missing recognition records;
- missing authorization records;
- malformed or duplicate recognition versions;
- malformed or duplicate authorization versions;
- non-ready recognition or authorization row status;
- missing explicit recognition or authorization confirmation;
- invalid recognition/authorization state;
- missing recognition or authorization binding for a durable commit;
- identity mismatch;
- recognition-version mismatch;
- accounting-date mismatch;
- amount mismatch;
- incomplete recognition coverage;
- incomplete authorization coverage;
- aggregate committed-vs-eligible total mismatch.

These failures do not execute any financial mutation. The response remains `read_only=True`, `executed=False`, with `return_cogs_profit_applied=False` on unavailable paths.

## Safety invariants

- Ozon remains READ-ONLY.
- `ReturnedToOzon` remains candidate evidence only and is not proof of `SALEABLE_RESTORED`.
- `unknown != zero`.
- Missing accounting/business evidence is not auto-filled.
- Recognition does not imply authorization.
- Authorization does not imply commit.
- Commit status does not permit final application unless exact upstream records still reconcile.
- Aggregate amount equality cannot replace exact per-record identity/version/date/amount binding.
- Final Period Profit remains a read-only recomputation from already durable evidence; no repository write path is added.

## Regression coverage

The package adds regression coverage proving that final application rejects:

- a commit referring to a missing recognition history ID;
- a commit referring to a missing authorization history ID;
- an authorization row with a different return/posting/SKU identity;
- a recognized amount different from the committed amount;
- an authorization accounting date different from the commit/recognition date;
- incomplete recognition coverage.

It also proves that a complete exact chain still applies the committed Return COGS amount to the read-only Period Profit result and emits `return_cogs_final_application_chain_bound=True`.

## SHA-bound verification evidence

- feature head `9ddc0907d506de2c0a3df9fc6f0c9fa92cf3990d` — Verify #1720 passed; artifact `verification-9ddc0907d506de2c0a3df9fc6f0c9fa92cf3990d`;
- PR #489 synthetic merge `aad9e3357162d5bcdfc56956975fb14d76b6d8bb` — Verify #1721 passed; artifact `verification-aad9e3357162d5bcdfc56956975fb14d76b6d8bb`;
- squash production main `57cb131769fe2f7fff4a0181be59172657f374d0` — Verify #1722 passed; artifact `verification-57cb131769fe2f7fff4a0181be59172657f374d0`.

Verification evidence is SHA-bound and must not be transferred between revisions.

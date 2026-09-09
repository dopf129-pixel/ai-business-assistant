# Verification Status

Date: 2026-09-09

## Latest verified product baseline

`57cb131769fe2f7fff4a0181be59172657f374d0`

Package: `Return COGS final recognition → authorization → commit chain binding`.

### Exact feature head

- SHA `9ddc0907d506de2c0a3df9fc6f0c9fa92cf3990d`;
- Verify #1720 succeeded;
- artifact `verification-9ddc0907d506de2c0a3df9fc6f0c9fa92cf3990d`;
- digest `sha256:d930f7d5fc78c08293453dccc51af9b09636dd15b5f1adc128e67f40358b0880`.

### PR integration checkout

- PR #489;
- synthetic merge SHA `aad9e3357162d5bcdfc56956975fb14d76b6d8bb`;
- Verify #1721 succeeded;
- artifact `verification-aad9e3357162d5bcdfc56956975fb14d76b6d8bb`;
- digest `sha256:b1702a15668e5115da031c4eac096420421fe07e0edbba8d751beab57715e765`.

### Exact production main

- squash SHA `57cb131769fe2f7fff4a0181be59172657f374d0`;
- Verify #1722 succeeded;
- artifact `verification-57cb131769fe2f7fff4a0181be59172657f374d0`;
- digest `sha256:b68dc20e786ba436a2070e3d25239ea7519c4a07d005c35eac940e7f2bd85eb4`.

## Product behavior verified

Seller-facing Period Profit keeps the Return COGS chain fail-closed from candidate evidence through inventory recovery, accounting attribution/compensation clearance, accounting recognition, application authorization, durable exact-once commit, and final read-only application.

Canonical status+boolean conjunctions remain required at accounting, recognition, authorization, and commit. Final application now additionally binds every durable commit row back to its exact recognition and authorization records by history IDs, exact return/posting/SKU identity, recovery accounting date, RUB currency, and monetary amount. Recognition and authorization coverage must be complete before any final Return COGS adjustment is reflected in seller-facing profit.

A successful final result exposes `return_cogs_final_application_chain_bound=True`. Missing, malformed, stale, mismatched, or partially copied evidence fails closed instead of being inferred or treated as zero.

The historical control warning of 8 unresolved units/returns remains distinct from the 785 exact raw Returns API records. Repository evidence does not prove the identities of that historical set of 8 and no identity list is fabricated.

## Safety invariants

- Ozon remains read-only.
- `ReturnedToOzon` is candidate evidence only and is not `SALEABLE_RESTORED`.
- `unknown != zero`.
- No guessed `quantity × unit cost` Return COGS derivation is permitted.
- Missing accounting/business facts are not auto-filled.
- Recognition does not imply authorization; authorization does not imply commit; commit does not bypass final exact-chain reconciliation.
- Seller-facing Period Profit remains `read_only=True` and `executed=False`.

## Verification policy

Verification is SHA-bound. Exact branch verification proves only that branch head. PR verification proves only the synthetic integration checkout. Every squash-main SHA requires its own exact verification. Failed SHAs remain failed permanently and successful evidence is never transferred between revisions.

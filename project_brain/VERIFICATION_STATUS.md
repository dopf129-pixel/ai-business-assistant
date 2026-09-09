# Verification Status

Date: 2026-09-09

## Latest verified product baseline

`6e08187ae7fde85f0985fd0082876c4c0f1f2574`

Package: `Return COGS downstream commit/final integrity gates`.

### Exact feature head

- SHA `80f697bfb853175fd0ea45d7f145298c78dae140`;
- Verify #1733 succeeded;
- artifact `verification-80f697bfb853175fd0ea45d7f145298c78dae140`;
- digest `sha256:86fb9a5530b0a72fcd7cfd803b126201d32bd31d2e6516fb1f0242bbded5f3fe`.

### PR integration checkout

- PR #491;
- synthetic merge SHA `bfdf3eb0cb430f5303f44cd48667f73261764d87`;
- Verify #1734 succeeded;
- artifact `verification-bfdf3eb0cb430f5303f44cd48667f73261764d87`;
- digest `sha256:29dc3f9183c50035e097b7a54e4ed4c178db8f5d345014fb27768ee483ae093f`.

### Exact production main

- squash SHA `6e08187ae7fde85f0985fd0082876c4c0f1f2574`;
- Verify #1735 succeeded;
- artifact `verification-6e08187ae7fde85f0985fd0082876c4c0f1f2574`;
- digest `sha256:fde356adf84ca4cbb80b1f74d683ee8aadc310cec545259e689a47c9c8f8bd25`.

## Product behavior verified

Seller-facing Period Profit keeps the Return COGS chain fail-closed from candidate evidence through inventory recovery, accounting attribution/compensation clearance, accounting recognition, application authorization, exact-once commit, and final read-only application.

The production chain now includes separate downstream integrity wrappers. Commit integrity rechecks canonical eligibility, complete candidate coverage, recognition and authorization row state, finite RUB amounts, accounting dates, monetary-authority exclusion, monetary-authority non-overlap, compensation non-overlap, and durable commit binding. Final integrity requires exact candidate → recognition → authorization → commit identity-set equality before the existing final calculation can run.

NaN and Infinity are invalid monetary evidence. A downstream subset cannot be accepted merely because its own aggregate amount reconciles. A durable commit row whose `error` field is unknown is invalid. Missing monetary-authority or compensation non-overlap proof remains unconfirmed.

Successful final application can expose `return_cogs_final_application_chain_bound=True`, `return_cogs_final_candidate_coverage_confirmed=True`, and `return_cogs_final_monetary_authority_reconfirmed=True`. These are read-only evidence flags, not mutation authority.

The historical control warning of 8 unresolved units/returns remains distinct from the 785 exact raw Returns API records. Repository evidence still does not prove the identities of that historical set of 8 and no identity list is fabricated.

## Safety invariants

- Ozon remains read-only.
- `ReturnedToOzon` is candidate evidence only and is not `SALEABLE_RESTORED`.
- `unknown != zero`.
- No guessed `quantity × unit cost` Return COGS derivation is permitted.
- Missing accounting/business facts are not auto-filled.
- Recognition does not imply authorization; authorization does not imply commit; commit does not bypass downstream exact-chain and candidate-set reconciliation.
- Seller-facing Period Profit remains `read_only=True` and `executed=False`.

## Verification policy

Verification is SHA-bound. Exact branch verification proves only that branch head. PR verification proves only the synthetic integration checkout. Every squash-main SHA requires its own exact verification. Failed SHAs remain failed permanently and successful evidence is never transferred between revisions.

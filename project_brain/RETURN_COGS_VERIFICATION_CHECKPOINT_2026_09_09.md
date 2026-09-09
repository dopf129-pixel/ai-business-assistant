# Return COGS verification checkpoint — 2026-09-09

Production code basis: `93ee4633295f483d04d445693c29bdf0c0139f40`.

This checkpoint records the currently proven seller-facing Return COGS control chain after the inventory, accounting diagnostics, recognition diagnostics, authorization/commit diagnostics, blocker-stage orchestration, and canonical-status hardening packages.

## Proven control chain

The current production chain is fail-closed in this order:

`candidate identity/quantity → inventory recovery → accounting attribution/compensation clearance → accounting readiness → recovery amount evidence → recognition eligibility → accounting recognition → application authorization/eligibility → exact-once commit readiness/commit → final read-only Period Profit application`.

No later boolean is sufficient to bypass the canonical status of its own stage. `PeriodProfitReturnCogsBlockerStageService` is the seller-facing first-blocker ordering authority, and compact Telegram diagnostics consume that resolver rather than maintaining a second gate-order implementation.

## What production can prove automatically

Where authoritative source evidence exists, production can automatically validate return candidate lineage, exact return/posting/SKU identity, originating-sale quantity evidence, historical effective-cost evidence, period matching, exact monetary reconciliation, canonical service statuses, durable recognition/authorization/commit versions, committed amounts, dates, currency, and duplicate recognition-version prevention.

Automatic validation is not the same as automatically supplying a missing business fact. The system does not invent inventory restoration, accounting attribution, compensation treatment, recognition, authorization, or commit evidence.

## Facts that remain explicit

The following remain explicit local/business/accounting evidence rather than inferred Ozon truth:

- whether returned stock is actually `SALEABLE_RESTORED` or `NON_SALEABLE`;
- accounting recovery attribution where no authoritative local record exists;
- compensation treatment and double-count clearance;
- accounting recognition;
- profit-application authorization;
- durable exact-once commit.

`ReturnedToOzon` does not replace the inventory fact.

## Seller-facing behavior

Compact Period Profit shows only the first unresolved stage. Exact rows are rendered from existing evidence and never become a write surface. Missing quantity remains `неизвестно`.

A commit-ready candidate is still described as not committed. A committed canonical chain that is not yet represented in seller-facing profit is described as `FINAL_APPLICATION`, with an explicit warning that this is not permission to repeat commit.

Final application recomputes the read-only Period Profit result only from already confirmed canonical downstream evidence and durable commit records. It does not mutate Ozon or accounting repositories.

## Historical warning semantics

The historical control warning of 8 unresolved returns/units must not be conflated with the 785 exact raw Returns API records from the control period. The warning is unresolved unit/candidate observability, not a raw API record count and not a financial `Возврат выручки` count.

The repository evidence still does not prove the identities of the historical set of 8. No identity list is fabricated from the 785-record source set.

## Safety invariants

- Ozon: READ-ONLY.
- Seller-facing Period Profit: `read_only=True`, `executed=False`.
- `unknown != zero`.
- `ReturnedToOzon != SALEABLE_RESTORED`.
- No guessed `quantity × unit cost` Return COGS.
- No automatic accounting fact creation.
- No boolean-only bypass of canonical statuses.
- No commit-ready → committed coercion.
- No final-application blocker → repeated-commit authorization.

## Verification chain for canonical-status package

- Feature SHA `d6352a58314e5b178e94c270af44a13210c1d21d`: Verify #1709 passed; artifact `verification-d6352a58314e5b178e94c270af44a13210c1d21d`.
- PR #487 synthetic merge SHA `113c70f2134d2f00dd750dac673bc32e9b6571ad`: Verify #1710 passed; artifact `verification-113c70f2134d2f00dd750dac673bc32e9b6571ad`.
- Production main SHA `93ee4633295f483d04d445693c29bdf0c0139f40`: Verify #1711 passed; artifact `verification-93ee4633295f483d04d445693c29bdf0c0139f40`.

The verification model remains SHA-bound. A successful report for one SHA is not evidence for a different revision.

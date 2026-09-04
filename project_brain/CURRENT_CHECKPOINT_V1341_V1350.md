# Current Checkpoint v1341-v1350

Date: 2026-09-04

Package: `Return COGS Recognition Eligibility`

## Status

Production lifecycle complete and exact-main verified.

Exact production main:

`5e579797ffbb78480445d90bbd9c8bb6f8f8b07d`

Verify #1186: 2258 passed / 0 failed.

## Entering baseline

Exact docs-reconciled predecessor:

`3b384ce8fd6820e00e412c3b0d75e78ffb231192`

No verification evidence is transferred between SHAs.

## Objective

Bind staged Return COGS monetary evidence to exact candidate identities and explicit requested-period accounting attribution, producing recognition eligibility without yet recognizing or applying money.

## Eligibility contract

Eligibility requires:

1. `return_cogs_accounting_readiness_confirmed=True`;
2. `return_cogs_recovery_amount_evidence_confirmed=True`;
3. finite non-negative staged amount;
4. staged currency exactly RUB;
5. non-empty candidate set;
6. exact `return_id + posting_number + SKU` identity coverage across candidates, staged amount records and accounting attribution records;
7. no duplicate identities;
8. every staged amount record ready and finite;
9. aggregate staged amount reconciled to per-candidate amount records within 0.01 RUB;
10. every attribution row explicitly ready and matched to the requested accounting period;
11. compensation state explicitly known;
12. compensation double-count clearance explicitly true.

Missing, malformed, conflicting or unmatched evidence blocks eligibility and leaves the eligible amount unknown.

## Recognition remains closed

Even when eligibility is confirmed:

- `period_cogs_recovery_confirmed=False`;
- `accounting_cogs_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0.0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- `compensation_profit_adjustment_allowed=False`.

## Production changes

Added:

- `app/services/period_profit_return_cogs_recognition_eligibility_service.py`;
- `tests/test_return_cogs_recognition_eligibility_v1341_v1350.py`.

Updated:

- `app/period_profit_factory.py`;
- `tests/test_period_profit_factory.py`.

## Verification evidence

No failed production SHA occurred in v1341-v1350.

### Exact feature head

- SHA `92c1e0b61cea965d848cbb79a125c05f02f5ef77`;
- Verify #1184;
- 2258 passed / 0 failed;
- artifact 9933760826;
- digest `sha256:04259a0faabf1743f590b12ba25cab5187248e50688111ab6e49ac2bfd8350cc`.

### PR synthetic integration

- PR #405;
- synthetic SHA `3b053dad64370a8e1f796c0c2f4097ab4a7b1eec`;
- Verify #1185;
- 2258 passed / 0 failed;
- artifact 9933811873;
- digest `sha256:da1c3c105d8ee93443bcd1f4ed87fd632c6a535fefa63e378b2601b852a201f3`.

### Exact squash-main

- SHA `5e579797ffbb78480445d90bbd9c8bb6f8f8b07d`;
- Verify #1186;
- 2258 passed / 0 failed;
- artifact 9933829424;
- digest `sha256:7d69f91bb3bfc14ae95a1c2a6299bcf85f840e936a9e5c958e69adc29fa10033`.

## Preserved boundaries

- permanent read-only Ozon product boundary;
- account-level Ozon monetary authority;
- all earlier evidence/readiness/amount contracts remain prerequisites;
- no Period Profit formula change;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Next accounting gap

Define a separate accounting-recognition evidence contract for an already-eligible amount. Keep actual Period Profit application disabled until recognition evidence itself is exact, period-bound and fail-closed.

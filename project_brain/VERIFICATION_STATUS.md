# Verification Status

Date: 2026-09-04

## Latest verified product baseline

`5e579797ffbb78480445d90bbd9c8bb6f8f8b07d`

Latest merged production batch:

`v1341-v1350: Return COGS Recognition Eligibility`

### Entering exact docs-reconciled main

- exact main: `3b384ce8fd6820e00e412c3b0d75e78ffb231192`;
- no verification evidence is transferred from this predecessor to later revisions.

### Failed intermediate evidence

No failed production SHA occurred in v1341-v1350. Failed SHAs from earlier packages remain failed evidence permanently.

### Exact feature-head verification

- SHA `92c1e0b61cea965d848cbb79a125c05f02f5ef77`;
- Verify #1184;
- 2258 passed / 0 failed;
- artifact 9933760826;
- digest `sha256:04259a0faabf1743f590b12ba25cab5187248e50688111ab6e49ac2bfd8350cc`.

### PR merge-ref integration verification

- PR #405;
- synthetic SHA `3b053dad64370a8e1f796c0c2f4097ab4a7b1eec`;
- Verify #1185;
- 2258 passed / 0 failed;
- artifact 9933811873;
- digest `sha256:da1c3c105d8ee93443bcd1f4ed87fd632c6a535fefa63e378b2601b852a201f3`.

### Post-merge exact-main verification

- exact main `5e579797ffbb78480445d90bbd9c8bb6f8f8b07d`;
- Verify #1186;
- 2258 passed / 0 failed;
- artifact 9933829424;
- digest `sha256:7d69f91bb3bfc14ae95a1c2a6299bcf85f840e936a9e5c958e69adc29fa10033`.

## Current Return COGS recognition-eligibility boundary

Eligibility requires accounting readiness, staged monetary evidence, exact identity coverage, RUB amount reconciliation, requested-period accounting attribution, explicit compensation state and explicit double-count clearance.

`return_cogs_recognition_eligibility_confirmed=True` is recognition eligibility only.

Accounting recognition and application remain closed:

- `period_cogs_recovery_confirmed=False`;
- `accounting_cogs_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0.0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`.

Period Profit formula is unchanged. No Ozon mutation is authorized or performed.

## Verification policy

Exact branch push verification proves only that exact branch head. Pull-request verification proves only the synthetic merge ref. Every squash-main SHA requires its own exact push verification. Failed SHAs remain failed evidence permanently. Cancelled/pending SHAs carry no transferable success claim. Missing evidence remains unknown and is never interpreted as zero or clean. Workflow evidence is project CI evidence only; `externally_verified=False`.

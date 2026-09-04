# AI Assistant Project State

## Current product state

AI Business Assistant is a read-only Ozon business analyst and advisor. Ozon business mutations remain prohibited by Decision 036.

## Current verified checkpoint

Package: `v1341-v1350: Return COGS Recognition Eligibility`

Exact production main: `5e579797ffbb78480445d90bbd9c8bb6f8f8b07d`

GitHub Actions push Verify #1186: 2258 passed / 0 failed.

## Period Profit accounting boundary

Decision 037 account-level Ozon finance remains the monetary authority.

Base formula remains unchanged:

`period_profit = account_net_accrual - product_cost - configured_tax`

Return COGS evidence now has an explicit recognition-eligibility layer after accounting readiness and staged monetary evidence.

Recognition eligibility requires exact identity coverage across candidate records, staged amount records and accounting-attribution records using `return_id + posting_number + SKU`. The staged aggregate must reconcile to the per-candidate amount records, currency must be RUB, every accounting attribution must belong to the requested period, compensation treatment must be explicit, and compensation double-count clearance must be true.

## Eligibility is not recognition

When all prerequisites are proven:

- `return_cogs_recognition_eligibility_confirmed=True`;
- `return_cogs_recognition_eligible_amount` may expose the staged RUB amount;
- `return_cogs_recognition_eligible_currency="RUB"`.

This does not book or apply the amount. In v1341-v1350:

- `period_cogs_recovery_confirmed=False`;
- `accounting_cogs_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0.0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`.

## Production verification

No failed production SHA occurred in v1341-v1350.

- feature `92c1e0b61cea965d848cbb79a125c05f02f5ef77` — Verify #1184 — 2258 passed / 0 failed — artifact 9933760826 — digest `sha256:04259a0faabf1743f590b12ba25cab5187248e50688111ab6e49ac2bfd8350cc`;
- PR #405 synthetic `3b053dad64370a8e1f796c0c2f4097ab4a7b1eec` — Verify #1185 — 2258 passed / 0 failed — artifact 9933811873 — digest `sha256:da1c3c105d8ee93443bcd1f4ed87fd632c6a535fefa63e378b2601b852a201f3`;
- squash main `5e579797ffbb78480445d90bbd9c8bb6f8f8b07d` — Verify #1186 — 2258 passed / 0 failed — artifact 9933829424 — digest `sha256:7d69f91bb3bfc14ae95a1c2a6299bcf85f840e936a9e5c958e69adc29fa10033`.

## Preserved boundaries

- Decisions 036-043 remain unchanged;
- Decision 044 records the recognition-eligibility boundary;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- no Period Profit formula change;
- no accounting-recognized Return COGS amount;
- no compensation double counting;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Next accounting package

Define an explicit accounting-recognition evidence layer for an already-eligible amount. Recognition evidence must remain separate from Period Profit application so that booking semantics can be proven before any seller-facing profit value changes.

# Verification Status

Date: 2026-09-04

## Latest verified product baseline

`3f82b65054a2a7a48b9918803c197377bdb3557f`

Latest merged production batch:

`v1291-v1300: Return Inventory Recovery Evidence`

### Entering exact-main verification
- exact main: `7f859d1073338c5c0144edea8fe15574460e5210`
- Verify #1115
- 2195 passed / 0 failed
- artifact id: 9906440691
- digest: `sha256:42618c7cd0f12fdd9b1c49f2231c990c71c6931727af3a09e1035719f248929a`

### Failed intermediate evidence

Failed SHA evidence is permanent and cannot be promoted by later green runs.

- exact SHA: `41b409edcd2a96016bf49e8e8303a7aec00c1886`
  - Verify #1125
  - compile failed (`SyntaxError`)
  - no verification artifact
- exact SHA: `4643126328c9e461712aae30f5f7a694a7549e89`
  - Verify #1126
  - compile failed at `app/period_profit_response.py:706`
  - no verification artifact
- exact SHA: `d90549d21c8fb46b0a9012c205520c68e012dbfa`
  - Verify #1127
  - compile failed with unmatched `)` at `app/period_profit_response.py:744`
  - no verification artifact
- exact SHA: `13e4cfbacf617bb60c5b897137b619f079c3d500`
  - Verify #1128
  - 2203 passed / 5 failed
  - artifact id: 9906768012
  - digest: `sha256:59dd7f0d342951b258bdef1d45b934cd107a858fc986d9326d1f06df016c2944`
  - failure cause: test-double return IDs were string-keyed while production preserved numeric Ozon Return API IDs; the test stub was corrected without weakening production identity semantics

### Exact final feature-head verification
- exact SHA: `1a83e5466bfebd79370e9576ce00b43b79bb668d`
- Verify #1129
- 2208 passed / 0 failed
- artifact id: 9906795648
- digest: `sha256:a20b8f66b8d28365b7c9d887250782e7ab01d7885ddcca75c5bfab90541bd875`

### PR merge-ref integration verification
- PR #395
- synthetic SHA: `7d7b3a5e180a2505850345cc753a7d40ba391cbf`
- Verify #1130
- 2208 passed / 0 failed
- artifact id: 9906847145
- digest: `sha256:36f7babc92f4f0d39e708927a61e95122eada8b76892dc4eb7da8912f3e01fa4`

This proves only the PR synthetic integration revision.

### Post-merge exact-main verification
- exact main: `3f82b65054a2a7a48b9918803c197377bdb3557f`
- Verify #1131
- 2208 passed / 0 failed
- artifact id: 9906878610
- digest: `sha256:45eb967f32521ae3c7a2007663f6acfffcf6fa2f1fbdddb58bc332f56a02311d`

## Current accounting safety boundary

Decision 040 adds explicit return-inventory recovery evidence only.

Even when originating sale period, historical cost basis and saleable inventory recovery are confirmed:

- `originating_sale_quantity_confirmed=False`
- `recovery_period_attribution_confirmed=False`
- `compensation_accounting_treatment_confirmed=False`
- `period_cogs_recovery_confirmed=False`
- `accounting_cogs_recovery_confirmed=False`
- `confirmed_cogs_recovery_amount=0.0`
- `profit_adjustment_allowed=False`
- `automatic_recovery_allowed=False`

Current Ozon stock snapshots or stock deltas are not proof of return recovery.
Period Profit formula is unchanged.

## Verification policy

Exact branch push verification proves only that exact branch head.
Pull-request runs prove only their synthetic merge refs.
Every squash-main SHA requires its own exact push verification.
Failed SHAs remain failed evidence permanently.
Cancelled/pending SHAs carry no transferable success claim.
Missing evidence remains unknown and is never interpreted as zero/clean.
Workflow evidence is project CI evidence only;
`externally_verified=False`.

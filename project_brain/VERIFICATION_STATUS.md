# Verification Status

Date: 2026-09-05

## Latest verified product baseline

`f96e291a8bd8b19c8b68e618b160cdca13fd31c4`

Package: `v1411-v1420: Period Profit Historical SKU Cost Recovery`

### Failed precursor

- SHA `898ef3cc3a59939b2b9d97939b267ccccb54178a`;
- Verify #1282 failed;
- this SHA remains failed permanently and receives no transferred success claim.

### Exact feature head

- SHA `7db015ae85326a2210e49162413ea6563a932c4d`;
- Verify #1283 succeeded.

### PR integration checkout

- PR #419;
- synthetic merge SHA `a40e207c4e55a80c041643b93877d9806c0e30fc`;
- Verify #1284 succeeded;
- artifact `9968047432`;
- digest `sha256:e8927c2c4c6bb2fba49ff2ce4bdced5d2412876103dccc6b577d83b99f37c537`.

### Exact production main

- squash SHA `f96e291a8bd8b19c8b68e618b160cdca13fd31c4`;
- Verify #1285 succeeded;
- artifact `9968055763`;
- digest `sha256:6ce330fb8775d0ff2b2c85150b6110f17cd6a98acbb300f6c74492a261bb6791`.

## Runtime defect boundary

Historical finance SKUs are no longer required to exist in the current Ozon catalog. A missing current-catalog SKU may be recovered only from confirmed historical cost evidence at the selected period end or from a unique existing local cost record for the exact SKU.

Ambiguous, invalid, non-RUB or unknown cost remains unavailable and fails closed. Account-level Ozon finance remains monetary authority, product/account revenue reconciliation remains mandatory, and Ozon mutation remains prohibited.

## Verification policy

Exact branch verification proves only that branch head. PR verification proves only the synthetic integration checkout. Every squash-main SHA requires its own exact verification. Failed SHAs remain failed permanently. Missing evidence is unknown, not zero. `externally_verified=False` until Telegram production validation confirms the repaired path.

# Verification Status

Date: 2026-09-05

## Latest verified product baseline

`91cba3362c67253cfb938458d716e5651471b5c9`

Package: `v1421-v1430: Period Profit Historical SKU Cost Input`

### Failed precursor

- SHA `8b0deeef6032b7f9d6732c9df323b3926b08b205`;
- Verify #1296 failed;
- this SHA remains failed permanently and receives no transferred success claim.

### Exact feature head

- SHA `148fde8d62caa158a85258b49ead954ca498b5f6`;
- Verify #1299 succeeded.

### PR integration checkout

- PR #421;
- synthetic merge SHA `91800bd8537cd964dbc8864752435b7a5e5deb99`;
- Verify #1300 succeeded;
- artifact `9968493971`;
- digest `sha256:c4ea23a745bba85e1bc85355d9a1bc4c9fa2ffe1d243a42287f15bc7cc28bbbf`.

### Exact production main

- squash SHA `91cba3362c67253cfb938458d716e5651471b5c9`;
- Verify #1301 succeeded;
- artifact `9968500427`;
- digest `sha256:791b5d2bfac7f0720b253c69eeca29c873edcb16a5589f399ecd08ec9add6d9d`.

## Runtime defect boundary

Finance SKU `3398133813` is present in the selected Ozon finance period but has no seller-confirmed local COGS evidence. Telegram therefore exposes `/costsku SKU COST` to store a local RUB cost without mutating Ozon. The resulting unique local SKU cost can be consumed by the existing historical finance-SKU recovery path.

Unknown, invalid, ambiguous or unavailable cost remains unavailable and fails closed. Account-level Ozon finance remains monetary authority, product/account revenue reconciliation remains mandatory, and Ozon mutation remains prohibited.

## Verification policy

Exact branch verification proves only that branch head. PR verification proves only the synthetic integration checkout. Every squash-main SHA requires its own exact verification. Failed SHAs remain failed permanently. Missing evidence is unknown, not zero. `externally_verified=False` until Telegram production validation confirms a seller-entered real COGS and successful Period Profit calculation.

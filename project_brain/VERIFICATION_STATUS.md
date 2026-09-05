# Verification Status

Date: 2026-09-05

## Latest verified product baseline

`cb6f3fd3341debf52617688350a3c6d7cab336fd`

Package: `v1401-v1410: Period Profit Finance SKU Scope`

### Failed precursor

- SHA `6650f02f255a07765ee8a53d518c16d3f34acc7d`;
- Verify #1268 failed;
- this SHA remains failed permanently and receives no transferred success claim.

### Exact feature head

- SHA `2737896a5def0d058a946c4edcbc69b07906d344`;
- Verify #1269 succeeded.

### PR integration checkout

- PR #417;
- synthetic merge SHA `962810cf789e62b16d287addbc182d7e9917576b`;
- Verify #1271 succeeded;
- artifact `9967881438`;
- digest `sha256:3534e8cbb49340a7157c3b9e33dd0ed4bddf60954a084af58f6f501ed50effbf`.

### Exact production main

- squash SHA `cb6f3fd3341debf52617688350a3c6d7cab336fd`;
- Verify #1272 succeeded;
- artifact `9967892096`;
- digest `sha256:fb2a8fa99482e86d2c70e7e9a40547f71065899c1162e7916999511c585a4e7a`.

## Runtime defect boundary

The selected-period SKU scope now comes from unique SKUs observed in Ozon finance `POSTING` accruals. Current catalog rows are used only for identity/cost mapping and are deduplicated by SKU.

A finance SKU without catalog/cost mapping fails closed. Account-level Ozon revenue and `net_accrual` remain monetary authority, and product/account revenue reconciliation remains mandatory as the final integrity guard.

## Verification policy

Exact branch verification proves only that branch head. PR verification proves only the synthetic integration checkout. Every squash-main SHA requires its own exact verification. Failed SHAs remain failed permanently. Missing evidence is unknown, not zero. Ozon mutation remains prohibited. `externally_verified=False` until Telegram production validation confirms the repaired path.

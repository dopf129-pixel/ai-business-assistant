# AI Assistant Project State

## Current product state

AI Business Assistant remains a read-only Ozon business analyst and advisor. Ozon business mutations remain prohibited.

## Current verified checkpoint

Package: `v1421-v1430: Period Profit Historical SKU Cost Input`

Exact production main: `91cba3362c67253cfb938458d716e5651471b5c9`

Verify #1301: success.

Artifact: `9968500427`.

Digest: `sha256:791b5d2bfac7f0720b253c69eeca29c873edcb16a5589f399ecd08ec9add6d9d`.

## Period Profit runtime fix

Telegram production validation confirmed that finance SKU `3398133813` has no confirmed local cost evidence. This is not an Ozon retrieval defect: seller COGS is local seller-confirmed data and must not be inferred from finance or replaced with zero.

Telegram now supports `/costsku SKU СЕБЕСТОИМОСТЬ`. The command stores only a local seller-confirmed RUB cost under a finance-SKU identity. It never writes to Ozon. Period Profit can then recover that historical finance SKU from the unique local cost record and recompute the selected period.

Invalid, negative, ambiguous, missing or unavailable cost still fails closed.

## Period Profit accounting boundary

Account-level Ozon revenue and `net_accrual` remain the monetary authority. Product/account revenue reconciliation remains mandatory.

The canonical seller-facing calculation remains:

`period_profit = account_net_accrual + exact_committed_return_cogs_if_valid - product_cost - configured_tax`

Unknown monetary evidence remains `None`, never inferred zero. Ozon remains read-only.

## Verification lifecycle

Failed feature precursor remains failed permanently:

- `8b0deeef6032b7f9d6732c9df323b3926b08b205` — Verify #1296 failed due to Telegram factory compatibility; later success is not transferred to it.

Successful lifecycle:

- feature head `148fde8d62caa158a85258b49ead954ca498b5f6` — Verify #1299 succeeded;
- PR #421 synthetic merge `91800bd8537cd964dbc8864752435b7a5e5deb99` — Verify #1300 succeeded; artifact `9968493971`, digest `sha256:c4ea23a745bba85e1bc85355d9a1bc4c9fa2ffe1d243a42287f15bc7cc28bbbf`;
- squash production main `91cba3362c67253cfb938458d716e5651471b5c9` — Verify #1301 succeeded; artifact `9968500427`, digest `sha256:791b5d2bfac7f0720b253c69eeca29c873edcb16a5589f399ecd08ec9add6d9d`.

## Preserved boundaries

- account-level Ozon finance remains monetary authority;
- finance-period SKU evidence defines product-cost scope;
- current catalog is not treated as historical truth;
- seller COGS is never inferred from Ozon finance;
- `/costsku` mutates only local cost storage, never Ozon;
- ambiguous or unknown cost fails closed;
- duplicate SKU rows are not double counted;
- product revenue reconciliation remains required;
- no compensation double counting;
- exact-once Return COGS commitment remains append-only;
- unknown money remains `None`, not zero;
- `externally_verified=False` until the user enters the real COGS and validates Period Profit in Telegram.

## Next product work

After `git pull`, enter the real seller-confirmed cost for the blocked SKU, for example `/costsku 3398133813 450`, then repeat `Прибыль за период`. The numeric example is syntax only and must be replaced by the real COGS.

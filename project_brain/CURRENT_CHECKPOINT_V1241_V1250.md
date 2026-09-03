# CURRENT_CHECKPOINT_V1241_V1250

Date: 2026-09-03

## Account-Level Ozon Profit Reconciliation

Production package:

`v1241-v1250: Account-Level Ozon Profit Reconciliation`

Goal:

Move Period Profit from SKU-summed operational profit toward a seller-account profit view by using the complete account-level Ozon daily accrual as monetary authority.

## Decision 037

Account-level Ozon monetary authority is now explicit.

For Period Profit V2:

- account-level Ozon daily finance is authoritative for revenue, net accrual, commission, logistics, acquiring, other fees and fee breakdown;
- SKU-level finance remains required for product sales counts, COGS attribution and product revenue reconciliation;
- summed SKU revenue must reconcile to account revenue within 0.01 RUB;
- reconciliation failure blocks the summary;
- mapped Ozon expenses already represented in account net accrual are never subtracted again.

## Why V1 was not sufficient

SKU-filtered finance may omit account-level charges that have no SKU.

A posting-level total may also match more than one SKU in a multi-SKU posting, so summing SKU-level net accruals can duplicate the same Ozon money.

Therefore summed SKU net accrual cannot be authoritative for seller-account profit.

## V2 formula

After product revenue coverage is proven:

`period_profit = account_net_accrual - product_cost - configured_tax`

Where:

- `account_net_accrual` is complete account-level Ozon daily money;
- `product_cost` is built from SKU sales evidence and configured product costs;
- tax is calculated from reconciled account revenue using the configured tax fraction.

## New evidence fields

- `account_level_ozon_accruals_included=True`;
- `product_revenue_reconciled=True`;
- `sku_attributed_net_accrual`;
- `ozon_account_reconciliation`;
- profit scope `OZON_ACCOUNT_ACCRUALS_COST_AND_CONFIGURED_TAX_V2`.

The account reconciliation is:

`account_net_accrual - summed_sku_attributed_net_accrual`

It may represent:

- account-level operations without SKU;
- corrections for posting-level money duplicated across SKU filters;
- other attribution differences that are already part of the authoritative Ozon account total.

## Seller-facing semantics

When account-level V2 is active:

- Telegram may show the non-zero reconciliation amount and percent of revenue;
- it explains that all account-level Ozon money already enters `Начисления Ozon`;
- returns/advertising/storage mappings remain classification evidence;
- mapped Ozon amounts are not subtracted a second time.

The product still does not claim complete accounting net profit.

## Remaining accounting gaps

To move from Ozon-account profit toward accounting net profit, the next evidence gaps are:

1. return-related COGS reversal / recovered-goods semantics;
2. business expenses outside Ozon;
3. accounting/tax adjustments outside the configured tax policy;
4. complete semantic classification of Ozon return/advertising/storage operations.

The next concrete production package should target return/COGS evidence because inventing recovery value from a raw return count would be unsafe.

## Product boundary

Decision 036 remains active and unchanged.

No Ozon state mutation, Product Decision execution or Product Task Draft execution is introduced.

## SHA-bound verification

- entering exact main `0aa27a1267b9d54f1207455b05e32db843091d86`: Verify #1003, 2141 passed / 0 failed, artifact 9888777124, digest `sha256:f5251c670e44174ebebc22f3152833c94450e99c8d7cd6f0192fb9231b3f59d2`;
- final feature `a0e528f36b1b4721af0e8d0b419c414d20fabea6`: Verify #1010, 2151 passed / 0 failed, artifact 9891989048, digest `sha256:4e28915675e1e8a6acf32600fe4e0294ba5a8a378c986b10a70a56bb06302d7a`;
- PR #385 synthetic `4a361a58d62e56c2e2aa4c608620ae86992ac05f`: Verify #1011, 2151 passed / 0 failed, artifact 9892029109, digest `sha256:3c5196c966a250b5bd54e6b558be085680f352fcc156d25d8562ffd172f8869f`;
- squash main `a359e3d8e68784849caa659dec0123fb15dc6932`: Verify #1012, 2151 passed / 0 failed, artifact 9892074726, digest `sha256:212517f2c06aec43f7c089df382d111436dfa8b17bbaf9f19b719779c6d9d072`;
- no failed production SHA occurred.

GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.

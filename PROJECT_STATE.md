# AI Assistant Project State

## Current product state

AI Business Assistant remains a read-only Ozon business analyst and advisor. Ozon business mutations remain prohibited.

## Current verified checkpoint

Package: `v1411-v1420: Period Profit Historical SKU Cost Recovery`

Exact production main: `f96e291a8bd8b19c8b68e618b160cdca13fd31c4`

Verify #1285: success.

Artifact: `9968055763`.

Digest: `sha256:6ce330fb8775d0ff2b2c85150b6110f17cd6a98acbb300f6c74492a261bb6791`.

## Period Profit runtime fix

Telegram validation exposed a finance SKU (`3398133813`) that participated in the selected historical period but no longer existed in the current Ozon catalog.

Period Profit now keeps finance-period SKU evidence as the scope authority and recovers missing current-catalog SKUs only from exact local cost evidence: confirmed historical cost by SKU at the selected period end, or a unique existing local cost record for that same SKU. Ambiguous, non-RUB, invalid or unknown cost still fails closed.

The current catalog is no longer required to contain every historical SKU. It remains an identity/cost mapping source for current products only.

## Period Profit accounting boundary

Account-level Ozon revenue and `net_accrual` remain the monetary authority. Product/account revenue reconciliation remains mandatory.

The canonical seller-facing calculation remains:

`period_profit = account_net_accrual + exact_committed_return_cogs_if_valid - product_cost - configured_tax`

Unknown monetary evidence remains `None`, never inferred zero. Ozon remains read-only.

## Verification lifecycle

Failed precursor remains failed permanently:

- `898ef3cc3a59939b2b9d97939b267ccccb54178a` — Verify #1282 failed due to a compatibility assertion; later success is not transferred to it.

Successful lifecycle:

- feature head `7db015ae85326a2210e49162413ea6563a932c4d` — Verify #1283 succeeded;
- PR #419 synthetic merge `a40e207c4e55a80c041643b93877d9806c0e30fc` — Verify #1284 succeeded; artifact `9968047432`, digest `sha256:e8927c2c4c6bb2fba49ff2ce4bdced5d2412876103dccc6b577d83b99f37c537`;
- squash production main `f96e291a8bd8b19c8b68e618b160cdca13fd31c4` — Verify #1285 succeeded; artifact `9968055763`, digest `sha256:6ce330fb8775d0ff2b2c85150b6110f17cd6a98acbb300f6c74492a261bb6791`.

## Preserved boundaries

- account-level Ozon finance remains monetary authority;
- finance-period SKU evidence defines product-cost scope;
- current catalog is not treated as historical truth;
- historical SKU recovery requires exact local cost evidence;
- ambiguous or unknown cost fails closed;
- duplicate SKU rows are not double counted;
- product revenue reconciliation remains required;
- no Ozon mutation;
- no compensation double counting;
- exact-once Return COGS commitment remains append-only;
- unknown money remains `None`, not zero;
- `externally_verified=False` until the user validates the repaired runtime path in Telegram.

## Next product work

Repeat production validation of `Прибыль за период` in Telegram. If SKU `3398133813` has a confirmed historical or unique local cost record, it should now be included even though it is absent from the current Ozon catalog.

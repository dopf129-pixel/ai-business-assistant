# Current Checkpoint v1411-v1420

## Package

`v1411-v1420: Period Profit Historical SKU Cost Recovery`

## Runtime observation

Telegram returned: `Не найдены товары для SKU из финансов Ozon: 3398133813`.

The finance SKU is valid historical participation evidence, while the current Ozon catalog is only a present-state catalog and may legitimately omit old products.

## Implemented boundary

`PeriodProfitFinanceSkuScopeService` now resolves each selected-period finance SKU as follows:

1. use the current catalog row when present;
2. otherwise use confirmed historical cost evidence for the exact SKU at the selected period end;
3. otherwise use a unique existing local `product_costs` row for the exact SKU;
4. otherwise fail closed.

Recovered rows carry exact SKU, local product identity and explicit RUB cost. No unknown cost is inferred and no Ozon state is mutated.

## Verification

- failed precursor `898ef3cc3a59939b2b9d97939b267ccccb54178a` — Verify #1282 failed and remains failed;
- exact feature head `7db015ae85326a2210e49162413ea6563a932c4d` — Verify #1283 success;
- PR #419 synthetic merge `a40e207c4e55a80c041643b93877d9806c0e30fc` — Verify #1284 success;
- production main `f96e291a8bd8b19c8b68e618b160cdca13fd31c4` — Verify #1285 success;
- production artifact `9968055763`, digest `sha256:6ce330fb8775d0ff2b2c85150b6110f17cd6a98acbb300f6c74492a261bb6791`.

## Preserved invariants

Account-level Ozon finance remains monetary authority. Revenue reconciliation remains required. Ozon is read-only. Unknown money remains `None`, not zero. Return COGS exact-once and no-double-count boundaries are unchanged.

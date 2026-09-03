# CURRENT_CHECKPOINT_V1251_V1260

Date: 2026-09-03

## Return COGS Recovery Evidence

Production package:

`v1251-v1260: Return COGS Recovery Evidence`

Goal:

Expose the size and quality of potential return-related COGS recovery without increasing profit from unsupported assumptions.

## Evidence preserved

From Ozon Returns API:

- return id and posting;
- product SKU / offer / quantity;
- return type / schema;
- visual status and change moment;
- compensation status and change moment;
- return logistics moments.

## Candidate recovery

A customer-return unit may become a candidate when its visual status reaches `ArrivedAtReturnPlace`.

Candidate value is calculated using current configured product cost only.

This is a diagnostic estimate, not accounting recovery.

## Explicitly unproven

The system does not prove:

- historical unit cost at the original sale;
- that the returned item became saleable inventory;
- that the original sale occurred inside the selected Period Profit interval;
- that compensation accounting belongs to the same finance period.

Therefore:

- `historical_cost_basis_confirmed=False`;
- `originating_sale_period_confirmed=False`;
- `saleable_inventory_recovery_confirmed=False`;
- `period_cogs_recovery_confirmed=False`;
- `accounting_cogs_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`.

## Seller-facing behavior

Period Profit may display:

- candidate return-place units;
- candidate value at current cost;
- compensated units;
- unresolved recovery units.

The response explicitly states that the candidate value is not added to profit.

Account-level Ozon monetary authority from Decision 037 remains unchanged.

## Accounting progress

Current profit now includes:

- complete account-level Ozon accrual money;
- configured product COGS for observed sales;
- configured tax.

It does not yet claim accounting net profit because:

- return COGS recovery is not sufficiently proven;
- external/non-Ozon operating expenses are not represented;
- other accounting/tax adjustments may exist.

## Next production gap

Add explicit seller-configured non-Ozon expense evidence with period scope.

Requirements:

- missing expense configuration must remain unknown, not zero;
- one-off and recurring expenses must be distinguishable;
- expenses must be attributable to the selected period;
- no automatic invented expense;
- accounting-net-profit claim should remain blocked until coverage is explicit.

## SHA-bound verification

- entering exact main `55942648266e9ca4fbb3d3380180c3a67bfc4c56`: Verify #1022, 2151 passed / 0 failed, artifact 9892287935, digest `sha256:ed019db51ad4ac1660271bf36ff514010c02f507b85ebd95bea0057738b1396b`;
- failed `2339d8aa8da1ec43c3298be2da8506a1e6dd8b9b`: Verify #1033, 2159 passed / 2 failed, artifact 9894124132, digest `sha256:aebeb9bd10d18a552aad913ac6389952dc54b96735ced94417e31777f3d4706b`;
- final feature `30f3edafd9d2af603f2277701cb13492a334dd30`: Verify #1038, 2161 passed / 0 failed, artifact 9894214090, digest `sha256:1a438369ed77017cfb871ed31b8e4e6a8f1645789088bab1c0f792d0b1aaa1c3`;
- PR #387 synthetic `c5947439450297dabb353b3dfd125e3fc6417576`: Verify #1039, 2161 passed / 0 failed, artifact 9894260067, digest `sha256:4395fe30324b1557496fd20f3bbeea103e3629581bd988144ded0bec7e03ac63`;
- squash main `d845c7183ef5a914853a15b788e18b0cebfd1c93`: Verify #1040, 2161 passed / 0 failed, artifact 9894294668, digest `sha256:a32f8b63ef84938477d4852fe0fcd0104206a38ae8962fa789926a3674dc94f6`.

Failed SHA evidence is not transferable.

Decision 036 unchanged.
Decision 037 unchanged.
GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.

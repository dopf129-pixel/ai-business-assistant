# CURRENT_CHECKPOINT_V1261_V1270

Date: 2026-09-03

## External Operating Expense Coverage

Production package:

`v1261-v1270: External Operating Expense Coverage`

Goal:

Move Period Profit closer to real business profit by incorporating explicit seller expenses outside the Ozon account accrual stream while keeping missing expense evidence unknown rather than zero.

## Accounting ownership

Decision 037 remains the monetary authority for Ozon money.

Base Period Profit remains:

`period_profit = account_net_accrual - product_cost - configured_tax`

Decision 038 adds a separate evidence-bound external-expense layer.

Derived external-expense view:

`profit_after_external_expenses = period_profit - external_expenses`

External expenses may be subtracted only when they are outside Ozon account net accrual.

Ozon advertising, storage, return operations and other Ozon charges already present in `account_net_accrual` are never deducted again.

## External expense evidence

The package uses:

- persisted local `expenses` rows;
- explicit `expense_coverage` intervals.

An expense row contains:

- expense date;
- category;
- finite non-negative amount;
- optional description.

Coverage records seller confirmation that expense accounting is complete for a date interval.

A requested Period Profit interval is fully covered only when confirmed coverage spans every calendar day in the request.

## Fail-closed semantics

- missing expense rows do not mean zero;
- empty uncovered period remains unknown;
- empty fully covered period is explicit confirmed 0 ₽ external expense;
- partial coverage stays partial even when some expenses are known;
- invalid dates are rejected;
- boolean amounts are rejected;
- NaN and infinity are rejected;
- missing/invalid repository evidence does not become a clean zero-expense report.

## Seller-facing behavior

Period Profit may show:

- profit before external expenses;
- entered external expenses;
- category breakdown;
- external-expense coverage state;
- observed profit after entered expenses when coverage is partial;
- complete profit after external expenses only when coverage is complete.

The response keeps accounting net-profit claim blocked.

Comparison semantics remain based on the base Period Profit until external-expense coverage is proven for both compared periods.

## Coverage confirmation

`confirm_expense_coverage.py` provides explicit local coverage confirmation.

Coverage confirmation is local accounting evidence only.

It does not authorize or perform Ozon mutation.

## Explicitly not implemented/proven

This package does not prove or automatically infer:

- recurring expense schedules;
- missing seller expenses;
- historical return COGS;
- saleable/restored inventory after returns;
- originating sale-period lineage for returned goods;
- compensation timing across periods;
- taxes/accounting adjustments outside configured policy.

Recurring expenses are therefore included only if represented by explicit dated expense evidence for the relevant period.

## Return COGS boundary

Return COGS candidate evidence remains diagnostic only.

Therefore:

- `historical_cost_basis_confirmed=False`;
- `originating_sale_period_confirmed=False`;
- `saleable_inventory_recovery_confirmed=False`;
- `period_cogs_recovery_confirmed=False`;
- `accounting_cogs_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`.

## Next production gap

The most material unresolved accounting gap is stronger return-related COGS recovery proof.

A future package may only allow COGS reversal if reliable evidence can prove, without inference:

- the original cost basis applicable to the returned unit;
- that the original sale belongs to the relevant accounting period;
- that the returned unit restored saleable inventory value or another accounting-equivalent recovery;
- compensation treatment without double counting.

Until then, candidate recovery must not change profit.

After that, remaining gaps include:

- taxes/accounting adjustments outside configured tax policy;
- any external-expense periods without explicit coverage;
- recurring expense evidence if the seller needs it represented without manual dated rows.

## SHA-bound verification

Entering exact docs-reconciled main:

- `9a29e853727c82abdf75b1992c45c532bd45e3ef`;
- Verify #1050;
- 2161 passed / 0 failed;
- artifact 9894484795;
- digest `sha256:0a864e6e4515eb024f13758d13d944907bcd4a72250cb7e5508e900145cab025`.

Failed intermediate evidence:

- `55d8f189dc170cc524aa8798aea42b1b7ae6251c`: Verify #1054, 2150 passed / 11 failed, artifact 9894680388, digest `sha256:49302f69375d247b9094b7a58f1a16c5671124eb894eef0153edd3dc1276c376`;
- `9f32163739d849dfe3681a9de6358fb64db40100`: Verify #1055, 2150 passed / 11 failed, artifact 9894698643, digest `sha256:e37593e820234269a9230e6be4f8c61fc591d7108f4093201bdb3192e09956d0`;
- `e788e5110109eb678767313278580989b192f689`: Verify #1060, 2160 passed / 1 failed, artifact 9894794990, digest `sha256:af0ffe3ef3fe9ddfce906ac6bbb3a33c10f5ac445f1884705aa3b85e483fb1fc`.

Cancelled intermediate SHAs carry no transferable success evidence.

Final feature:

- `07f9a35eb238280e95b52bc14d18cc6aba735703`;
- Verify #1062;
- 2171 passed / 0 failed;
- artifact 9894853461;
- digest `sha256:9d28a3a5ae753f1215fd042622fd62d7e4985fa96eeba0f2f140318166617298`.

PR integration:

- PR #389;
- synthetic SHA `77dd43cfeb36ebe0066f8747c6c51580083848a6`;
- Verify #1063;
- 2171 passed / 0 failed;
- artifact 9894897854;
- digest `sha256:9111b865c015e95c360ba417c3ef68f82377e82f9e2eddfc7c7e7d8c61ae93a0`.

Squash main:

- `875cc4a783a48eb9a9059b9e2e9ba85316fbdc0d`;
- Verify #1064;
- 2171 passed / 0 failed;
- artifact 9894942156;
- digest `sha256:6ba30eda33b5a1315469e4fbf9253058d932cbc756e634b8996b2f31b2158e53`.

Failed SHA evidence is not transferable.

Decision 036 unchanged.
Decision 037 unchanged.
Decision 038 implemented.
GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.

# AI Assistant Project State

## Current product state

AI Business Assistant

## Product role

Read-only Ozon business analyst and advisor.

The assistant may read seller/business evidence, analyze it, compare periods, explain risks, rank priorities, recommend next steps, and prepare non-executable drafts/checklists.

The assistant must not mutate Ozon business state.

## Current verified checkpoint

Package:

`v1261-v1270: External Operating Expense Coverage`

Goal:

Include explicit seller-recorded operating expenses outside the Ozon accrual stream without treating missing expense evidence as zero.

Immediately preceding verified package:

`v1251-v1260: Return COGS Recovery Evidence`

## Stable verification

Latest exact production main:

`875cc4a783a48eb9a9059b9e2e9ba85316fbdc0d`

GitHub Actions push Verify #1064:

2171 passed / 0 failed.

## Seller-facing accounting progress

Period Profit V2 still uses account-level Ozon accruals as the monetary authority for Ozon money.

Base formula remains:

`period_profit = account_net_accrual - product_cost - configured_tax`

The external-expense layer now reads explicit local seller expense rows and explicit `expense_coverage` intervals.

Evidence semantics:

- missing external expense rows are never interpreted as zero;
- an uncovered empty period remains unknown;
- a fully covered empty period is an explicit confirmed 0 ₽ external expense;
- partial expense evidence may produce only an observed profit-after-entered-expenses view;
- complete coverage over every calendar day permits a complete external-expense adjustment;
- invalid dates, boolean amounts and non-finite amounts fail closed.

Derived external-expense formula:

`profit_after_external_expenses = period_profit - external_expenses`

This subtraction applies only to expenses outside Ozon account net accrual and therefore does not duplicate Ozon advertising, storage, return-operation or other Ozon charges already present in `account_net_accrual`.

## Explicit boundaries

Accounting net-profit claim remains prohibited.

The following are still not fully proven:

- historical COGS basis for returned units;
- saleable-inventory recovery after returns;
- originating sale-period lineage for return COGS reversal;
- compensation timing/accounting across periods;
- taxes or accounting adjustments outside the configured tax policy;
- completeness of seller external-expense evidence unless explicit coverage exists.

Return COGS candidate evidence remains diagnostic only:

- `confirmed_cogs_recovery_amount=0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`.

## Production evidence

Entering exact docs-reconciled main:

- `9a29e853727c82abdf75b1992c45c532bd45e3ef` / Verify #1050 / 2161 passed / 0 failed / artifact 9894484795 / digest `sha256:0a864e6e4515eb024f13758d13d944907bcd4a72250cb7e5508e900145cab025`.

Failed intermediate SHAs remain failed evidence:

- `55d8f189dc170cc524aa8798aea42b1b7ae6251c` / Verify #1054 / 2150 passed / 11 failed / artifact 9894680388 / digest `sha256:49302f69375d247b9094b7a58f1a16c5671124eb894eef0153edd3dc1276c376`;
- `9f32163739d849dfe3681a9de6358fb64db40100` / Verify #1055 / 2150 passed / 11 failed / artifact 9894698643 / digest `sha256:e37593e820234269a9230e6be4f8c61fc591d7108f4093201bdb3192e09956d0`;
- `e788e5110109eb678767313278580989b192f689` / Verify #1060 / 2160 passed / 1 failed / artifact 9894794990 / digest `sha256:af0ffe3ef3fe9ddfce906ac6bbb3a33c10f5ac445f1884705aa3b85e483fb1fc`.

Cancelled intermediate SHAs carry no transferable success evidence.

Final feature:

- `07f9a35eb238280e95b52bc14d18cc6aba735703` / Verify #1062 / 2171 passed / 0 failed / artifact 9894853461 / digest `sha256:9d28a3a5ae753f1215fd042622fd62d7e4985fa96eeba0f2f140318166617298`.

PR integration:

- PR #389 synthetic `77dd43cfeb36ebe0066f8747c6c51580083848a6` / Verify #1063 / 2171 passed / 0 failed / artifact 9894897854 / digest `sha256:9111b865c015e95c360ba417c3ef68f82377e82f9e2eddfc7c7e7d8c61ae93a0`.

Squash main:

- `875cc4a783a48eb9a9059b9e2e9ba85316fbdc0d` / Verify #1064 / 2171 passed / 0 failed / artifact 9894942156 / digest `sha256:6ba30eda33b5a1315469e4fbf9253058d932cbc756e634b8996b2f31b2158e53`.

## Preserved boundaries

- Decision 036 permanent read-only Ozon analyst boundary;
- Decision 037 account-level Ozon monetary authority;
- Decision 038 external operating expense evidence/coverage contract;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- no double subtraction of Ozon expenses;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Remaining path toward accounting net profit

The most material unresolved evidence gap is now return-related COGS recovery proof.

Candidate return evidence exists, but automatic COGS reversal remains blocked until stronger evidence can prove historical cost basis, sale-period lineage and saleable/restored inventory value.

After that, remaining accounting gaps include taxes/adjustments outside the configured policy and any external-expense periods that have not been explicitly covered.

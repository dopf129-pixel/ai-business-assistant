# AI Assistant Project State

## Current product state

AI Business Assistant is a read-only Ozon business analyst and advisor. Ozon business mutations remain prohibited by Decision 036.

## Current verified checkpoint

Package: `v1321-v1330: Return COGS Accounting Readiness`

Exact production main: `ea92d314b81b80878d5127ed261b448b7cf7abd0`

GitHub Actions push Verify #1168: 2238 passed / 0 failed.

## Period Profit accounting boundary

Decision 037 account-level Ozon finance remains the monetary authority.

Base formula remains unchanged:

`period_profit = account_net_accrual - product_cost - configured_tax`

External expense adjustment remains separately evidence-bound under Decision 038.

Return COGS evidence now has an explicit accounting-readiness layer. Readiness requires all of the following to be independently confirmed:

- complete return sample;
- originating sale period;
- historical cost basis;
- saleable inventory recovery;
- explicit originating-sale quantity evidence;
- explicit recovery accounting-period attribution;
- explicit compensation accounting treatment;
- explicit compensation double-count clearance;
- complete accounting-attribution evidence.

## Promoted readiness gates

When the source evidence is explicit and complete:

- `originating_sale_quantity_confirmed=True`;
- `originating_sale_quantity_gate_promoted=True`;
- `recovery_period_attribution_confirmed=True`;
- `compensation_accounting_treatment_confirmed=True`;
- `return_cogs_accounting_readiness_confirmed=True`.

Each missing or ambiguous prerequisite remains fail-closed and appears in `return_cogs_accounting_readiness_blockers`.

## Monetary recovery remains closed

v1321-v1330 does not create or apply a Return COGS amount. Even when readiness is confirmed:

- `period_cogs_recovery_confirmed=False`;
- `accounting_cogs_recovery_confirmed=False`;
- `confirmed_cogs_recovery_amount=0.0`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`;
- `compensation_profit_adjustment_allowed=False`.

This separates accounting readiness from monetary recognition and prevents source evidence from silently changing Period Profit.

## Production verification

No failed production SHA occurred in v1321-v1330.

- feature `137940e12eb9b3671f580b091a26bf45101aee8c` — Verify #1166 — 2238 passed / 0 failed — artifact 9932839687 — digest `sha256:a89bcb223c2f34dbea2e6f47d2b03d45de4bff176bb38c54f1e2883e0d36cd06`;
- PR #401 synthetic `adc169fc389fda629bd0f923f2ddb05400aa8993` — Verify #1167 — 2238 passed / 0 failed — artifact 9933152845 — digest `sha256:a1db974d7671e94e3c86cb1263da1b96342c20661dc1e1e94349cd5e599cbd59`;
- squash main `ea92d314b81b80878d5127ed261b448b7cf7abd0` — Verify #1168 — 2238 passed / 0 failed — artifact 9933178755 — digest `sha256:5a0fc7d1f42b4ac4f23af1fa0a89e9279beea45dac4caf72ccd91f4df9df6021`.

## Preserved boundaries

- Decisions 036-041 remain unchanged;
- Decision 042 records readiness-gate promotion while monetary recovery stays separate;
- no Ozon mutation;
- no Product Decision/Product Task Draft execution;
- no Period Profit formula change;
- no non-zero COGS recovery;
- no compensation inference from operational status absence;
- no accounting-date inference from confirmation provenance;
- `data/users.json` unchanged;
- `externally_verified=False`.

## Next accounting package

Define the monetary Return COGS recognition contract only from candidate-level evidence that already passes accounting readiness. The next package must prove amount construction and period ownership without double-counting Ozon account-level finance, and should continue to stage the amount before enabling any Period Profit adjustment.

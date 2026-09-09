# Period Profit Return COGS blocker stage orchestration

Production basis: `11d552466d5343c2d0eeb05cdada2bbbc02db43d`.

## Decision

Return COGS seller-facing observability now has one explicit read-only stage resolver. It does not calculate, authorize, recognize, commit, or apply money. Its only responsibility is to identify the first fail-closed gate already represented by production evidence.

The stage order is fixed:

1. inventory recovery evidence;
2. accounting attribution / compensation double-count clearance;
3. separate accounting recognition;
4. profit-application authorization;
5. exact-once application commit;
6. final seller-facing application;
7. no blocker after the full chain is applied.

Later evidence must never hide an earlier unresolved gate. A malformed or contradictory downstream record cannot make the resolver skip inventory, accounting attribution, recognition, authorization, or commit.

## Inventory authority

Inventory remains the first presentation gate. A state string is authoritative only when `inventory_recovery_evidence_status == RETURN_INVENTORY_RECOVERY_READY` and the local state is exactly `SALEABLE_RESTORED` or `NON_SALEABLE`.

Therefore:

- `ReturnedToOzon` is not `SALEABLE_RESTORED`;
- non-ready `SALEABLE_RESTORED` remains inventory-blocked;
- non-ready `NON_SALEABLE` remains inventory-blocked;
- ready `NON_SALEABLE` may advance past the inventory presentation gate but does not prove any accounting fact.

## Downstream gates

The resolver consumes only existing booleans and records already emitted by the Return COGS pipeline. It does not infer missing business facts.

`ACCOUNTING_ATTRIBUTION` remains before `ACCOUNTING_RECOGNITION`. Recognition remains before application authorization. Authorization remains before exact-once commit. A commit-ready state is not a committed state.

When durable commit evidence is confirmed but seller-facing application is still not represented as applied, the resolver exposes a distinct `FINAL_APPLICATION` stage. This is an observability state, not permission to repeat a commit or synthesize a financial adjustment.

## Query integration

`PeriodProfitFinalApplicationQueryService` now exposes `return_cogs_blocker_stage` alongside the existing Return COGS evidence and final-application result. The object is explicitly `read_only=True` and `executed=False`.

The final application service remains the only existing component in this path that can recompute seller-facing Period Profit from already committed Return COGS evidence. The stage resolver does not call repositories, Ozon, tax calculation, or commit/application operations.

## Financial invariants

- Ozon remains READ-ONLY.
- `ReturnedToOzon` is candidate evidence only.
- `unknown != zero`.
- No Return COGS amount is derived from returned quantity multiplied by a guessed unit cost.
- Missing accounting, recognition, authorization, and commit facts are not auto-filled.
- Commit readiness is not execution.
- Final application observability does not authorize a repeated commit.
- Seller-facing Period Profit remains `read_only=True` and `executed=False`.

## Regression coverage

Regression tests prove the stage precedence chain and specifically verify that:

- unresolved inventory beats every downstream false gate;
- accounting attribution beats recognition, authorization, and commit;
- recognition beats authorization and commit;
- authorization beats commit;
- commit beats final application;
- committed-but-not-applied evidence produces the final-application stage;
- a fully applied chain produces no blocker;
- ready `NON_SALEABLE` can advance past inventory while non-ready `NON_SALEABLE` cannot;
- invalid evidence fails closed without inventing a financial stage;
- the stage result itself remains read-only and non-executing.

## SHA-bound verification evidence

Code package:

- feature head `9f66d4a530d043ebb950a1a41dfb8553d18e046d` — Verify #1693 passed on the exact feature revision;
- PR #485 synthetic merge `805f845b763c9d75d1a2608bef34a522f7c4625c` — Verify #1694 passed; artifact `verification-805f845b763c9d75d1a2608bef34a522f7c4625c` binds the report to the PR merge revision;
- squash production main `11d552466d5343c2d0eeb05cdada2bbbc02db43d` — Verify #1695 passed on the exact `main` push revision.

Verification evidence is revision-specific and must not be transferred between SHAs.

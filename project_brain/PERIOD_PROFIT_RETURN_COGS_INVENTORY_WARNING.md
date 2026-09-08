# Period Profit Return COGS inventory warning

Production basis: `612778b0be89f15cd70d193d1caaf94ebf422cc8`.

## Decision

A customer return becoming a Return COGS candidate must not make the compact Telegram warning disappear while saleable-inventory recovery is still unproven.

The current FBO Returns API status `ReturnedToOzon` (`На складе Ozon`) is candidate evidence only. It does not prove `SALEABLE_RESTORED` and does not authorize a COGS recovery amount.

Compact Period Profit therefore keeps two unresolved groups visible:

1. customer-return units that do not reach the Return COGS candidate gate (`unresolved_units`);
2. candidate records whose inventory recovery state is not confirmed as `NON_SALEABLE` and whose Period COGS recovery is not yet confirmed.

A candidate explicitly confirmed as `NON_SALEABLE` is not described as an unconfirmed COGS recovery, because no saleable inventory was restored.

## Financial invariants

This is presentation/observability only. It does not change the Period Profit formula and does not create return COGS evidence.

- Ozon remains READ-ONLY.
- `ReturnedToOzon` is not mapped to `SALEABLE_RESTORED`.
- `unknown != zero`.
- No candidate amount is included until the full no-double-counting -> recognition -> authorization -> commit chain succeeds.
- Seller-facing Period Profit remains `read_only=True` and `executed=False`.

## Root cause

After production began recognizing `ReturnedToOzon` as a conservative Return COGS candidate, those rows stopped contributing to `unresolved_units`. The compact Telegram formatter still warned only from `unresolved_units`, so a return blocked by missing inventory-recovery evidence could become invisible even though its COGS recovery remained unconfirmed.

The correction derives the compact unresolved count from both unresolved customer-return units and still-unproven candidate records. It deliberately excludes candidate rows explicitly confirmed `NON_SALEABLE`.

## Regression coverage

Regression tests prove that:

- a `ReturnedToOzon` candidate with no inventory proof remains visible in compact Telegram output;
- a candidate confirmed `NON_SALEABLE` does not produce a false unconfirmed-recovery warning;
- pre-candidate unresolved units and unproven candidate units are both counted without treating financial return operations as return-count authority.

## SHA-bound verification evidence

- feature head `77042b8aa2ecccdac965858e4a20b5541178b6ef` — Verify #1622 passed on exact push SHA;
- actual PR #471 synthetic merge `b21dabbbdc3e674412a2787953d007c8c72be62b` — Verify #1623 passed; artifact `verification-b21dabbbdc3e674412a2787953d007c8c72be62b`;
- squash production main `612778b0be89f15cd70d193d1caaf94ebf422cc8` — Verify #1624 passed.

Verification evidence is SHA-bound and is never transferred between revisions.

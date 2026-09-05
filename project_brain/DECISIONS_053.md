# Decision 053 — Compact Seller-Facing Period Profit Presentation

Date: 2026-09-05

## Decision

Period Profit keeps one canonical financial result but exposes two presentation layers:

- `text`: compact seller-facing Telegram report;
- `details_text`: full diagnostic report preserved for troubleshooting.

The compact report may summarize or omit technical evidence blocks, but it must not alter any monetary value, accounting gate, reconciliation rule, or Ozon read-only boundary.

Sold quantity is displayed only from exact `units_sold` evidence. If unavailable, the UI renders unknown (`—`) rather than zero.

## Rationale

The prior report was operationally correct but too verbose for routine seller decisions. Separating management presentation from diagnostic detail improves readability without weakening evidence requirements.

## Preserved invariants

- account-level Ozon finance remains monetary authority;
- canonical Period Profit formula is unchanged;
- Return COGS remains exact-once and gated;
- unknown monetary or quantity evidence is never inferred as zero;
- no Ozon business mutation is introduced;
- detailed diagnostics remain available separately.

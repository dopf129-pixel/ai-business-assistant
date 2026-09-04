# Decisions 041-045 Supplement

This additive registry restores the Return COGS accounting decisions that are referenced by later checkpoints but are absent from the historical `DECISIONS.md` file. The historical registry is preserved unchanged.

## Decision 041 — Explicit Return COGS Accounting Attribution and Compensation Evidence

**Status:** Accepted.

Return COGS accounting-period attribution and compensation treatment are seller/accounting facts, not operational inferences.

- `return_inventory_recovery_history.confirmed_on` is physical/evidence confirmation only and MUST NOT be used as the accounting recognition date.
- Absence of a compensation marker MUST NOT be interpreted as proof that compensation did not occur.
- Accounting attribution uses explicit, versioned seller evidence keyed by Return COGS identity.
- Missing, malformed, ambiguous, or conflicting evidence remains unknown and fails closed.
- Ozon remains read-only.

## Decision 042 — Return COGS Accounting Readiness Is a Gate, Not Recognition

**Status:** Accepted.

Accounting readiness may be promoted only when all independent evidence gates are confirmed: originating sale period, historical cost basis, saleable inventory recovery, originating-sale quantity, explicit recovery-period attribution, explicit compensation treatment, and double-count clearance.

Readiness does not book money, does not confirm a recovery amount, and does not change Period Profit.

## Decision 043 — Return COGS Monetary Amount Is Staged Evidence

**Status:** Accepted.

A candidate Return COGS recovery amount may be staged only from confirmed historical cost multiplied by explicit return quantity after accounting readiness is confirmed.

- The staged amount is evidence, not a recognized accounting entry.
- Stored/derived candidate amounts must reconcile exactly within the established monetary tolerance.
- Missing monetary evidence is unknown, never zero by inference.
- Period Profit remains unchanged.

## Decision 044 — Period-Bound Recognition Eligibility Requires Exact Coverage

**Status:** Accepted.

Return COGS recognition eligibility requires exact identity coverage across candidates, staged amount evidence, and accounting attribution evidence using `return_id + posting_number + SKU`.

Eligibility additionally requires RUB reconciliation, requested-period match, explicit compensation treatment, and confirmed double-count clearance.

Eligibility is not accounting recognition and cannot change Period Profit.

## Decision 045 — Explicit Accounting Booking Is Required Before Return COGS Is Recognized

**Status:** Accepted.

A Return COGS recovery becomes an accounting-recognized fact only when append-only seller accounting booking evidence exists for every eligible candidate and reconciles exactly with the eligible amount.

Required recognition evidence includes:

- exact `return_id + posting_number + SKU` identity;
- explicit accounting recognition date matching the eligible accounting attribution;
- explicit recognized amount;
- RUB currency;
- explicit recognition state;
- versioned confirmation evidence.

Revocation is append-only and supersedes an earlier recognition record. Missing, conflicting, malformed, mismatched, or revoked evidence fails closed.

Recognition may set `period_cogs_recovery_confirmed`, `accounting_cogs_recovery_confirmed`, and `confirmed_cogs_recovery_amount`, but it still MUST NOT alter Period Profit until a separate explicit application decision and package is completed.

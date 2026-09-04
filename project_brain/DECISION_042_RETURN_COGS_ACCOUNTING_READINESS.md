# Decision 042

Date: 2026-09-04

Topic: Return COGS Accounting Readiness Gate Promotion

## Decision

Independently proven Return COGS source evidence may be promoted into explicit accounting-readiness gates, but readiness is not monetary recognition and must not by itself change Period Profit.

## Rules

- `originating_sale_quantity_confirmed` may become true only from explicit originating-sale quantity evidence;
- `recovery_period_attribution_confirmed` may become true only from explicit accounting-date evidence that belongs to the requested period;
- `compensation_accounting_treatment_confirmed` may become true only when compensation treatment is explicit and double-count clearance is true;
- accounting readiness additionally requires complete return evidence, originating sale period, historical cost basis, saleable inventory recovery and complete accounting-attribution evidence;
- missing, malformed, ambiguous or conflicting evidence keeps readiness blocked;
- readiness blockers must remain explicit and deterministic;
- readiness does not imply `period_cogs_recovery_confirmed` or `accounting_cogs_recovery_confirmed`;
- readiness does not create a non-zero `confirmed_cogs_recovery_amount`;
- readiness does not authorize `profit_adjustment_allowed` or `automatic_recovery_allowed`;
- compensation presence without explicit double-count clearance cannot pass the compensation gate;
- Period Profit formula remains unchanged;
- Decision 036 read-only Ozon boundary and Decisions 037-041 evidence/accounting ownership remain unchanged.

## Reason

The preceding packages established independent facts but deliberately kept their accounting gates false. Once those facts are all explicit, the system needs a deterministic way to say that a candidate set is accounting-ready without prematurely recognizing money. Separating readiness from monetary recovery preserves fail-closed behavior and prevents evidence completeness from silently changing seller-facing profit.

Status: Implemented

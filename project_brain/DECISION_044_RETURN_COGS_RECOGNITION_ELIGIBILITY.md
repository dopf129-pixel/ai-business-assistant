# Decision 044

Date: 2026-09-04

Topic: Return COGS Recognition Eligibility

## Decision

An accounting-ready staged Return COGS amount may become recognition-eligible only when its monetary records and accounting-attribution records cover the exact same candidate identities and all requested-period and compensation no-double-count conditions are explicit. Recognition eligibility is not accounting recognition and must not by itself change Period Profit.

## Rules

- accounting readiness must already be confirmed;
- staged recovery amount evidence must already be confirmed;
- staged currency must be RUB and the staged amount must be finite and non-negative;
- candidate, staged-amount and accounting-attribution record sets must match exactly on `return_id + posting_number + SKU`;
- duplicate or missing identities block eligibility;
- every staged amount record must be ready and its aggregate must reconcile to the staged amount within 0.01 RUB;
- every accounting-attribution record must be ready and explicitly match the requested period;
- compensation state must be explicit;
- compensation double-count clearance must be explicitly true;
- missing, malformed, conflicting or unmatched evidence blocks eligibility;
- eligibility may expose `return_cogs_recognition_eligible_amount`, but does not set `period_cogs_recovery_confirmed` or `accounting_cogs_recovery_confirmed`;
- eligibility does not set a non-zero `confirmed_cogs_recovery_amount`;
- eligibility does not authorize `profit_adjustment_allowed`, `automatic_recovery_allowed`, or compensation profit adjustment;
- accounting recognition requires a later explicit evidence contract;
- Decision 036 and Decisions 037-043 remain unchanged.

## Reason

A staged monetary amount is not sufficient by itself to prove that every unit and every ruble belongs to the selected accounting period or is safe from compensation double counting. Exact cross-record identity coverage and explicit period/compensation evidence are required before the amount can be considered recognition-eligible. Keeping eligibility separate from recognition preserves fail-closed accounting semantics.

Status: Implemented

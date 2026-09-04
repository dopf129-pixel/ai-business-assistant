# Decision 041

Date: 2026-09-04

Topic: Explicit Return COGS Accounting Attribution Evidence

## Decision

Return COGS accounting recognition timing and compensation treatment must be stored as explicit return-level seller accounting evidence. Operational return state, inventory-recovery confirmation time, missing compensation markers, stock observations, or monetary heuristics must not be promoted into accounting facts.

## Persistence contract

A separate append-only `return_cogs_accounting_attribution_history` table stores:

- exact `return_id`;
- exact `posting_number`;
- exact `SKU`;
- dedicated `recovery_accounting_date`;
- explicit compensation state;
- explicit boolean `compensation_double_count_clear`;
- `confirmed_on` provenance date;
- source.

Allowed compensation states are:

- `NO_COMPENSATION_CONFIRMED`;
- `COMPENSATION_PRESENT`.

## Rules

- `confirmed_on` is evidence-confirmation provenance only and never establishes the accounting recognition date;
- absence of an operational compensation marker is not evidence of no compensation;
- `NO_COMPENSATION_CONFIRMED` requires explicit double-count clearance;
- `COMPENSATION_PRESENT` may be recorded while double-count clearance remains false;
- duplicate `return_id + confirmed_on` versions are rejected rather than overwritten;
- all versions for one return must preserve posting-number + SKU identity; identity drift makes the evidence conflicting and unconfirmed;
- malformed or missing accounting dates remain unknown;
- malformed or missing compensation treatment remains unknown;
- repository/service failures fail closed;
- source-evidence completeness does not itself promote the existing Return COGS accounting gates;
- v1311-v1320 keeps `recovery_period_attribution_confirmed=False`, `compensation_accounting_treatment_confirmed=False`, `period_cogs_recovery_confirmed=False`, `accounting_cogs_recovery_confirmed=False`, `confirmed_cogs_recovery_amount=0.0`, `profit_adjustment_allowed=False`, and `automatic_recovery_allowed=False`;
- Period Profit formula remains unchanged;
- Decision 036 read-only Ozon boundary and Decisions 037-040 accounting/evidence ownership remain unchanged.

## Reason

Inventory recovery can be physically confirmed on one date while accounting recognition belongs to another period. Likewise, a missing operational compensation flag cannot prove that compensation did not occur or that its economic effect is absent from account-level finance. A dedicated append-only accounting evidence contract prevents timing inference and compensation double counting before any future COGS recovery is considered.

Status: Implemented

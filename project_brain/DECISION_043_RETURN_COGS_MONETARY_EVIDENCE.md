# Decision 043

Date: 2026-09-04

Topic: Staged Return COGS Monetary Evidence

## Decision

A Return COGS monetary amount may be computed as read-only source evidence after accounting readiness is confirmed, but the staged amount is not an accounting-recognized recovery and must not by itself change Period Profit.

## Rules

- the candidate set must already satisfy `return_cogs_accounting_readiness_confirmed=True`;
- each candidate requires exact return identity, explicit positive quantity and explicit effective-dated historical unit cost;
- staged candidate amount is `historical_cost_per_unit * return_quantity`;
- the derived candidate amount must reconcile to existing `candidate_value_at_historical_cost` within 0.01 RUB;
- every candidate must pass before an aggregate staged amount is confirmed;
- explicit historical cost zero is a valid zero-value fact;
- missing, malformed, boolean, negative, non-finite or inconsistent monetary evidence remains unknown and blocks the aggregate amount;
- staged monetary evidence does not set `period_cogs_recovery_confirmed` or `accounting_cogs_recovery_confirmed`;
- staged monetary evidence does not set a non-zero `confirmed_cogs_recovery_amount`;
- staged monetary evidence does not authorize `profit_adjustment_allowed`, `automatic_recovery_allowed`, or compensation profit adjustment;
- recognition ownership and application to Period Profit require a separate explicit contract;
- Decision 036 and Decisions 037-042 remain unchanged.

## Reason

Accounting readiness proves that the source facts required for a possible COGS recovery are coherent, but a monetary figure still needs its own evidence contract. Separating staged amount evidence from recognition prevents a derived number from silently becoming an accounting entry and preserves account-level Ozon no-double-counting boundaries.

Status: Implemented

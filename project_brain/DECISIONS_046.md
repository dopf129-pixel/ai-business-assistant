# Decision 046 Supplement

Date: 2026-09-04

## Decision 046 — Return COGS Period Profit Application Eligibility Requires Explicit Monetary-Authority Exclusion

**Status:** Accepted.

An accounting-recognized Return COGS recovery is not automatically eligible to adjust seller-facing Period Profit.

Because Decision 037 makes account-level Ozon finance the monetary authority, application eligibility requires explicit seller/accounting evidence that the exact recognized Return COGS recovery is excluded from account-level `net_accrual`. Absence of an inclusion marker is not proof of exclusion.

The application-eligibility contract additionally requires:

- exact accounting-recognition history version;
- exact `return_id + posting_number + SKU` identity;
- active, non-revoked recognition;
- exact recognized accounting period and selected-period reconciliation;
- exact recognized and authorized amount reconciliation within the established monetary tolerance;
- RUB currency;
- explicit compensation non-overlap;
- append-only explicit application authorization;
- explicit no-repeat state for the exact recognition version.

Application authorization is a separate accounting evidence layer from recognition. Authorization can be revoked only by a later append-only version. Once `PROFIT_APPLICATION_APPLIED` evidence exists for an exact recognition version, that version must not become eligible again.

Missing, malformed, conflicting, mismatched, revoked, already-applied, or monetary-authority-ambiguous evidence fails closed.

### Deliberate non-decision in v1361-v1370

Decision 046 does not authorize changing the Period Profit formula and does not define the final tax treatment or atomic application semantics.

Even when application eligibility is confirmed:

- `return_cogs_profit_applied=False`;
- `return_cogs_profit_application_amount=None`;
- `profit_adjustment_allowed=False`;
- `automatic_recovery_allowed=False`.

Canonical Period Profit remains:

`period_profit = account_net_accrual - product_cost - configured_tax`

A later package must separately prove actual application ownership, exact-once consumption, active-recognition revalidation, and tax semantics before any seller-facing profit adjustment is permitted.

Ozon business state remains permanently read-only.

# Period Profit Return COGS status authority

Production basis: `e86bc01eadcb2bcc3356742198ee98e97ee96cf3`.

## Current Returns API status

Observed complete FBO Returns API evidence for 2026-05-03 through 2026-08-31 uses `ReturnedToOzon` (`На складе Ozon`) for customer returns that have reached Ozon. The previous Return COGS candidate gate expected `ArrivedAtReturnPlace`, so current customer returns could remain unresolved before sale-lineage, effective-cost and inventory-recovery gates were evaluated.

Production now treats `ReturnedToOzon` only as a Return COGS **candidate** status for `ClientReturn` / `FullReturn` records. This status is not evidence that inventory is saleable or that COGS has been recovered.

## Mandatory independent inventory evidence

`ReturnedToOzon` must never be converted directly into a profit adjustment. Saleable inventory recovery remains a separate local evidence gate. A candidate must still have exact recovery evidence for the same return identity, posting, SKU and quantity, with recovery state `SALEABLE_RESTORED`. Missing, conflicting, non-saleable or quantity-mismatched recovery evidence fails closed.

Compensated returns remain handled separately and are not silently converted into inventory COGS recovery.

## Accounting invariants

Return COGS still requires the complete chain: no-double-counting evidence, complete return sample, originating-sale lineage, seller-confirmed effective originating-sale cost, originating-sale quantity, saleable inventory recovery, recovery-period attribution, compensation accounting treatment and double-count clearance, accounting attribution/readiness, recognition, authorization and commit.

Until all required gates are confirmed, `confirmed_cogs_recovery_amount` remains zero, `profit_adjustment_allowed` remains false, and seller-facing Period Profit remains `read_only=True`, `executed=False`.

Ozon remains READ-ONLY.

## Regression coverage

The production regression proves that current `ReturnedToOzon` evidence reaches the conservative downstream gates when independent saleable-recovery evidence exists. A legacy `ArrivedAtReturnPlace` value is not silently accepted as current authority and remains unresolved. Effective-cost tests continue proving that mutable current cost is not originating-sale historical authority.

## SHA-bound verification

- PR #469 actual synthetic merge: `7d16b89dae079d43f5d7c74512daca97633d7f4c`; Verify #1614 passed with 2384 tests; artifact `verification-7d16b89dae079d43f5d7c74512daca97633d7f4c`.
- production squash main: `e86bc01eadcb2bcc3356742198ee98e97ee96cf3`; Verify #1615 passed.

Verification evidence is SHA-bound and is never transferred between revisions.

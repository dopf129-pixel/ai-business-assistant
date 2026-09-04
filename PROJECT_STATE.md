# AI Assistant Project State

## Current product state

AI Business Assistant remains a read-only Ozon business analyst and advisor. Ozon business mutations remain prohibited.

## Current verified checkpoint

Package: `v1381-v1390: Final Period Profit Application`

Exact production main: `767b3e99d4439d1cbbe7b441a19914a366e62e22`

Verify #1235: success.

Artifact: `9940791251`.

Digest: `sha256:c9f3a9e84c37cb9792dec169d3ca50632784d54ecdd9837b4c891f1b6d1d4b9b`.

## Period Profit is seller-facing complete

The read-only seller-facing Period Profit path now consumes durable committed Return COGS when, and only when, the full accounting chain is still valid:

`evidence -> readiness -> staged amount -> recognition eligibility -> accounting recognition -> profit application eligibility -> exact-once commit -> final Period Profit application`

The final calculation preserves account-level Ozon `net_accrual` as monetary authority. A committed Return COGS amount is added as a separately proven recovery only after explicit exclusion/no-double-count evidence and exact recognition/authorization/commit reconciliation.

Repeated queries are idempotent: every query starts from the current account-level summary and reads the same append-only exact-once commit. The committed amount is not accumulated again.

If no valid commit exists, Return COGS is not applied and the adjustment amount remains `None`; missing evidence is never converted to zero.

## Tax semantics

Configured tax is now evaluated through `TaxService` for all supported Period Profit modes:

- `NONE`: no tax;
- `USN_INCOME`: tax remains based on revenue, so committed Return COGS changes profit but not the revenue tax base;
- `USN_INCOME_MINUS_EXPENSES`: tax is recalculated from pre-tax profit after committed Return COGS recovery, while the configured minimum tax on revenue is still enforced.

The final seller-facing calculation therefore uses account `net_accrual`, product cost, any exact committed Return COGS recovery, and the configured tax policy without double counting.

## Telegram/runtime boundary

The production factory returns the final Period Profit query layer. After final Return COGS application it rebuilds coverage, comparison, external-expense observation and response text, so the Telegram Period Profit route receives the final adjusted seller-facing profit.

The whole path remains read-only: `read_only=True`, `executed=False`; no Ozon mutation or automatic business execution is introduced.

## Verification lifecycle

Failed precursor, permanently failed evidence:

- `f6e9d9af0e93dec0f9d425b6666f99f2d736d0ca` — Verify #1230 failed; later success is not transferred to this SHA.

Successful lifecycle:

- feature head `986d9ffed2b348890a57bac37362388d08be8780` — Verify #1233 succeeded; artifact `9940720378`, digest `sha256:03e7d16f62eee2af88130b68f09952e4549098eff7f086bd11f69c75a943fe71`;
- PR #413 synthetic merge `8ac09b60672bd4f8823547d542f274a4cf609d13` — Verify #1234 succeeded; artifact `9940750283`, digest `sha256:730d36be4d902331838213dc6464a5ca7a3c7b22aa2eeb2d422c4af40fde6697`;
- squash production main `767b3e99d4439d1cbbe7b441a19914a366e62e22` — Verify #1235 succeeded; artifact `9940791251`, digest `sha256:c9f3a9e84c37cb9792dec169d3ca50632784d54ecdd9837b4c891f1b6d1d4b9b`.

## Preserved boundaries

- account-level Ozon finance remains the monetary authority;
- no Ozon mutation;
- no compensation double counting;
- exact-once Return COGS commitment remains append-only;
- active recognition/application eligibility remains required at read time;
- unknown money remains `None`, not zero;
- `externally_verified=False`.

## Next product work

Period Profit itself is ready for user validation in Telegram. Further work can focus on observed production data/UX issues found during that validation rather than another prerequisite accounting gate.

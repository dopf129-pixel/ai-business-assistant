# Current Checkpoint — v1381-v1390

Date: 2026-09-04

## Package

`v1381-v1390: Final Period Profit Application`

## Verified production SHA

`767b3e99d4439d1cbbe7b441a19914a366e62e22`

Verify #1235 succeeded with SHA-bound artifact `9940791251`.

## What is now complete

Seller-facing Period Profit can consume an already durable exact-once Return COGS commit when the recognition and application-eligibility chain still validates the same identity/version/period/amount.

The query is read-only and idempotent. It recalculates from account-level Ozon `net_accrual` on each request and does not accumulate a committed recovery across repeated queries.

Configured tax now has explicit Period Profit semantics for `NONE`, `USN_INCOME`, and `USN_INCOME_MINUS_EXPENSES`. The latter also enforces minimum revenue tax.

The final query rebuilds comparison, coverage, external-expense observation and seller-facing response text after Return COGS application, making the final result available to the existing Telegram runtime.

## Safety/accounting invariants

- Ozon remains read-only;
- account-level `net_accrual` remains monetary authority;
- exact exclusion/no-double-count proof remains mandatory before Return COGS application;
- durable exact-once commit remains mandatory;
- active recognition and application eligibility are revalidated at query time;
- missing/uncommitted monetary evidence remains `None`, not zero;
- compensation double counting remains prohibited;
- automatic business execution remains disabled.

## Verification lifecycle

- failed precursor `f6e9d9af0e93dec0f9d425b6666f99f2d736d0ca` — Verify #1230 failed permanently;
- feature `986d9ffed2b348890a57bac37362388d08be8780` — Verify #1233 succeeded;
- PR #413 synthetic `8ac09b60672bd4f8823547d542f274a4cf609d13` — Verify #1234 succeeded;
- production main `767b3e99d4439d1cbbe7b441a19914a366e62e22` — Verify #1235 succeeded.

## Next validation

User validation should now be performed through the production Telegram Period Profit flow after `git pull`. Any next package should respond to observed runtime/data/UX findings rather than add another prerequisite accounting stage.

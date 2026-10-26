# Exact-head CI regression fix — 25.10.2026

## Finding

The first exact-head runs for PR #714–#716 found the same three test failures on Windows and Linux:

1. Two historical-SKU identity cases called `_product_from_current_cost_row` after B04 had removed that helper to prevent current cost from filling historical COGS. The caller uses the row only to recover `product_id` / `offer_id`; the identity parser had been removed along with the cost fallback.
2. The compact report test still expected whole-ruble strings, although C01 intentionally formats amounts with two decimal places.

The failed heads and runs were #714 `21826e59330dce708388092fedb44ce241d4e8ca` / `40181793806`, #715 `0ee67ced202a82ea0622cf36dfd3bf723fb8d3dd` / `40181869351`, and #716 `24a9d8c2fad09b8c4543c5f33bfe23c578ade183` / `40181908157`. Each reported the same three failures while the remaining suite passed. These runs are evidence of a defect, not accepted verification.

## Correction

- Added a dedicated `_seller_cost_identity_from_row` projection to the identity service. It validates the legacy row and returns only product and offer identity; it never returns or applies `cost_price`. Date-effective historical cost remains authoritative for COGS.
- Updated compact report assertions to expect the approved two-decimal money format.
- Existing related-SKU resolution, ambiguity/fail-closed and end-to-end tax regressions cover the corrected paths. Every changed exact head must complete a fresh Windows/Linux full CI and Docker smoke before PRs are considered ready.

## Verification attempts

- In-memory Python AST parsing of both changed Python files succeeded.
- `git diff --check` exited successfully. Git printed access warnings for two existing ignored D06 pytest scratch directories; no scratch files were staged.
- A local focused pytest attempt using the main checkout's venv produced no output for more than 90 seconds and was interrupted. It is not counted as passed. The worktree has no local venv, and system Python has no pytest. Use exact-head GitHub CI as the authoritative regression check.

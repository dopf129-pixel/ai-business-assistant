# CURRENT_CHECKPOINT_V1201_V1210

Date: 2026-09-03

## Period Profit Data Completeness Integrity

Production package:

`v1201-v1210: Period Profit Data Completeness Integrity`

Goal:

Prevent Period Profit from returning plausible-looking zero financials when persisted products are present but represented as SQLite tuples, and make return-record counts pagination-aware.

## Live issue reproduced from seller output

Observed Telegram output:

- revenue: 0.00 ₽;
- net accrual: 0.00 ₽;
- all Ozon fee components: 0.00 ₽;
- product cost: 0.00 ₽;
- tax: 0.00 ₽;
- profit: 0.00 ₽;
- returns observed: exactly 500.

Those values were not reliable business evidence.

## Root causes

### Product data

`ProductService.load_products()` returns rows from SQLite as:

`(id, offer_id, sku)`

Period Profit previously skipped every non-dict row, leaving zero usable products and then returning a successful zero summary.

### Return evidence

`PeriodProfitReturnEvidenceService` previously requested only one Returns API page with `limit=500` and did not follow `has_next`.

Therefore exactly 500 could be merely a first-page cap.

## Verified behavior

- SQLite product tuples normalize into Period Profit product records;
- existing dict product inputs remain supported;
- no usable products => explicit `PERIOD_PROFIT_PRODUCTS_UNAVAILABLE`;
- zero products can no longer produce a successful 0.00 ₽ summary;
- Returns evidence paginates via `has_next` and `last_id`;
- pagination is bounded to 10 pages;
- complete counts are marked exact;
- incomplete counts are marked non-exact;
- partial counts are displayed as `как минимум N`;
- later-page failure does not turn partial evidence into an exact total;
- return evidence remains read-only/non-financial.

## Product boundary

Decision 036 remains active and unchanged.

No Ozon mutation, business execution, return-cost extrapolation or finance formula change is introduced.

## SHA-bound verification

- entering exact main `5e8e74a78e2c5aa41ed59378c27a0f1ed7b55397`: Verify #930, 2101 passed / 0 failed, artifact 9885946944, digest `sha256:9d4245aa4460358cadfb38a9887dd8bacf212394a995182bd1afd55754c6829b`;
- failed `e3d8b2ed1600e3759135bda4f62865ba38a43ae9`: Verify #935, 2103 passed / 2 failed, artifact 9886500028, digest `sha256:3d92acbe35ea2c4aab44beed55707f6edf0667e8c08376db82993617fd51dfad`;
- failed `49c02ae1790b7d395794932e7ac4fa95cbac1644`: Verify #936, 2109 passed / 2 failed, artifact 9886515012, digest `sha256:179b93cff72ed7316f5aed922b25de95a84f2a3447b09d67b956d237a2074345`;
- final feature `16c53622612b72bce2aa43fd97d5ff66d47466c3`: Verify #937, 2111 passed / 0 failed, artifact 9886550033, digest `sha256:cd5485dd1d5c8b1dd49355f1de14795445055b11e6127d2ae4fe4010fb55defb`;
- PR #377 synthetic `f1593267f67339f2dd68d235056cdbc69960160a`: Verify #938, 2111 passed / 0 failed, artifact 9886596735, digest `sha256:6a1599d927da9f77e928ed321e0de92fa14b8b4bd938974e7199e107da9e8d98`;
- squash main `7b2b570278c9cc71f3eb6dbb23b5554d41de07f7`: Verify #939, 2111 passed / 0 failed, artifact 9886631604, digest `sha256:51ab9910779fa0141662aafc5e90738299ef13b3f0ee95d25b25a034fcc358ad`.

Failed SHA evidence is not transferable.

## Next validation

After local `git pull origin main` and Telegram bot restart, rerun the same Period Profit request.

Expected qualitative change:

- seller financials should no longer be zero merely because products came from SQLite tuples;
- if products truly cannot be resolved, the bot should fail explicitly instead of showing 0.00 ₽;
- return count should exceed 500 when more pages exist, or be marked as a lower bound if evidence is incomplete.

GitHub Actions evidence is project CI evidence only.
`externally_verified=False`.
`data/users.json` unchanged.

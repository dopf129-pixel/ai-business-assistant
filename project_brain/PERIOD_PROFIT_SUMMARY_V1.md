# Period Profit Summary v1

## Goal

Answer the business question: how much profit was earned over a selected date range.

The service aggregates existing daily Ozon finance accruals by product and subtracts product cost and configured tax.

## v1 formula

`profit = net_accrual - product_cost - tax`

where tax is currently calculated from gross sales using the configured rate supplied to the service.

## Explicit completeness boundary

v1 deliberately reports:

- `returns_included=False`;
- `advertising_included=False`;
- `storage_included=False`.

Therefore the result is a scoped operational profit estimate, not accounting net income. Missing product cost or missing daily finance data blocks the calculation instead of inventing values.

## Safety

Read-only business analytics. No Product Decision mutation, Ozon mutation, Action Executor, or automatic execution is introduced.

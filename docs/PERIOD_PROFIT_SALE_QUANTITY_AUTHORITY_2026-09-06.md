# Period Profit sale quantity authority — 2026-09-06

## May control evidence

For 2026-05-01 through 2026-05-31 the official Ozon accrual workbook contains 1,632 `Продажи / Выручка` rows but quantity 1,635. One exact row, accrual ID `0131043464-0056-7`, SKU `3921245627`, carries quantity 4. The previous Period Profit path counted one posting product as one sold unit, so it reported 1,632 units and 34,272 RUB COGS instead of 1,635 units and 34,335 RUB COGS at configured cost 21 RUB/unit.

The by-day finance API remains the monetary authority, but its posting product schema does not expose quantity. Therefore row/product count is not a safe COGS quantity authority.

## Production rule

Standard sale money remains the signed finance `sale_amount`. Standard sale identity remains positive sale finance evidence. Quantity is now reconciled separately by exact `posting_number + SKU` against read-only Ozon quantity evidence:

1. primary source: `/v1/finance/realization/posting`, using `delivery_commission.quantity`;
2. exact fallback only when the realization row is absent: FBO or FBS posting detail product quantity;
3. missing, conflicting, duplicate, malformed or unresolved quantity evidence fails closed rather than silently assuming one unit.

Return quantities and return COGS are not mixed into standard positive-sale COGS. Existing return authorization / no-double-counting / commit gates remain unchanged. Account-level net accrual and configured tax remain unchanged. Ozon is strictly read-only.

## Expected May control

Using the official May accrual workbook:

- revenue: 175,577.41 RUB;
- standard sold units: 1,635;
- account net accrual: -23,772.98 RUB;
- standard COGS at 21 RUB/unit: 34,335 RUB;
- configured 6% tax: 10,534.64 RUB;
- profit before any separately authorized return-COGS restoration: -68,642.62 RUB, displayed as -68,643 RUB;
- margin: about -39.10%.

The previous 1,632-unit / 34,272 RUB COGS result understated standard COGS by 63 RUB.

## Verification

The first feature SHA `49dbf4144ffa344be87fef06a84cbbc1dfe7603a` failed Verify #1511 only because the factory test double did not accept the new constructor keyword. It remains failed and is not release evidence.

The corrected feature head is `abf39b863dcc843f0cd731acc01cc94964964af1`; Verify #1512 passed the full suite. Final release evidence is recorded after the full PR / main / docs lifecycle completes.

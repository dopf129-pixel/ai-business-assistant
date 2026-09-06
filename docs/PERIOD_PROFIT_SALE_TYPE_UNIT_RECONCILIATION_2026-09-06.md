# Period Profit June reversal reconciliation — 2026-09-06

## Corrected control evidence

For 2026-06-01 through 2026-06-30, the official Ozon accrual report contains 4,931 rows classified as `Продажи / Выручка`, but those rows are not 4,931 independent positive sales.

Exact inspection of the official workbook shows:

- 4,930 `Продажи / Выручка` rows have positive revenue;
- 1 `Продажи / Выручка` row is a negative reversal on 2026-06-19;
- the reversal belongs to accrual ID `49885639-0254-1`, SKU `3921245627`, and has seller price `-100.00` and revenue amount `-67.62`;
- the same accrual ID also contains the matching positive sale with seller price `100.00` and revenue amount `67.62`, plus corresponding reversal service rows.

Therefore the earlier interpretation that 4,931 revenue rows meant 4,931 standard sold units was incorrect. The negative reversal must not consume a second unit of COGS.

## Canonical sold-unit rule

Period Profit keeps the previously verified standard-sale rule:

- signed `sale_amount` remains the seller-revenue monetary authority;
- `sale_amount > 0` creates one standard sold unit and one unit of standard COGS;
- `sale_amount <= 0` does not create standard positive-sale COGS;
- returns and reversals remain separate from standard sale COGS and may restore return COGS only through the existing authorization / no-double-counting / commit gates.

This preserves the distinction between money movements and inventory-cost recognition. A negative cancellation/reversal can reduce signed revenue without representing another physical unit sold.

Ozon remains strictly read-only. Account-level net accrual authority, configured tax, return COGS gates, and Telegram output shape are unchanged.

## June control result

The correct Period Profit control for 2026-06-01 through 2026-06-30 is therefore:

- revenue: 486,122.75 RUB;
- standard sold units: 4,930;
- account net accrual: 126,958.65 RUB;
- standard COGS at 21 RUB/unit: 103,530 RUB;
- configured 6% tax: 29,167.37 RUB;
- profit before any separately authorized return-COGS restoration: -5,738.72 RUB, displayed as -5,739 RUB.

The bot output of 4,930 units / 103,530 RUB COGS was correct. The unchanged output after the previous deployment exposed the mistaken control interpretation before it could change production economics.

## Corrective production package

The temporary explicit-revenue override introduced in PR #447 has been removed. It could have promoted non-positive revenue rows to standard sold units if accrual-type labels matched, which would be unsafe for reversal rows such as the June 19 control case.

Regression coverage now includes the exact June pattern: a +100 sale and -100 reversal with matching +67.62 / -67.62 account amounts must net money to zero while consuming standard COGS exactly once. A standalone negative reversal must consume zero standard-sale COGS.

Verified production evidence:

- corrective feature head: `d27f6916f1382bc54f041810c4d3a72bc7c4f41d`; Verify #1500 SUCCESS;
- PR #449 synthetic merge: `2ad8a8b3b927b63116c56b07786fc17ec435673d`; Verify #1501 SUCCESS;
- corrective production main: `6cc8103f8b1040a437d15897acf750c8c58bb410`; Verify #1502 SUCCESS.

The earlier 4,931-unit expectation and 103,551 RUB COGS expectation are superseded by this corrected reconciliation.

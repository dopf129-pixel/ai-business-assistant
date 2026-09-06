# Period Profit return status-period reconciliation — 2026-09-07

## Scope

This reconciliation resolves the July 2026 discrepancy between the compact Period Profit return warning and the official Ozon accrual report. Ozon access remains strictly READ-ONLY.

The investigated period is `2026-07-01` through `2026-07-31` inclusive.

## Proven source semantics

Period Profit return evidence is loaded from Ozon `/v1/returns/list`. The request period is applied to `visual_status_change_moment`, so a record belongs to the selected return-evidence period when its return visual status changes in that period.

This is not the same accounting axis as the official accrual report, whose `Дата начисления` determines the financial accrual period.

Therefore a Returns API record count, recovery candidate count, or unresolved recovery count must not be interpreted as the number of financial `Возврат выручки` accrual rows in the same calendar period.

## July official evidence

The official July accrual report contains exactly two rows with:

- `Группа услуг = Возвраты`;
- `Тип начисления = Возврат выручки`.

They are:

1. `0142584879-0342-1`, accrual date `2026-07-12`;
2. `43509459-1183-1`, accrual date `2026-07-21`.

The separately supplied Ozon returns report contains nine records whose status date is in July 2026. Most are delivery-failure returns and the set does not equal the two July financial revenue-reversal rows.

## Decisive cross-period record

Posting `66486812-0506-1` proves the accounting-layer difference directly:

- order processing date: `2026-05-16`;
- return date: `2026-05-21`;
- official financial `Возврат выручки` accrual date: `2026-05-21`;
- seller-price reversal: `-78 RUB` in May return financial components;
- Returns report visual-status date: `2026-07-10`;
- return reason: `Покупатель передумал`.

Thus this single return belongs to May on the financial-accrual axis and to July on the Returns API status-change axis. Comparing July Returns API/recovery counts directly with July `Возврат выручки` rows is therefore semantically invalid.

## Production correction

No Period Profit monetary formula or Return COGS gate was changed.

The production correction only clarifies the compact Telegram warning. An unresolved recovery warning now states that it describes Returns API records whose status changed in the selected period and explicitly says that the number is not the count of financial `Возврат выручки` rows.

Preserved contracts:

- account-level Ozon finance remains the seller-facing money authority;
- `period_profit = account_net_accrual + exact_committed_return_cogs_if_valid - product_cost - configured_tax`;
- `unknown != zero`;
- Return COGS still requires recognition, authorization, commit, and no-double-counting evidence;
- Ozon remains READ-ONLY;
- seller-facing result remains `read_only=True`, `executed=False`.

## Runtime verification evidence

- exact feature head `971c37b298687cb379a06d2c7af33e9d76eadd29`: Verify #1522 — SUCCESS;
- PR #453 actual synthetic-merge lifecycle: Verify #1523 — SUCCESS; PR synthetic merge SHA `762ad7be05a440e0e9e92634a3c2c969450f3025`;
- squash-merged production main `a3be2b3e8289fecab7542d700a83ef6eaf781ba9`: Verify #1524 — SUCCESS.

Documentation reconciliation starts from that exact verified production main. Failed SHA evidence is not carried between revisions.

## May control-period checkpoint

The official May accrual report was also inspected as the next control period.

Confirmed account-level facts:

- account net accrual: `-23772.98 RUB`;
- positive sale components before returns: `175905.41 RUB`;
- May return sale components: `-328.00 RUB`;
- signed canonical revenue: `175577.41 RUB`;
- sold quantity: `1635` units;
- SKU `3921245627`: `1560` positive sold units;
- historical SKU `3398133813`: `75` positive sold units.

A canonical May Period Profit is intentionally not asserted yet because the repository contains no confirmed historical cost value for SKU `3398133813`. Its 75 units remain unknown rather than being silently assigned the current SKU cost. This preserves the project rule `unknown != zero` and avoids an unsupported COGS assumption.

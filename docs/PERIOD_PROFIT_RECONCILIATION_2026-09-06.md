# Period Profit reconciliation — 2026-09-06

## Scope

Control period: `2026-08-09` through `2026-08-31` inclusive.

This reconciliation compares the seller-facing Period Profit calculation with official Ozon reports supplied for the same account and period. Ozon access remains strictly READ-ONLY.

## Official control totals

The official Ozon accrual report for the control period reconciles to:

- all accrual rows / account net accrual: `141707.34 RUB`;
- `Выручка`: `4072` positive sale rows, `286096.92 RUB`;
- `Возврат выручки`: `1` negative row, `-61.03 RUB`;
- `Баллы за скидки`: `85882.82 RUB`, product quantity `0`;
- `Программы партнёров`: `2410.22 RUB`, product quantity `0`.

Signed revenue reconciliation:

```text
286096.92 + 85882.82 + 2410.22 - 61.03 = 374328.93 RUB
```

That total matches the historical Period Profit `sale_amount` result to display rounding. It does not support replacing `sale_amount` with `seller_price`.

## Proven defect

Before the fix, `FinanceService._process_posting` incremented `sales_count` for every product row in every `POSTING` accrual. This treated zero-quantity financial rows such as discount points / partner-program accruals, and negative return rows, as standard sold units.

For the control period the bot reported `4811` sold units while the official accrual report contains `4072` positive sale events. With configured unit cost `21 RUB`, this produced:

```text
4811 * 21 = 101031 RUB COGS
4072 * 21 = 85512 RUB standard-sale COGS
COGS overstatement = 15519 RUB
```

A return is not converted into a normal negative COGS adjustment here. Return COGS restoration remains governed by its separate recognition, authorization, commit, and no-double-counting gates.

## Production correction

Production main SHA: `2eaaaa531f8e9be2e01d03aebafa0b9eadc3b203`.

The correction is intentionally narrow:

- `PeriodProfitOzonClient` validates and preserves signed `commission.sale_amount` instead of overwriting it with `seller_price`;
- `seller_price`, `sale_price`, `bonus`, and `coinvestment` remain diagnostic fields only;
- `FinanceService` increments `sales_count` only when `sale_amount > 0`;
- signed `gross_sales` still includes zero, negative, return, and correction effects as supplied by Ozon;
- missing/invalid Period Profit money fails closed in the strict Period Profit finance wrapper;
- no Ozon mutation path was added;
- Telegram diagnostics remain internal;
- seller-facing result remains `read_only=True`, `executed=False`.

## Verification evidence

- exact feature head `dd1305c662ab2f9030952d87569fa93ad212160c`: Verify #1414 — SUCCESS;
- PR #437 synthetic merge `a02ee8b33bda10e5338b5272085f093e7dd79158`: Verify #1415 — SUCCESS, `2366 passed`;
- squash-merged production main `2eaaaa531f8e9be2e01d03aebafa0b9eadc3b203`: Verify #1416 — SUCCESS.

Failed intermediate SHAs are not evidence for this package and must never be promoted or reused as successful verification.

## Expected control-period effect

Using the proven control values and excluding any uncommitted return COGS restoration:

```text
account_net_accrual = 141707.34
standard_sale_COGS = 85512.00
configured_tax ~= 22459.74  # 6% of 374328.93
period_profit ~= 33735.60 RUB
margin ~= 9.01%
```

These are reconciliation expectations, not permission to infer missing return COGS. Live seller-facing output must continue to fail closed wherever required evidence is unavailable.

## Post-reconciliation runtime regression: omitted aggregate sale_amount

After deploying the sale/unit reconciliation package, the live Telegram query returned `Финансовые данные SKU недоступны`. The message was not a catalog or SKU identity failure. `PeriodProfitFinanceSkuScopeService` emits that generic message when its shared strict Period Profit finance reader returns an error for any day in the requested period.

The regression was introduced by the stricter finance normalization: a `POSTING` product was rejected whenever Ozon omitted only the aggregate `commission.sale_amount`, even when the explicit Ozon monetary components needed to reconstruct that aggregate were present and valid.

Repository-captured real Ozon payloads prove the component identity on actual operations:

```text
67.62 + 22.38 + 0.00 = 90.00
61.85 + 27.53 + 0.62 = 90.00
```

The same identity was observed at control-period aggregate level: `sale_price + bonus + coinvestment` reconciles to `sale_amount` to display rounding.

### Safe compatibility rule

Production main `32a740c6341feadf67979e43cba8fea47f2f75f5` implements a narrow recovery rule:

- explicit valid `sale_amount` always wins and is preserved unchanged;
- only when `sale_amount` itself is omitted/invalid, it may be reconstructed from the three explicit Ozon money fields `sale_price + bonus + coinvestment`;
- `seller_price` is never used as a revenue fallback;
- if any of the three reconstruction components is missing, invalid, or non-finite, Period Profit still fails closed;
- the internal raw-source diagnostic continues to mark the omitted `sale_amount` as incomplete rather than pretending Ozon supplied it;
- no tax, account-net-accrual, return-COGS, or execution formula was broadened;
- Ozon remains READ-ONLY and seller-facing Period Profit remains `read_only=True`, `executed=False`.

### Verification evidence for the runtime regression fix

- `c9a69b38c4adaf678e7a4765c8cea136dbe2f42b`: Verify #1428 — FAILED (`1 failed, 2366 passed`); this SHA is permanently failed and is not package evidence;
- exact corrected feature head `0aa22d474de946fb184b6c4be443b84968a3801c`: Verify #1429 — SUCCESS;
- PR #439 actual synthetic merge: Verify #1430 — SUCCESS;
- squash-merged production main `32a740c6341feadf67979e43cba8fea47f2f75f5`: Verify #1431 — SUCCESS.

This follow-up fixes availability of the reconciled finance path without changing the proven seller-facing revenue semantics or treating unknown money as zero.

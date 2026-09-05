# AI Assistant Project State

## Current product state

AI Business Assistant remains a read-only Ozon business analyst and advisor. Ozon business mutations remain prohibited.

## Current verified checkpoint

Package: `v1401-v1410: Period Profit Finance SKU Scope`

Exact production main: `cb6f3fd3341debf52617688350a3c6d7cab336fd`

Verify #1272: success.

Artifact: `9967892096`.

Digest: `sha256:fb2a8fa99482e86d2c70e7e9a40547f71065899c1162e7916999511c585a4e7a`.

## Period Profit runtime fix

Repeated Telegram validation showed that complete current catalog pagination alone was insufficient. Period Profit had been using catalog rows as the SKU scope for a historical period, while Ozon finance defines the actual SKU participation for that period.

Period Profit now derives the unique SKU scope from Ozon finance `POSTING` accruals for the exact selected interval. The catalog is used only to resolve product identity and configured cost. Duplicate catalog rows for the same SKU are deduplicated before product-cost calculation.

If a SKU observed in finance has no catalog/cost mapping, the calculation fails closed with a specific coverage error. Unknown cost is never converted to zero.

The product/account revenue reconciliation guard remains intact as a final integrity check.

## Period Profit accounting boundary

Account-level Ozon revenue and `net_accrual` remain the monetary authority.

The canonical seller-facing calculation remains:

`period_profit = account_net_accrual + exact_committed_return_cogs_if_valid - product_cost - configured_tax`

Return COGS application remains exact-once, read-only and no-double-count. Unknown monetary evidence remains `None`, never inferred zero.

## Verification lifecycle

Failed feature precursor remains failed permanently:

- `6650f02f255a07765ee8a53d518c16d3f34acc7d` — Verify #1268 failed; later success is not transferred to it.

Successful lifecycle:

- feature head `2737896a5def0d058a946c4edcbc69b07906d344` — Verify #1269 succeeded;
- PR #417 synthetic merge `962810cf789e62b16d287addbc182d7e9917576b` — Verify #1271 succeeded; artifact `9967881438`, digest `sha256:3534e8cbb49340a7157c3b9e33dd0ed4bddf60954a084af58f6f501ed50effbf`;
- squash production main `cb6f3fd3341debf52617688350a3c6d7cab336fd` — Verify #1272 succeeded; artifact `9967892096`, digest `sha256:fb2a8fa99482e86d2c70e7e9a40547f71065899c1162e7916999511c585a4e7a`.

## Preserved boundaries

- account-level Ozon finance remains the monetary authority;
- finance-period SKU evidence defines product-cost scope;
- catalog provides identity/cost mapping only;
- duplicate SKU rows are not double counted;
- missing finance SKU mapping fails closed;
- product revenue reconciliation remains required;
- no Ozon mutation;
- no compensation double counting;
- exact-once Return COGS commitment remains append-only;
- unknown money remains `None`, not zero;
- `externally_verified=False` until the user validates the new runtime path in Telegram.

## Next product work

Repeat production validation of `Прибыль за период` in Telegram. If a historical finance SKU lacks a current/local product mapping, surface that exact SKU coverage blocker instead of the previous generic revenue mismatch.

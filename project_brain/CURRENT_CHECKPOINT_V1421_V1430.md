# Current Checkpoint v1421-v1430

Package: `Period Profit Historical SKU Cost Input`

Verified production main: `91cba3362c67253cfb938458d716e5651471b5c9`

Verify #1301: success.

Artifact: `9968500427`.

Digest: `sha256:791b5d2bfac7f0720b253c69eeca29c873edcb16a5589f399ecd08ec9add6d9d`.

Runtime result: finance SKU `3398133813` has no confirmed local seller COGS. Telegram now supports `/costsku SKU COST` as a local-only seller-confirmed COGS input. Period Profit then recovers the historical finance SKU from that unique local record.

Safety: Ozon remains read-only; unknown cost is never zero; account-level finance remains monetary authority; product/account revenue reconciliation and no-double-count guards remain required.

# Current Checkpoint v1441-v1450

Package: `v1441-v1450: Period Profit Finance Retry`

Verified production main: `3baf95dde0ccf5e9f808e61b79803f841d74a664`.

Runtime trigger: Telegram returned `Финансовые данные недоступны за 2026-08-30`.

Period Profit now uses a read-only Ozon client that adds an extra retry layer for transient HTTP `408`, `500`, `502`, `503`, and `504` responses from finance reads. Non-transient errors and exhausted retry budgets remain unavailable; no missing monetary value is converted to zero.

The accounting contract is unchanged: account-level Ozon finance remains monetary authority, unknown money remains unknown, Ozon mutations remain prohibited, and no-double-count rules remain intact.

Verification: feature head `643447a246695d111b5e66ddb6f77ce6a1d383e2` passed Verify #1329; PR #425 synthetic merge `3abf9439ec6a0fb4e70f251253cd2c4317f6c33b` passed Verify #1330; production main `3baf95dde0ccf5e9f808e61b79803f841d74a664` passed Verify #1331.

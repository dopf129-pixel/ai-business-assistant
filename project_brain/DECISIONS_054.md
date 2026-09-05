# Decision 054 — Transient Finance Read Retry

A transient Ozon finance HTTP failure must not be treated as proof of zero financial activity.

For Period Profit finance reads, HTTP `408`, `500`, `502`, `503`, and `504` may be retried within a bounded retry budget. A successful response is consumed normally. A non-transient error or exhausted retry budget remains unavailable and causes fail-closed behavior.

This changes transport resilience only. It does not change financial formulas, monetary authority, coverage rules, Return COGS recognition, or the permanent read-only Ozon boundary.

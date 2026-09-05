# Decision 055 — Visible Telegram Work Feedback

Long-running Telegram requests must acknowledge accepted work before synchronous assistant or Ozon reads begin.

The transport shows a transient progress message plus a best-effort `typing` action. The progress message is replaced with the final result or error when possible; otherwise one fallback final message is sent. Transport feedback must never change financial values, infer missing data, or mutate Ozon.

Slash commands remain immediate. Period Profit remains read-only and all existing accounting/no-double-count/unknown-not-zero rules remain authoritative.

# Decision 058 — Fail-Closed Required Money and Compact Seller Output

Period Profit must validate Ozon monetary evidence that directly feeds its calculation before legacy parsing can convert missing or malformed values into zero. Required `total_amount`, POSTING seller price and sale commission, and present delivery/item-fee accrued amounts must be finite monetary values. Missing or malformed required money is unknown and the Period Profit read fails closed; an explicitly observed numeric zero remains zero.

Revenue diagnostics are troubleshooting evidence, not normal seller-facing report content. They remain internal and read-only while the compact Telegram report stays focused on revenue, units, Ozon accrual, COGS, tax, profit, margin, comparison, and material warnings.

This decision does not change Decision 056 seller-price revenue authority, account-level Ozon `total_amount` monetary authority, the canonical Period Profit formula, tax policy, COGS, return-COGS gates, or Ozon read-only behavior.

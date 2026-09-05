# Current Checkpoint — v1481-v1490 Period Profit Trust Hardening

Production runtime SHA: `7a2385b6a507b1ca182a848d902fb743c9bb8961`.

Period Profit now validates Ozon monetary fields required by the calculation before the legacy FinanceService can coerce missing or malformed values to zero. Missing or malformed required money fails closed; explicit numeric zero remains a valid observed zero.

The compact Telegram report remains seller-focused. Raw Ozon revenue diagnostics stay available in the internal read-only result for troubleshooting but are no longer rendered in the normal Telegram response.

This package does not change the canonical Period Profit formula, account-level `total_amount` authority, seller-price revenue authority, configured tax, COGS, return-COGS recognition/application gates, or Ozon read-only policy.

Verification: exact production main `7a2385b6a507b1ca182a848d902fb743c9bb8961`, Verify run `33971220986`, full verification succeeded.

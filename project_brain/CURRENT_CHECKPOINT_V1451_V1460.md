# Current Checkpoint v1451-v1460

## Telegram Loading Feedback

Production feature main: `cd399c3322203b1bc6d6b2f30bd22dc58fb7930c`.

- Long Telegram text requests immediately show a progress message before synchronous assistant/Ozon work starts.
- Finance-like requests show `⏳ Загружаю финансовые данные Ozon…`; other non-command requests show `⏳ Обрабатываю запрос…`.
- Telegram `typing` is sent best-effort and never affects the business result.
- On completion, the progress message is edited into the final result; if editing is unavailable, exactly one fallback final message is sent.
- Errors can replace the same progress message, so users are not left with a stale loading indicator.
- Slash commands remain immediate and do not get a loading placeholder.
- This package changes presentation/transport only. Period Profit formulas, unknown-vs-zero semantics, no-double-counting, and the read-only Ozon boundary are unchanged.

Verification: feature head and PR synthetic merge passed; exact production main Verify #1342 passed.

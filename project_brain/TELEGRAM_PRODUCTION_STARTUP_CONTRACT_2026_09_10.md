# Telegram production startup contract — 2026-09-10

## Production entrypoint

The canonical repository-owned polling entrypoint is `app/telegram_api_bot.py`.

From the repository root it is started with:

```bash
PYTHONPATH=app python -m telegram_api_bot
```

The entrypoint delegates to `telegram_app_layer.telegram_api_bot` and exposes `build_application()` and `main()`.

## Startup behavior

Importing the Telegram entrypoint no longer creates the seller assistant runtime. The assistant is created lazily on the first handled Telegram request/callback through `get_runner()`.

`build_application()` performs startup assembly without starting polling. It:

- resolves `TELEGRAM_BOT_TOKEN` (or an explicitly supplied token),
- strips surrounding whitespace,
- fails fast with `RuntimeError` when the token is absent,
- does not include the token value in the error,
- registers the `/start`, text-message, and callback handlers,
- does not create the seller runtime or start network polling.

`main()` is the only production polling boundary: it builds the application and calls `run_polling()`.

## Verification coverage

`tests/test_telegram_runtime_dependencies.py` now additionally verifies that:

- the canonical imported `telegram_api_bot` module is the repository file `app/telegram_api_bot.py`,
- importing Telegram startup code does not materialize seller runtime state,
- missing `TELEGRAM_BOT_TOKEN` fails fast,
- application assembly registers the three expected handler classes without starting polling,
- explicit token normalization is deterministic.

The implementation PR is #507.

Feature SHA: `43cf3785ca11b6501dd0097e25bcd4726316efd5`.

PR synthetic merge SHA: `f46e9044ab15d324702947bcafa45e539ab96651`.

Production main after the implementation squash merge: `0eed4ac2e8c3d0ed32e7f32efa752a61d92bd006`.

All three implementation lifecycle verification runs completed successfully before this reconciliation branch was created.

## Safety invariants

This package changes Telegram process startup only. It does not add Ozon write operations or accounting execution.

Existing Return COGS safety semantics remain unchanged: `ReturnedToOzon` is candidate evidence only; unknown values are not zero; no guessed quantity × cost is created; accounting facts are not auto-created; Period Profit remains seller-facing read-only/non-executing; readiness is not execution; repeat commit remains prohibited; canonical status and boolean requirements remain jointly enforced; inventory recovery is presentation-authoritative only under the established ready/status-state conditions.

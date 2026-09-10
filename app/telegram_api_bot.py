"""Canonical production entrypoint for the Telegram polling bot.

Run from the repository root with:
    PYTHONPATH=app python -m telegram_api_bot
"""

from telegram_app_layer.telegram_api_bot import build_application, main


__all__ = ["build_application", "main"]


if __name__ == "__main__":
    main()

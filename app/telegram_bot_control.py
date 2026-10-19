"""Local status and graceful-stop CLI; makes no Telegram or Ozon requests."""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from services.bot_instance_lifecycle_service import (
    BotLifecycleError,
    inspect_bot_instance,
    request_graceful_stop,
)


def _status_text(status: dict) -> str:
    state = status["state"]
    phrases = {
        "STOPPED": "Бот остановлен.",
        "STARTING": "Бот запускается; готовность Telegram ещё не подтверждена.",
        "RUNNING": "Бот работает и завершил инициализацию Telegram.",
        "STOPPING": "Бот завершает работу.",
        "UNKNOWN": "Состояние не удалось безопасно подтвердить.",
    }
    lines = [f"Состояние: {state}", phrases.get(state, phrases["UNKNOWN"])]
    if status.get("revision"):
        lines.append(f"Ревизия: {status['revision']}")
    if status.get("started_at_utc"):
        lines.append(f"Запущен (UTC): {status['started_at_utc']}")
    if status.get("mode"):
        lines.append(f"Режим: {status['mode']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Управление локальным экземпляром Telegram-бота")
    parser.add_argument("command", choices=("status", "stop"))
    arguments = parser.parse_args(argv)
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN не настроен в локальном .env.", file=sys.stderr)
        return 2

    try:
        if arguments.command == "status":
            print(_status_text(inspect_bot_instance(token)))
            return 0
        result = request_graceful_stop(token)
    except BotLifecycleError as error:
        print(f"Не удалось управлять экземпляром бота ({error.code}).", file=sys.stderr)
        return 3

    if result.get("stopped"):
        print("Бот штатно остановлен.")
        return 0
    code = result.get("code", "BOT_INSTANCE_STOP_TIMEOUT")
    if code == "BOT_INSTANCE_STOP_TIMEOUT":
        print("Бот не подтвердил остановку за 15 секунд; принудительно не завершал.", file=sys.stderr)
    else:
        print(f"Не удалось подтвердить остановку ({code}); процесс не завершался принудительно.", file=sys.stderr)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())

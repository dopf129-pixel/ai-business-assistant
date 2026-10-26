"""Local status and checkout-scoped graceful-stop CLI; no Telegram/Ozon calls."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

from runtime_healthcheck import check_runtime_environment
from services.bot_instance_lifecycle_service import (
    BotLifecycleError,
    inspect_bot_instance,
    project_root_fingerprint,
    request_graceful_stop,
)


_HEALTH_REASONS = {
    "ok": ("ENVIRONMENT_READY", "Настройки локального запуска корректны."),
    "telegram token is not configured": (
        "TELEGRAM_TOKEN_MISSING", "Не задан Telegram bot token."
    ),
    "storage root does not exist": (
        "STORAGE_ROOT_MISSING", "Папка локальных данных не найдена."
    ),
    "storage root is not a directory": (
        "STORAGE_ROOT_INVALID", "Путь локальных данных не является папкой."
    ),
    "storage root is not writable": (
        "STORAGE_ROOT_NOT_WRITABLE", "Нет доступа к папке локальных данных."
    ),
    "Ozon credential master key is not configured": (
        "OZON_MASTER_KEY_MISSING", "Не настроен ключ локального шифрования Ozon."
    ),
    "Ozon credential master key is invalid": (
        "OZON_MASTER_KEY_INVALID", "Ключ локального шифрования Ozon имеет неверный формат."
    ),
}
_FAILURE_LABELS = {
    "TELEGRAM_STARTUP_FAILED": "Ошибка настройки Telegram приложения при запуске.",
    "TELEGRAM_POLLING_FAILED": "Telegram polling завершился с ошибкой.",
    "BOT_INSTANCE_UPDATER_UNAVAILABLE": "В сборке недоступен Telegram polling updater.",
}


def _health_summary(environment_result):
    if (
        not isinstance(environment_result, tuple)
        or len(environment_result) != 2
        or not isinstance(environment_result[0], bool)
    ):
        return "RUNTIME_CHECK_UNAVAILABLE", "Проверка локальной конфигурации недоступна."
    healthy, reason = environment_result
    if healthy:
        return _HEALTH_REASONS["ok"]
    safe_reason = reason if isinstance(reason, str) else None
    return _HEALTH_REASONS.get(
        safe_reason,
        ("RUNTIME_CONFIGURATION_INVALID", "Настройки локального запуска требуют проверки."),
    )


def _status_text(status: dict, environment_result=None, expected_checkout_fingerprint=None) -> str:
    state = status.get("state", "UNKNOWN")
    phrases = {
        "STOPPED": "Polling не запущен.",
        "STARTING": "Процесс запускается; готовность polling ещё не подтверждена.",
        "RUNNING": "Telegram polling и обработка обновлений подтверждены.",
        "STOPPING": "Процесс штатно завершает работу.",
        "UNKNOWN": "Состояние процесса не удалось безопасно подтвердить.",
    }
    lines = [f"Состояние: {state}", phrases.get(state, phrases["UNKNOWN"])]
    if environment_result is not None:
        health_code, health_text = _health_summary(environment_result)
        lines.append("Настройки локального запуска: " + health_code)
        lines.append(health_text)
    if state in {"RUNNING", "STARTING", "STOPPING"}:
        observed_fingerprint = status.get("project_root_fingerprint")
        if observed_fingerprint is None:
            checkout = "не подтверждена (старая lifecycle-запись)"
        elif observed_fingerprint == expected_checkout_fingerprint:
            checkout = "совпадает с текущей папкой проекта"
        else:
            checkout = "другая папка проекта"
        lines.append("Папка процесса: " + checkout)
    if status.get("revision"):
        lines.append(f"Ревизия: {status['revision']}")
    if status.get("started_at_utc"):
        lines.append(f"Запущен (UTC): {status['started_at_utc']}")
    if status.get("mode") in {"foreground", "background"}:
        lines.append("Режим: " + ("фоновый" if status["mode"] == "background" else "обычный"))
    failure_code = status.get("last_failure_code")
    if isinstance(failure_code, str) and failure_code in _FAILURE_LABELS:
        lines.append("Последний сбой: " + _FAILURE_LABELS[failure_code])
        lines.append("Код сбоя: " + failure_code)
    return "\n".join(lines)


def _parser():
    parser = argparse.ArgumentParser(description="Локальный статус и штатная остановка Telegram-бота")
    parser.add_argument("command", choices=("status", "stop"))
    parser.add_argument("--project-root", default=os.getcwd())
    return parser


def main(argv=None) -> int:
    arguments = _parser().parse_args(argv)
    project_root = Path(arguments.project_root).resolve(strict=False)
    load_dotenv(dotenv_path=project_root / ".env", override=False)
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    environment = os.environ.copy()
    storage_root = str(environment.get("AI_ASSISTANT_STORAGE_ROOT", "") or "").strip()
    if storage_root and not Path(storage_root).is_absolute():
        environment["AI_ASSISTANT_STORAGE_ROOT"] = str(project_root / storage_root)
    environment_result = check_runtime_environment(environment)
    checkout_fingerprint = project_root_fingerprint(project_root)

    if arguments.command == "status":
        if not token:
            unknown_status = {
                "state": "UNKNOWN", "revision": None, "started_at_utc": None,
                "mode": None, "project_root_fingerprint": None,
                "last_failure_code": None,
            }
            print(_status_text(unknown_status, environment_result, checkout_fingerprint))
            return 2
        try:
            status = inspect_bot_instance(token)
        except BotLifecycleError as error:
            status = {
                "state": "UNKNOWN", "revision": None, "started_at_utc": None,
                "mode": None, "project_root_fingerprint": None,
                "last_failure_code": error.code,
            }
        print(_status_text(status, environment_result, checkout_fingerprint))
        if status.get("state") == "UNKNOWN":
            return 3
        return 0 if environment_result[0] else 5

    if not token:
        print("Не настроен Telegram bot token; остановка не выполнялась.", file=sys.stderr)
        return 2
    try:
        result = request_graceful_stop(
            token,
            expected_project_root_fingerprint=checkout_fingerprint,
        )
    except BotLifecycleError as error:
        print(f"Не удалось управлять экземпляром бота ({error.code}).", file=sys.stderr)
        return 3

    if result.get("stopped"):
        print("Бот штатно остановлен.")
        return 0
    code = result.get("code", "BOT_INSTANCE_STOP_TIMEOUT")
    if code == "BOT_INSTANCE_STOP_TIMEOUT":
        print("Бот не подтвердил остановку за 15 секунд; принудительно не завершал.", file=sys.stderr)
    elif code == "BOT_INSTANCE_CHECKOUT_MISMATCH":
        print("Бот запущен из другой или неподтверждённой папки; остановка не выполнялась.", file=sys.stderr)
    else:
        print(f"Не удалось подтвердить остановку ({code}); процесс не завершался принудительно.", file=sys.stderr)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())

from pathlib import Path

from telegram_bot_control import main
from services.bot_instance_lifecycle_service import project_root_fingerprint


def test_status_cli_shows_captured_process_metadata_without_token(monkeypatch, capsys):
    token = "synthetic-cli-token-not-for-output"
    monkeypatch.setattr("telegram_bot_control.load_dotenv", lambda **_kwargs: None)
    monkeypatch.setattr("telegram_bot_control.check_runtime_environment", lambda _env: (True, "ok"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setattr(
        "telegram_bot_control.inspect_bot_instance",
        lambda value: {
            "state": "RUNNING",
            "revision": "abcdef0123456789",
            "started_at_utc": "2026-10-19T10:00:00.000Z",
            "mode": "background",
            "project_root_fingerprint": project_root_fingerprint(Path.cwd()),
            "last_failure_code": None,
        },
    )

    assert main(["status"]) == 0
    output = capsys.readouterr().out
    assert "Состояние: RUNNING" in output
    assert "abcdef0123456789" in output
    assert "2026-10-19T10:00:00.000Z" in output
    assert "фоновый" in output
    assert "Настройки локального запуска: ENVIRONMENT_READY" in output
    assert "Папка процесса: совпадает" in output
    assert token not in output


def test_stop_cli_does_not_claim_success_when_owner_still_stopping(monkeypatch, capsys):
    token = "synthetic-cli-stop-token"
    monkeypatch.setattr("telegram_bot_control.load_dotenv", lambda **_kwargs: None)
    monkeypatch.setattr("telegram_bot_control.check_runtime_environment", lambda _env: (True, "ok"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setattr(
        "telegram_bot_control.request_graceful_stop",
        lambda value, **_kwargs: {
            "stopped": False,
            "state": "STOPPING",
            "code": "BOT_INSTANCE_STOP_TIMEOUT",
        },
    )

    assert main(["stop"]) == 4
    output = capsys.readouterr()
    assert "не подтвердил остановку" in output.err
    assert "штатно остановлен" not in output.out
    assert token not in output.out + output.err


def test_stop_cli_refuses_foreign_checkout_without_force_termination(monkeypatch, capsys):
    token = "synthetic-foreign-checkout-token"
    received = {}
    monkeypatch.setattr("telegram_bot_control.load_dotenv", lambda **_kwargs: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)

    def stop(received_token, *, expected_project_root_fingerprint):
        received["token"] = received_token
        received["checkout"] = expected_project_root_fingerprint
        return {
            "stopped": False,
            "state": "RUNNING",
            "code": "BOT_INSTANCE_CHECKOUT_MISMATCH",
        }

    monkeypatch.setattr("telegram_bot_control.request_graceful_stop", stop)

    assert main(["stop"]) == 4
    output = capsys.readouterr()
    assert received["token"] == token
    assert received["checkout"] == project_root_fingerprint(Path.cwd())
    assert "другой" in output.err
    assert "принудительно" not in output.err
    assert token not in output.out + output.err


def test_status_distinguishes_configuration_error_from_foreign_running_process(monkeypatch, capsys):
    secret_path = "C:/seller/private-project"
    monkeypatch.setattr("telegram_bot_control.load_dotenv", lambda **_kwargs: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "synthetic-status-token")
    monkeypatch.setattr(
        "telegram_bot_control.check_runtime_environment",
        lambda _env: (False, "Ozon credential master key is invalid"),
    )
    monkeypatch.setattr(
        "telegram_bot_control.inspect_bot_instance",
        lambda _token: {
            "state": "RUNNING",
            "revision": "abcdef0123456789",
            "started_at_utc": None,
            "mode": "background",
            "project_root_fingerprint": "f" * 64,
            "last_failure_code": "TELEGRAM_POLLING_FAILED",
        },
    )

    assert main(["status", "--project-root", secret_path]) == 5
    output = capsys.readouterr().out
    assert "Состояние: RUNNING" in output
    assert "OZON_MASTER_KEY_INVALID" in output
    assert "другая папка проекта" in output
    assert "TELEGRAM_POLLING_FAILED" in output
    assert secret_path not in output
    assert "ozon credential master key is invalid" not in output.lower()


def test_cli_requires_token_without_echoing_it(monkeypatch, capsys):
    monkeypatch.setattr("telegram_bot_control.load_dotenv", lambda **_kwargs: None)
    monkeypatch.setattr(
        "telegram_bot_control.check_runtime_environment",
        lambda _env: (False, "telegram token is not configured"),
    )
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    assert main(["status"]) == 2
    output = capsys.readouterr()
    assert "TELEGRAM_TOKEN_MISSING" in output.out
    assert "UNKNOWN" in output.out

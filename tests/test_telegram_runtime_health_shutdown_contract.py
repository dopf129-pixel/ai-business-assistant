import signal
from pathlib import Path

import pytest

import runtime_healthcheck
from telegram_app_layer import telegram_api_bot


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"


def test_healthcheck_requires_telegram_token_without_exposing_value(tmp_path):
    healthy, message = runtime_healthcheck.check_runtime_environment(
        {
            "TELEGRAM_BOT_TOKEN": "",
            "AI_ASSISTANT_STORAGE_ROOT": str(tmp_path),
        }
    )

    assert healthy is False
    assert message == "telegram token is not configured"


def test_healthcheck_accepts_existing_persistent_storage(tmp_path):
    healthy, message = runtime_healthcheck.check_runtime_environment(
        {
            "TELEGRAM_BOT_TOKEN": "secret-token",
            "AI_ASSISTANT_STORAGE_ROOT": str(tmp_path),
        }
    )

    assert healthy is True
    assert message == "ok"
    assert "secret-token" not in message


def test_healthcheck_is_side_effect_free_for_missing_storage(tmp_path):
    missing = tmp_path / "not-created"

    healthy, message = runtime_healthcheck.check_runtime_environment(
        {
            "TELEGRAM_BOT_TOKEN": "secret-token",
            "AI_ASSISTANT_STORAGE_ROOT": str(missing),
        }
    )

    assert healthy is False
    assert message == "storage root does not exist"
    assert not missing.exists()


def test_healthcheck_rejects_non_directory_storage_root(tmp_path):
    file_path = tmp_path / "state-file"
    file_path.write_text("x", encoding="utf-8")

    healthy, message = runtime_healthcheck.check_runtime_environment(
        {
            "TELEGRAM_BOT_TOKEN": "secret-token",
            "AI_ASSISTANT_STORAGE_ROOT": str(file_path),
        }
    )

    assert healthy is False
    assert message == "storage root is not a directory"


def test_healthcheck_cli_returns_zero_for_healthy_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(tmp_path))

    with pytest.raises(SystemExit) as exc_info:
        runtime_healthcheck.main()

    assert exc_info.value.code == 0


def test_telegram_main_registers_graceful_shutdown_signals(monkeypatch):
    calls = []

    class _Application:
        def run_polling(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(telegram_api_bot, "build_application", lambda: _Application())

    telegram_api_bot.main()

    assert calls == [
        {
            "stop_signals": (signal.SIGINT, signal.SIGTERM),
        }
    ]


def test_dockerfile_declares_healthcheck_and_sigterm_stop_contract():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert 'CMD ["python", "-m", "runtime_healthcheck"]' in dockerfile
    assert "HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3" in dockerfile
    assert "STOPSIGNAL SIGTERM" in dockerfile

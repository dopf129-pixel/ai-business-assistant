import os
import signal
import asyncio
from pathlib import Path

import pytest

import runtime_healthcheck
from telegram_app_layer import telegram_api_bot
from services.bot_instance_lifecycle_service import BotInstanceAlreadyRunning


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
TEST_MASTER_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def _environment(storage_root, **overrides):
    environment = {
        "TELEGRAM_BOT_TOKEN": "secret-token",
        "AI_ASSISTANT_STORAGE_ROOT": str(storage_root),
        "OZON_CREDENTIAL_MASTER_KEY": TEST_MASTER_KEY,
    }
    environment.update(overrides)
    return environment


def test_healthcheck_requires_telegram_token_without_exposing_value(tmp_path):
    healthy, message = runtime_healthcheck.check_runtime_environment(
        _environment(tmp_path, TELEGRAM_BOT_TOKEN="")
    )

    assert healthy is False
    assert message == "telegram token is not configured"


def test_healthcheck_accepts_existing_persistent_storage(tmp_path):
    healthy, message = runtime_healthcheck.check_runtime_environment(
        _environment(tmp_path)
    )

    assert healthy is True
    assert message == "ok"
    assert "secret-token" not in message
    assert TEST_MASTER_KEY not in message


def test_healthcheck_requires_ozon_master_key_for_persistent_runtime(tmp_path):
    healthy, message = runtime_healthcheck.check_runtime_environment(
        _environment(tmp_path, OZON_CREDENTIAL_MASTER_KEY="")
    )

    assert healthy is False
    assert message == "Ozon credential master key is not configured"
    assert TEST_MASTER_KEY not in message


def test_healthcheck_rejects_invalid_ozon_master_key_without_echoing_it(tmp_path):
    invalid_key = "not-a-valid-fernet-key"
    healthy, message = runtime_healthcheck.check_runtime_environment(
        _environment(tmp_path, OZON_CREDENTIAL_MASTER_KEY=invalid_key)
    )

    assert healthy is False
    assert message == "Ozon credential master key is invalid"
    assert invalid_key not in message


def test_healthcheck_is_side_effect_free_for_missing_storage(tmp_path):
    missing = tmp_path / "not-created"

    healthy, message = runtime_healthcheck.check_runtime_environment(
        _environment(missing)
    )

    assert healthy is False
    assert message == "storage root does not exist"
    assert not missing.exists()


def test_healthcheck_rejects_non_directory_storage_root(tmp_path):
    file_path = tmp_path / "state-file"
    file_path.write_text("x", encoding="utf-8")

    healthy, message = runtime_healthcheck.check_runtime_environment(
        _environment(file_path)
    )

    assert healthy is False
    assert message == "storage root is not a directory"


def test_healthcheck_cli_returns_zero_for_healthy_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("OZON_CREDENTIAL_MASTER_KEY", TEST_MASTER_KEY)

    with pytest.raises(SystemExit) as exc_info:
        runtime_healthcheck.main()

    assert exc_info.value.code == 0


def test_telegram_main_registers_graceful_shutdown_signals(monkeypatch):
    calls = []

    class _Lease:
        def __init__(self, token):
            assert token == "synthetic-lifecycle-token"
            self.closed = False

        def acquire(self):
            calls.append("acquire")

        def close(self):
            self.closed = True
            calls.append("close")

    class _Application:
        def __init__(self):
            self.bot_data = {}
            self.updater = object()

        def run_polling(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(telegram_api_bot, "_resolve_token", lambda: "synthetic-lifecycle-token")
    monkeypatch.setattr(telegram_api_bot, "BotInstanceLease", _Lease)
    monkeypatch.setattr(telegram_api_bot, "build_application", lambda token=None: _Application())

    telegram_api_bot.main()

    assert calls == [
        "acquire",
        {"stop_signals": None if os.name == "nt" else (signal.SIGINT, signal.SIGTERM)},
        "close",
    ]


def test_second_main_owner_does_not_build_or_poll_application(monkeypatch, capsys):
    class _Lease:
        def __init__(self, token):
            self.token = token

        def acquire(self):
            raise BotInstanceAlreadyRunning()

    monkeypatch.setattr(telegram_api_bot, "_resolve_token", lambda: "synthetic-duplicate-token")
    monkeypatch.setattr(telegram_api_bot, "BotInstanceLease", _Lease)
    monkeypatch.setattr(
        telegram_api_bot,
        "build_application",
        lambda token=None: pytest.fail("duplicate instance must not build polling"),
    )

    assert telegram_api_bot.main() == 3
    assert "already running" in capsys.readouterr().out


def test_running_status_waits_until_updater_and_application_are_running():
    marks = []

    class _Lease:
        def mark_running(self):
            marks.append("ready")

    class _Updater:
        running = False

    class _Application:
        updater = _Updater()
        running = False

    async def scenario():
        task = asyncio.create_task(
            telegram_api_bot._publish_polling_readiness(_Application(), _Lease())
        )
        await asyncio.sleep(0.05)
        assert marks == []
        _Application.updater.running = True
        await asyncio.sleep(0.05)
        assert marks == []
        _Application.running = True
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(scenario())
    assert marks == ["ready"]


def test_dockerfile_declares_healthcheck_and_sigterm_stop_contract():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert 'CMD ["python", "-m", "runtime_healthcheck"]' in dockerfile
    assert "HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3" in dockerfile
    assert "STOPSIGNAL SIGTERM" in dockerfile

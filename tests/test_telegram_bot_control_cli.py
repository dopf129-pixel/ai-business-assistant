from telegram_bot_control import main


def test_status_cli_shows_captured_process_metadata_without_token(monkeypatch, capsys):
    token = "synthetic-cli-token-not-for-output"
    monkeypatch.setattr("telegram_bot_control.load_dotenv", lambda: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setattr(
        "telegram_bot_control.inspect_bot_instance",
        lambda value: {
            "state": "RUNNING",
            "revision": "abcdef0123456789",
            "started_at_utc": "2026-10-19T10:00:00.000Z",
            "mode": "background",
        },
    )

    assert main(["status"]) == 0
    output = capsys.readouterr().out
    assert "Состояние: RUNNING" in output
    assert "abcdef0123456789" in output
    assert "2026-10-19T10:00:00.000Z" in output
    assert "background" in output
    assert token not in output


def test_stop_cli_does_not_claim_success_when_owner_still_stopping(monkeypatch, capsys):
    token = "synthetic-cli-stop-token"
    monkeypatch.setattr("telegram_bot_control.load_dotenv", lambda: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setattr(
        "telegram_bot_control.request_graceful_stop",
        lambda value: {
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


def test_cli_requires_token_without_echoing_it(monkeypatch, capsys):
    monkeypatch.setattr("telegram_bot_control.load_dotenv", lambda: None)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    assert main(["status"]) == 2
    output = capsys.readouterr()
    assert "TELEGRAM_BOT_TOKEN" in output.err

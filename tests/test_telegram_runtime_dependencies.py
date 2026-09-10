from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ENTRYPOINT = ROOT / "app" / "telegram_api_bot.py"


def test_production_requirements_install_telegram_runtime_dependency():
    requirements = Path("requirements.txt").read_text(encoding="utf-8")

    assert "python-telegram-bot" in requirements


def test_dev_requirements_include_production_runtime_dependencies():
    requirements = Path("requirements-dev.txt").read_text(encoding="utf-8")

    assert "-r requirements.txt" in requirements


def test_telegram_runtime_dependency_is_importable():
    from telegram import Update
    from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler

    assert Update is not None
    assert Application is not None
    assert CallbackQueryHandler is not None
    assert CommandHandler is not None
    assert MessageHandler is not None


def test_canonical_telegram_entrypoint_is_repository_owned():
    import telegram_api_bot

    module_path = Path(telegram_api_bot.__file__).resolve()
    assert module_path == CANONICAL_ENTRYPOINT.resolve()
    assert callable(telegram_api_bot.build_application)
    assert callable(telegram_api_bot.main)


def test_telegram_import_does_not_materialize_seller_runtime():
    from telegram_app_layer import telegram_api_bot

    assert telegram_api_bot._runner is None


def test_build_application_fails_fast_when_token_is_missing(monkeypatch):
    from telegram_app_layer import telegram_api_bot

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        telegram_api_bot.build_application()

    assert str(exc_info.value) == "TELEGRAM_BOT_TOKEN environment variable is required"


def test_build_application_registers_handlers_without_starting_polling(monkeypatch):
    from telegram_app_layer import telegram_api_bot

    class FakeApplication:
        def __init__(self):
            self.handlers = []

        def add_handler(self, handler):
            self.handlers.append(handler)

    class FakeBuilder:
        def __init__(self):
            self.token_value = None
            self.application = FakeApplication()

        def token(self, token):
            self.token_value = token
            return self

        def build(self):
            return self.application

    fake_builder = FakeBuilder()
    monkeypatch.setattr(
        telegram_api_bot.Application,
        "builder",
        lambda: fake_builder,
    )

    application = telegram_api_bot.build_application("  test-token  ")

    assert application is fake_builder.application
    assert fake_builder.token_value == "test-token"
    assert len(application.handlers) == 3
    assert telegram_api_bot._runner is None

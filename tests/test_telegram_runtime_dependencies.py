from pathlib import Path


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

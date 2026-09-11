import os
import signal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from telegram_assistant_factory import create_telegram_assistant
from telegram_app_layer.telegram_action_formatter import TelegramActionFormatter
from telegram_app_layer.telegram_history_formatter import TelegramHistoryFormatter
from telegram_app_layer.telegram_plan_formatter import TelegramPlanFormatter
from telegram_app_layer.telegram_progress_feedback import begin_progress, finish_progress
from telegram_app_layer.telegram_response_formatter import TelegramResponseFormatter


_runner = None
formatter = TelegramResponseFormatter()
action_formatter = TelegramActionFormatter()
plan_formatter = TelegramPlanFormatter()
history_formatter = TelegramHistoryFormatter()


def get_runner():
    """Create the seller assistant only when the bot actually handles traffic."""
    global _runner
    if _runner is None:
        _runner = create_telegram_assistant()
    return _runner


def build_keyboard(keyboard_data):
    if not keyboard_data:
        return None

    rows = []
    for button in keyboard_data.get("buttons", []):
        rows.append(
            [
                InlineKeyboardButton(
                    button["text"],
                    callback_data=button["callback"],
                )
            ]
        )
    return InlineKeyboardMarkup(rows)


def format_response(result):
    if not result:
        return "Нет ответа"
    if result.get("history") is not None:
        return history_formatter.format(result)
    if result.get("plan"):
        return plan_formatter.format(result)
    if result.get("actions"):
        return action_formatter.format(result)
    return formatter.format(result)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result = get_runner().start(user_id)
    keyboard = build_keyboard(result.get("keyboard"))
    await update.message.reply_text(
        result.get("text", ""),
        reply_markup=keyboard,
    )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    progress_message = await begin_progress(
        update.message,
        bot=context.bot,
        chat_id=update.effective_chat.id,
        text=text,
    )

    try:
        result = get_runner().receive_message(user_id, text)
    except Exception:
        await finish_progress(
            update.message,
            progress_message,
            "⚠️ Не удалось обработать запрос. Попробуйте ещё раз.",
        )
        raise

    response = format_response(result)
    keyboard = build_keyboard(result.get("keyboard"))
    await finish_progress(
        update.message,
        progress_message,
        response,
        reply_markup=keyboard,
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    callback = query.data
    progress_message = await begin_progress(
        query.message,
        bot=context.bot,
        chat_id=query.message.chat_id,
        text=callback,
        force=True,
    )

    try:
        result = get_runner().receive_callback(user_id, callback)
    except Exception:
        await finish_progress(
            query.message,
            progress_message,
            "⚠️ Не удалось обработать запрос. Попробуйте ещё раз.",
        )
        raise

    response = format_response(result)
    keyboard = build_keyboard(result.get("keyboard"))
    await finish_progress(
        query.message,
        progress_message,
        response,
        reply_markup=keyboard,
    )


def _resolve_token(token=None):
    resolved = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN")
    resolved = (resolved or "").strip()
    if not resolved:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is required")
    return resolved


def _polling_stop_signals(platform_name=None):
    """Return supported polling stop signals for the current platform."""
    platform_name = platform_name or os.name
    if platform_name == "nt":
        return None
    return (signal.SIGINT, signal.SIGTERM)


def build_application(token=None):
    """Build the polling application without starting network traffic."""
    application = Application.builder().token(_resolve_token(token)).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT, message_handler))
    application.add_handler(CallbackQueryHandler(callback_handler))
    return application


def main():
    application = build_application()
    print("Telegram API bot started")
    application.run_polling(
        stop_signals=_polling_stop_signals(),
    )


if __name__ == "__main__":
    main()

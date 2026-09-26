import asyncio
import io
import os
import signal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonCommands, Update
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


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result = get_runner().receive_callback(user_id, "main_menu")
    keyboard = build_keyboard(result.get("keyboard"))
    await update.message.reply_text(
        result.get("text") or result.get("message") or "Главное меню",
        reply_markup=keyboard,
    )


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
        result = await _run_sync_with_stall_notice(
            lambda: get_runner().receive_message(user_id, text),
            progress_message=progress_message,
        )
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


async def _send_result(message, result, progress_message=None):
    keyboard = build_keyboard(result.get("keyboard"))
    file_content = result.get("file_content")
    filename = result.get("filename")
    if file_content is not None and filename:
        payload = file_content.encode("utf-8") if isinstance(file_content, str) else bytes(file_content)
        document = io.BytesIO(payload)
        document.name = str(filename)
        caption = format_response(result)
        if progress_message is not None:
            await finish_progress(message, progress_message, caption or "Таблица готова.")
        elif caption:
            await message.reply_text(caption)
        await message.reply_document(
            document=document,
            filename=str(filename),
            caption="Заполните себестоимость и отправьте этот CSV-файл обратно боту.",
        )
        return
    response = format_response(result)
    if progress_message is not None:
        await finish_progress(message, progress_message, response, reply_markup=keyboard)
    else:
        await message.reply_text(response, reply_markup=keyboard)


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    document = update.message.document
    if document is None:
        return
    progress_message = await begin_progress(
        update.message,
        bot=context.bot,
        chat_id=update.effective_chat.id,
        text="seller_cost_table_upload",
        force=True,
    )
    try:
        telegram_file = await context.bot.get_file(document.file_id)
        content = bytes(await telegram_file.download_as_bytearray())
        result = await _run_sync_with_stall_notice(
            lambda: get_runner().receive_document(user_id, content, document.file_name),
            progress_message=progress_message,
        )
    except Exception:
        await finish_progress(
            update.message,
            progress_message,
            "⚠️ Не удалось обработать таблицу. Попробуйте ещё раз.",
        )
        raise
    await _send_result(update.message, result, progress_message)


async def _run_sync_with_stall_notice(
    function,
    *,
    progress_message=None,
    stall_seconds=8.0,
    long_wait_seconds=45.0,
    heartbeat_seconds=60.0,
    diagnostic_seconds=90.0,
):
    """Run blocking work off-loop and visibly heartbeat while it is alive.

    This watchdog never imposes a business-operation deadline.  After the slow
    thresholds it updates the same Telegram progress message every heartbeat
    interval with elapsed time.  A user can therefore distinguish a long
    calculation from a bot/process that stopped producing heartbeats.
    """
    loop = asyncio.get_running_loop()
    started_at = loop.time()
    from services.period_profit_operation_diagnostics import (
        PeriodProfitOperationTrace,
        activate_period_profit_trace,
        reset_period_profit_trace,
    )

    trace = PeriodProfitOperationTrace("telegram_callback")

    def observed_function():
        token = activate_period_profit_trace(trace)
        trace.bind_worker()
        try:
            return function()
        finally:
            reset_period_profit_trace(token)

    task = asyncio.create_task(asyncio.to_thread(observed_function))
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=stall_seconds)
    except asyncio.TimeoutError:
        await _mark_progress_slow(progress_message)

    remaining = max(0.0, float(long_wait_seconds) - float(stall_seconds))
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=remaining)
    except asyncio.TimeoutError:
        await _mark_progress_long_running(
            progress_message,
            elapsed_seconds=loop.time() - started_at,
        )

    interval = max(0.01, float(heartbeat_seconds))
    diagnostic_dumped = False
    while True:
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=interval)
        except asyncio.TimeoutError:
            elapsed = loop.time() - started_at
            if not diagnostic_dumped and elapsed >= float(diagnostic_seconds):
                trace.dump_worker_stack()
                diagnostic_dumped = True
            await _mark_progress_heartbeat(
                progress_message,
                elapsed_seconds=elapsed,
            )


def _format_elapsed(seconds):
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    if minutes:
        return f"{minutes} мин {secs:02d} сек"
    return f"{secs} сек"


async def _mark_progress_heartbeat(progress_message, elapsed_seconds):
    if progress_message is None:
        return False
    editor = getattr(progress_message, "edit_text", None)
    if not callable(editor):
        return False
    try:
        await editor(
            "💓 Бот работает. Запрос всё ещё выполняется — "
            + _format_elapsed(elapsed_seconds)
            + ". Продолжаю ждать ответ Ozon/расчёт."
        )
        return True
    except Exception:
        return False


async def _mark_progress_long_running(progress_message, elapsed_seconds=45.0):
    if progress_message is None:
        return False
    editor = getattr(progress_message, "edit_text", None)
    if not callable(editor):
        return False
    try:
        await editor(
            "⏳ Запрос выполняется уже "
            + _format_elapsed(elapsed_seconds)
            + ", но я продолжаю обработку. "
            "Дальше буду обновлять статус каждую минуту."
        )
        return True
    except Exception:
        return False


async def _mark_progress_slow(progress_message):
    if progress_message is None:
        return False
    editor = getattr(progress_message, "edit_text", None)
    if not callable(editor):
        return False
    try:
        await editor(
            "⚠️ Ответ задерживается дольше обычного. "
            "Жду Ozon или локальное хранилище — бот не завис молча…"
        )
        return True
    except Exception:
        return False


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
        result = await _run_sync_with_stall_notice(
            lambda: get_runner().receive_callback(user_id, callback),
            progress_message=progress_message,
        )
    except Exception:
        await finish_progress(
            query.message,
            progress_message,
            "⚠️ Не удалось обработать запрос. Попробуйте ещё раз.",
        )
        raise

    await _send_result(query.message, result, progress_message)


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


async def _post_init(application):
    await application.bot.set_my_commands([
        ("start", "Запустить ассистента"),
        ("menu", "Главное меню"),
    ])
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())


def build_application(token=None):
    """Build the polling application without starting network traffic."""
    application = Application.builder().token(_resolve_token(token)).post_init(_post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(MessageHandler(filters.Document.ALL, document_handler))
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

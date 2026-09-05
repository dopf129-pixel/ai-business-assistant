import os
import sys


sys.path.insert(
    0,
    "app"
)


from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)


from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)


from telegram_assistant_factory import (
    create_telegram_assistant
)


from telegram_app_layer.telegram_response_formatter import (
    TelegramResponseFormatter
)


from telegram_app_layer.telegram_action_formatter import (
    TelegramActionFormatter
)


from telegram_app_layer.telegram_plan_formatter import (
    TelegramPlanFormatter
)


from telegram_app_layer.telegram_history_formatter import (
    TelegramHistoryFormatter
)


from telegram_app_layer.telegram_progress_feedback import (
    begin_progress,
    finish_progress,
)


runner = (
    create_telegram_assistant()
)


formatter = (
    TelegramResponseFormatter()
)


action_formatter = (
    TelegramActionFormatter()
)


plan_formatter = (
    TelegramPlanFormatter()
)


history_formatter = (
    TelegramHistoryFormatter()
)



def build_keyboard(
    keyboard_data
):


    if not keyboard_data:

        return None


    buttons = (
        keyboard_data
        .get("buttons", [])
    )


    rows = []


    for button in buttons:

        rows.append(
            [
                InlineKeyboardButton(
                    button["text"],
                    callback_data=button["callback"]
                )
            ]
        )


    return InlineKeyboardMarkup(
        rows
    )



def format_response(
    result
):


    if not result:

        return "Нет ответа"



    if result.get("history") is not None:

        return (
            history_formatter
            .format(
                result
            )
        )



    if result.get("plan"):

        return (
            plan_formatter
            .format(
                result
            )
        )



    if result.get("actions"):

        return (
            action_formatter
            .format(
                result
            )
        )



    return (
        formatter
        .format(
            result
        )
    )



async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):


    user_id = (
        update.effective_user.id
    )


    result = (
        runner.start(
            user_id
        )
    )


    keyboard = build_keyboard(
        result.get("keyboard")
    )


    await update.message.reply_text(
        result.get("text", ""),
        reply_markup=keyboard
    )



async def message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):


    user_id = (
        update.effective_user.id
    )


    text = (
        update.message.text
    )


    progress_message = await begin_progress(
        update.message,
        bot=context.bot,
        chat_id=update.effective_chat.id,
        text=text,
    )


    try:
        result = (
            runner.receive_message(
                user_id,
                text
            )
        )
    except Exception:
        await finish_progress(
            update.message,
            progress_message,
            "⚠️ Не удалось обработать запрос. Попробуйте ещё раз.",
        )
        raise


    response = (
        format_response(
            result
        )
    )


    keyboard = build_keyboard(
        result.get("keyboard")
    )


    await finish_progress(
        update.message,
        progress_message,
        response,
        reply_markup=keyboard,
    )



async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):


    query = (
        update.callback_query
    )


    await query.answer()


    user_id = (
        query.from_user.id
    )


    callback = (
        query.data
    )


    progress_message = await begin_progress(
        query.message,
        bot=context.bot,
        chat_id=query.message.chat_id,
        text=callback,
        force=True,
    )


    try:
        result = (
            runner.receive_callback(
                user_id,
                callback
            )
        )
    except Exception:
        await finish_progress(
            query.message,
            progress_message,
            "⚠️ Не удалось обработать запрос. Попробуйте ещё раз.",
        )
        raise


    response = (
        format_response(
            result
        )
    )


    keyboard = build_keyboard(
        result.get("keyboard")
    )


    await finish_progress(
        query.message,
        progress_message,
        response,
        reply_markup=keyboard
    )



def main():


    token = (
        os.getenv(
            "TELEGRAM_BOT_TOKEN"
        )
    )


    if not token:

        raise Exception(
            "TELEGRAM_BOT_TOKEN is missing"
        )



    application = (
        Application
        .builder()
        .token(token)
        .build()
    )



    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )



    application.add_handler(
        MessageHandler(
            filters.TEXT,
            message_handler
        )
    )



    application.add_handler(
        CallbackQueryHandler(
            callback_handler
        )
    )



    print(
        "Telegram API bot started"
    )



    application.run_polling()



if __name__ == "__main__":

    main()

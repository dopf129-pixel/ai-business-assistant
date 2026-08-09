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



runner = (
    create_telegram_assistant()
)


formatter = (
    TelegramResponseFormatter()
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


    result = (
        runner.receive_message(
            user_id,
            text
        )
    )


    response = (
        formatter.format(
            result
        )
    )


    await update.message.reply_text(
        response
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


    result = (
        runner.receive_callback(
            user_id,
            callback
        )
    )


    response = (
        formatter.format(
            result
        )
    )


    await query.message.reply_text(
        response
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
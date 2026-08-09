from assistant_app import create_assistant


from services.assistant_keyboard_service import (
    AssistantKeyboardService
)


from services.assistant_button_handler_service import (
    AssistantButtonHandlerService
)


from telegram.assistant_telegram_adapter import (
    AssistantTelegramAdapter
)


from telegram.telegram_bot_service import (
    TelegramBotService
)


from telegram.telegram_runner import (
    TelegramRunner
)



def create_telegram_bot():

    assistant = (
        create_assistant()
    )


    keyboard = (
        AssistantKeyboardService()
    )


    button_handler = (
        AssistantButtonHandlerService(
            assistant
        )
    )


    adapter = (
        AssistantTelegramAdapter(
            assistant,
            keyboard,
            button_handler
        )
    )


    bot_service = (
        TelegramBotService(
            adapter
        )
    )


    return (
        TelegramRunner(
            bot_service
        )
    )



if __name__ == "__main__":

    bot = (
        create_telegram_bot()
    )


    print(
        "Telegram Assistant ready"
    )


    print(
        bot.start()
    )


    print(
        bot.receive_message(
            "Что нужно сделать?"
        )
    )


    print(
        bot.receive_callback(
            "analyze"
        )
    )
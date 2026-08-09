from assistant_app import create_assistant


from services.assistant_keyboard_service import (
    AssistantKeyboardService
)


from services.assistant_button_handler_service import (
    AssistantButtonHandlerService
)


from services.assistant_user_profile_service import (
    AssistantUserProfileService
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


    profiles = (
        AssistantUserProfileService()
    )


    adapter = (
        AssistantTelegramAdapter(
            assistant,
            keyboard,
            button_handler,
            profiles
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


    user_1 = 1001

    user_2 = 2002


    print(
        "Telegram Assistant ready"
    )


    print(
        "\nUSER 1001"
    )


    print(
        bot.start(
            user_1
        )
    )


    print(
        bot.receive_message(
            user_1,
            "Что нужно сделать?"
        )
    )


    print(
        "\nUSER 2002"
    )


    print(
        bot.start(
            user_2
        )
    )


    print(
        bot.receive_message(
            user_2,
            "Что нужно сделать?"
        )
    )
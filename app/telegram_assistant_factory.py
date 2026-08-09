from telegram_core_factory import (
    create_telegram_core
)


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



def create_telegram_assistant():


    system = (
        create_telegram_core()
    )


    assistant = (
        system["core"]
    )


    profiles = (
        system["profiles"]
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
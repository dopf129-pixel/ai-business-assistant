from telegram_core_factory import (
    create_telegram_core
)


from services.assistant_keyboard_service import (
    AssistantKeyboardService
)


from services.assistant_button_handler_service import (
    AssistantButtonHandlerService
)


from services.assistant_telegram_memory_service import (
    AssistantTelegramMemoryService
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


    telegram_memory = (
        AssistantTelegramMemoryService(
            profiles
        )
    )


    keyboard = (
        AssistantKeyboardService()
    )


    button_handler = (
        AssistantButtonHandlerService(
            assistant,
            telegram_memory
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


    runner = (
        TelegramRunner(
            bot_service
        )
    )


    runner.memory_service = (
        telegram_memory
    )


    runner.profiles = (
        profiles
    )


    return runner
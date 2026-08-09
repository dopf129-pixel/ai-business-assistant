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


from services.assistant_memory_command_service import (
    AssistantMemoryCommandService
)


from telegram_app_layer.assistant_telegram_adapter import (
    AssistantTelegramAdapter
)


from telegram_app_layer.telegram_command_service import (
    TelegramCommandService
)


from telegram_app_layer.telegram_bot_service import (
    TelegramBotService
)


from telegram_app_layer.telegram_runner import (
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


    memory_commands = (
        AssistantMemoryCommandService(
            telegram_memory
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
            profiles,
            memory_commands
        )
    )


    command_service = (
        TelegramCommandService(
            adapter
        )
    )


    bot_service = (
        TelegramBotService(
            adapter,
            command_service
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


    runner.memory_commands = (
        memory_commands
    )


    runner.profiles = (
        profiles
    )


    return runner
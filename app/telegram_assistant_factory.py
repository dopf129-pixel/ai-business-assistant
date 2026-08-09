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


from services.assistant_user_storage_service import (
    AssistantUserStorageService
)


from services.assistant_history_service import (
    AssistantHistoryService
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


    storage_service = (
        AssistantUserStorageService()
    )


    telegram_memory = (
        AssistantTelegramMemoryService(
            storage_service
        )
    )


    memory_commands = (
        AssistantMemoryCommandService(
            telegram_memory
        )
    )


    history_service = (
        AssistantHistoryService(
            storage_service
        )
    )


    keyboard = (
        AssistantKeyboardService()
    )


    button_handler = (
        AssistantButtonHandlerService(
            assistant,
            telegram_memory,
            history_service
        )
    )


    adapter = (
        AssistantTelegramAdapter(
            assistant,
            keyboard,
            button_handler,
            storage_service,
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


    runner.history_service = (
        history_service
    )


    runner.storage_service = (
        storage_service
    )


    runner.profiles = (
        storage_service
    )


    return runner
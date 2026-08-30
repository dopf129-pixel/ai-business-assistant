from telegram_core_factory import (
    create_telegram_core
)

from current_unit_economics_factory import (
    create_current_unit_economics_query
)

from product_business_decision_factory import (
    create_product_business_decision_query,
    create_product_decision_history
)


from product_returns_finance_impact_factory import (
    create_product_returns_finance_impact_query
)


from services.assistant_keyboard_service import (
    AssistantKeyboardService
)


from services.assistant_button_handler_service import (
    AssistantButtonHandlerService
)


from product_decision_learning_health import (
    build_product_decision_learning_health
)


from services.assistant_telegram_memory_service import (
    AssistantTelegramMemoryService
)


from services.assistant_memory_command_service import (
    AssistantMemoryCommandService
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
        system["storage"]
    )


    context_service = (
        system["context"]
    )


    task_context_service = (
        system["task_context"]
    )


    unit_economics_query = (
        create_current_unit_economics_query(
            core_components=system
        )
    )


    product_business_decision_query = (
        create_product_business_decision_query(
            core_components=system,
            unit_economics_query=(
                unit_economics_query
            ),
            decision_history_service=(
                create_product_decision_history()
            )
        )
    )



    returns_finance_impact_query = (
        create_product_returns_finance_impact_query(
            core_components=system
        )
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
            history_service,
            task_context_service,
            keyboard_service=keyboard,
            unit_economics_query=(
                unit_economics_query
            ),
            product_business_decision_query=(
                product_business_decision_query
            ),
            returns_finance_impact_query=(
                returns_finance_impact_query
            ),
            product_decision_learning_health_builder=(
                build_product_decision_learning_health
            )
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


    runner.context_service = (
        context_service
    )


    runner.task_context_service = (
        task_context_service
    )


    runner.button_handler = (
        button_handler
    )


    runner.unit_economics_query = (
        unit_economics_query
    )


    runner.product_business_decision_query = (
        product_business_decision_query
    )


    runner.returns_finance_impact_query = (
        returns_finance_impact_query
    )


    runner.profiles = (
        storage_service
    )


    return runner

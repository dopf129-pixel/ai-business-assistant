import sys

sys.path.insert(
    0,
    "app"
)


from services.assistant_action_generator_service import (
    AssistantActionGeneratorService
)


from services.assistant_memory_service import (
    AssistantMemoryService
)



def test_action_generator_uses_memory():


    memory = (
        AssistantMemoryService()
    )


    memory.remember(

        {

            "action":
                "Получить данные",

            "status":
                "DONE",

            "solution":
                "Использовать резервный источник"

        }

    )


    generator = (
        AssistantActionGeneratorService(
            memory_service=memory
        )
    )


    result = (
        generator.generate(
            "Получить данные"
        )
    )


    assert (
        result["error"]
        ==
        False
    )


    assert (
        "memory"
        in result
    )
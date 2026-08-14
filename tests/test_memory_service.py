import sys

sys.path.insert(
    0,
    "app"
)


from services.assistant_memory_service import (
    AssistantMemoryService
)



def test_memory_service_stores_experience():


    service = (
        AssistantMemoryService()
    )


    result = (
        service.remember(
            {

                "action":
                    "Создать отчет",

                "status":
                    "DONE"

            }
        )
    )


    assert (
        result["error"]
        ==
        False
    )


    assert (
        len(
            service.memory
        )
        ==
        1
    )
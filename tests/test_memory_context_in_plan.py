import sys

sys.path.insert(
    0,
    "app"
)


from services.assistant_planning_service import (
    AssistantPlanningService
)


from services.assistant_memory_service import (
    AssistantMemoryService
)



def test_plan_contains_memory_context():


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


    planner = (
        AssistantPlanningService(
            memory_service=memory
        )
    )


    result = (
        planner.create_plan(
            "Получить данные"
        )
    )


    assert (
        result["error"]
        ==
        False
    )


    assert (
        len(
            result["memory"]
        )
        ==
        1
    )
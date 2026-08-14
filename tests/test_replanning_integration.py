import sys

sys.path.insert(
    0,
    "app"
)


from telegram_core_factory import create_telegram_core


USER_ID = 1000



def test_failed_execution_triggers_replanning():


    core = create_telegram_core()


    execution_service = (
        core["execution_service"]
    )


    task_service = (
        core["task_service"]
    )


    task_service.create_task(

        USER_ID,

        "Интеграция replanning",

        [

            {

                "title":
                    "Получить данные",

                "type":
                    "sales",

                "status":
                    "NEW"

            }

        ]

    )


    assert hasattr(
        execution_service,
        "replanning_service"
    )
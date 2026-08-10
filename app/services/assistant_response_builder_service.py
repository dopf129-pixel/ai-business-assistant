class AssistantResponseBuilderService:


    def build(
        self,
        result
    ):


        if (
            result.get(
                "message"
            )
        ):


            return {

                "error":
                    result.get(
                        "error",
                        False
                    ),

                "message":
                    result.get(
                        "message"
                    ),

                "task":
                    result.get(
                        "task"
                    ),

                "next_step":
                    result.get(
                        "next_step"
                    ),

                "action":
                    result.get(
                        "action"
                    ),

                "last_completed":
                    result.get(
                        "last_completed"
                    ),

                "result":
                    result.get(
                        "result"
                    )
            }



        count = (
            result.get(
                "count",
                0
            )
        )



        if count == 0:


            return {

                "error": False,

                "message":
                    "Проблем не найдено"
            }



        return {

            "error": False,

            "message":
                f"Создано действий: {count}",

            "actions":
                result.get(
                    "actions",
                    []
                )
        }
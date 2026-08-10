class AssistantResponseBuilderService:


    def build(
        self,
        result
    ):


        if (
            result.get("message")
            ==
            "Продолжаем работу"
        ):


            return {
                "error": False,

                "message":
                    "Продолжаем работу",

                "task":
                    result.get(
                        "task",
                        ""
                    ),

                "next_step":
                    result.get(
                        "next_step",
                        ""
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
class AssistantResponseBuilderService:


    def build(
        self,
        result
    ):


        if (
            result.get(
                "message"
            )
            ==
            "Действие выполнено"
        ):


            return {

                "error": False,

                "message":
                    "Действие выполнено",

                "action":
                    result.get(
                        "action"
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
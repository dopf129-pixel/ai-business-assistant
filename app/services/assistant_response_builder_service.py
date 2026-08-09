class AssistantResponseBuilderService:


    def build(
        self,
        result
    ):

        count = (
            result.get(
                "count",
                0
            )
        )


        if count == 0:

            return {
                "error": False,
                "message": (
                    "Проблем не найдено"
                )
            }


        return {
            "error": False,
            "message": (
                f"Создано действий: {count}"
            ),
            "actions": (
                result.get(
                    "actions",
                    []
                )
            )
        }
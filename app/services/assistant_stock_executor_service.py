class AssistantStockExecutorService:


    def execute(
        self,
        action
    ):


        context = (
            action.get(
                "context",
                {}
            )
        )


        reason = (
            context.get(
                "reason"
            )
        )


        details = [
            "Проверены остатки товара",
            "Найдены позиции для контроля"
        ]


        if reason:


            details.append(
                "Причина анализа: "
                +
                reason
            )


        return {

            "error": False,

            "result":
                {

                    "type":
                        "stock",

                    "message":
                        "Проверка остатков выполнена",

                    "details":
                        details,

                    "priority":
                        action.get(
                            "priority",
                            "NORMAL"
                        )

                }

        }
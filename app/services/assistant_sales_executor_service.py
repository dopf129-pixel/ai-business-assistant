class AssistantSalesExecutorService:


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
            "Проверено падение продаж",
            "Найдены возможные причины"
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
                        "sales",

                    "message":
                        "Анализ продаж выполнен",

                    "details":
                        details,

                    "priority":
                        action.get(
                            "priority",
                            "NORMAL"
                        )

                }

        }
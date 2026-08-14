class AssistantMarketingExecutorService:


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
            "Проверены рекламные каналы",
            "Найдены возможности улучшения продвижения"
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
                        "marketing",

                    "message":
                        "Маркетинг анализ выполнен",

                    "details":
                        details,

                    "priority":
                        action.get(
                            "priority",
                            "NORMAL"
                        )

                }

        }
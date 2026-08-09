class TelegramPlanFormatter:


    def format(
        self,
        result
    ):


        if not result:

            return "Нет данных"



        actions = (
            result.get("actions")
        )


        if not actions:

            return (
                "📋 План действий пуст"
            )



        text = (
            "📋 План действий:\n\n"
        )


        for index, action in enumerate(
            actions,
            1
        ):


            text += (
                f"{index}️⃣ "
                f"{action['title']}\n"
            )


            status = (
                action.get(
                    "status",
                    "NEW"
                )
            )


            priority = (
                action.get(
                    "priority",
                    "NORMAL"
                )
            )


            text += (
                f"   Статус: {status}\n"
            )


            text += (
                f"   Приоритет: {priority}\n\n"
            )


        return text
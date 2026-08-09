class TelegramActionFormatter:


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

            return str(result)



        text = (
            "📊 Результат анализа:\n\n"
        )


        for index, action in enumerate(
            actions,
            1
        ):

            text += (
                f"{index}️⃣ "
                f"{action['title']}\n"
            )

            text += (
                f"   Приоритет: "
                f"{action.get('priority', 'N/A')}\n"
            )

            text += "\n"


        return text
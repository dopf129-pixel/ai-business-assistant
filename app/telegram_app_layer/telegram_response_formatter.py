class TelegramResponseFormatter:


    def format(
        self,
        result
    ):


        if not result:

            return "Нет ответа"



        if result.get("memory") is not None:

            memory = (
                result.get("memory")
            )


            if not memory:

                return (
                    "🧠 Память пустая"
                )


            text = (
                "🧠 Твоя память:\n\n"
            )


            for key, value in memory.items():

                text += (
                    f"• {key}: {value}\n"
                )


            return text



        if result.get("message"):

            return (
                result["message"]
            )



        if result.get("actions"):

            text = (
                "📊 Результат анализа:\n\n"
            )


            for index, action in enumerate(
                result["actions"],
                1
            ):

                text += (
                    f"{index}. "
                    f"{action['title']}\n"
                )


            return text



        return str(result)
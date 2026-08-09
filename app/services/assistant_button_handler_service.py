class AssistantButtonHandlerService:


    def __init__(
        self,
        assistant,
        memory_service=None,
        history_service=None
    ):

        self.assistant = (
            assistant
        )

        self.memory_service = (
            memory_service
        )

        self.history_service = (
            history_service
        )



    def handle(
        self,
        button_id,
        user_id=None
    ):


        if button_id == "analyze":


            result = (
                self.assistant
                .ask(
                    "Что нужно сделать с продажами?",
                    user_id
                )
            )


            if (
                self.history_service
                and user_id
            ):

                self.history_service.add(
                    user_id,
                    "Выполнен анализ"
                )


            return result



        if button_id == "plan":


            result = (
                self.assistant
                .ask(
                    "Создай план действий",
                    user_id
                )
            )


            if (
                self.history_service
                and user_id
            ):

                self.history_service.add(
                    user_id,
                    "Создан план действий"
                )


            return result



        if button_id == "history":


            if (
                self.history_service
                and user_id
            ):

                return (
                    self.history_service
                    .get(
                        user_id
                    )
                )


            return {
                "error": False,
                "history": []
            }



        if button_id == "memory":


            if (
                self.memory_service
                and user_id
            ):

                return (
                    self.memory_service
                    .get_memory(
                        user_id
                    )
                )


            return {
                "error": False,
                "memory": {}
            }



        return {
            "error": True,
            "message": "Кнопка неизвестна"
        }
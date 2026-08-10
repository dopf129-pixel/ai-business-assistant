class AssistantButtonHandlerService:


    def __init__(
        self,
        assistant,
        memory_service=None,
        history_service=None,
        task_context_service=None
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

        self.task_context_service = (
            task_context_service
        )



    def prepare_context(
        self,
        user_id,
        action,
        task
    ):


        if (
            self.task_context_service
            and user_id
        ):

            self.task_context_service.user_context_service.update(
                user_id,
                "last_action",
                action
            )


            self.task_context_service.update_task(
                user_id,
                task
            )



    def handle(
        self,
        button_id,
        user_id=None
    ):



        if button_id == "analyze":


            self.prepare_context(
                user_id,
                "analyze",
                "Анализ продаж"
            )


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


            self.prepare_context(
                user_id,
                "plan",
                "Создание плана действий"
            )


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
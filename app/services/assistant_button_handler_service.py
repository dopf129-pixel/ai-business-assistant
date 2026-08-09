class AssistantButtonHandlerService:


    def __init__(
        self,
        assistant,
        memory_service=None
    ):

        self.assistant = (
            assistant
        )

        self.memory_service = (
            memory_service
        )



    def handle(
        self,
        button_id,
        user_id=None
    ):


        if button_id == "analyze":

            return (
                self.assistant
                .ask(
                    "Что нужно сделать с продажами?",
                    user_id
                )
            )



        if button_id == "plan":

            return (
                self.assistant
                .ask(
                    "Создай план действий",
                    user_id
                )
            )



        if button_id == "history":

            return {
                "error": False,
                "command": "history"
            }



        if button_id == "memory":


            if self.memory_service:

                return (
                    self.memory_service
                    .get_memory(
                        user_id
                    )
                )


            return {
                "error": False,
                "command": "memory"
            }



        return {
            "error": True,
            "message": "Кнопка неизвестна"
        }
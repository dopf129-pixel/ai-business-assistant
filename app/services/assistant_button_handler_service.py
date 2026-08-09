class AssistantButtonHandlerService:


    def __init__(
        self,
        assistant
    ):

        self.assistant = (
            assistant
        )



    def handle(
        self,
        button_id
    ):


        if button_id == "analyze":

            return (
                self.assistant
                .ask(
                    "Что нужно сделать с продажами?"
                )
            )


        if button_id == "plan":

            return (
                self.assistant
                .ask(
                    "Создай план действий"
                )
            )


        if button_id == "history":

            return {
                "error": False,
                "command": "history"
            }


        if button_id == "memory":

            return {
                "error": False,
                "command": "memory"
            }


        return {
            "error": True,
            "message": "Кнопка неизвестна"
        }
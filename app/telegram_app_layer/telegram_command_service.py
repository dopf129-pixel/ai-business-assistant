class TelegramCommandService:


    def __init__(
        self,
        assistant_adapter
    ):

        self.assistant_adapter = (
            assistant_adapter
        )



    def handle(
        self,
        user_id,
        text
    ):


        command = (
            text.strip()
            .lower()
        )


        if command == "/start":

            return (
                self.assistant_adapter
                .get_start_response(
                    user_id
                )
            )



        if command == "/help":

            return {
                "error": False,

                "message": (
                    "Доступные команды:\n"
                    "/start - запуск\n"
                    "/memory - память"
                )
            }



        if command == "/memory":

            return (
                self.assistant_adapter
                .handle_button(
                    "memory",
                    user_id
                )
            )



        return None
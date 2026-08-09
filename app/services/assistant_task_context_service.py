class AssistantTaskContextService:


    def __init__(
        self,
        user_context_service
    ):

        self.user_context_service = (
            user_context_service
        )



    def is_continue_command(
        self,
        text
    ):

        text = (
            text.lower()
            .strip()
        )


        return (
            "продолж" in text
            or
            "дальше" in text
            or
            "далее" in text
        )



    def update_task(
        self,
        user_id,
        text
    ):


        if self.is_continue_command(
            text
        ):

            return {
                "error": False,
                "updated": False
            }



        return (
            self.user_context_service
            .update(
                user_id,
                "current_task",
                text
            )
        )
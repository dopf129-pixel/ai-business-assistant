class AssistantRequestContextService:


    def __init__(
        self,
        user_context_service
    ):

        self.user_context_service = (
            user_context_service
        )



    def build(
        self,
        user_id,
        text
    ):

        context = (
            self.user_context_service
            .get_context(
                user_id
            )
        )


        return {
            "user_id": user_id,

            "text": text,

            "memory": (
                context["memory"]
            )
        }
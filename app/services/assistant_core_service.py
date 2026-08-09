class AssistantCoreService:


    def __init__(
        self,
        orchestrator_service,
        memory_service=None,
        request_context_service=None
    ):

        self.orchestrator_service = (
            orchestrator_service
        )

        self.memory_service = (
            memory_service
        )

        self.request_context_service = (
            request_context_service
        )



    def ask(
        self,
        text,
        user_id=None
    ):


        context = None


        if (
            self.request_context_service
            and user_id is not None
        ):

            context = (
                self.request_context_service
                .build(
                    user_id,
                    text
                )
            )


        result = (
            self.orchestrator_service
            .process(
                text
            )
        )


        if context:

            result["context"] = context


        elif self.memory_service:

            result["memory"] = (
                self.memory_service
                .all()
            )


        return result
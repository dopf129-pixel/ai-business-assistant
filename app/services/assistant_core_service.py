class AssistantCoreService:


    def __init__(
        self,
        orchestrator_service,
        memory_service=None,
        request_context_service=None,
        user_context_service=None,
        task_context_service=None
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

        self.user_context_service = (
            user_context_service
        )

        self.task_context_service = (
            task_context_service
        )



    def ask(
        self,
        text,
        user_id=None
    ):


        context = None



        if (
            self.user_context_service
            and user_id is not None
        ):

            context = (
                self.user_context_service
                .get_context(
                    user_id
                )
            )



        elif (
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
                text,
                context,
                user_id
            )
        )



        if (
            self.user_context_service
            and user_id is not None
        ):

            self.user_context_service.update(
                user_id,
                "last_message",
                text
            )


            context = (
                self.user_context_service
                .get_context(
                    user_id
                )
            )



        if context:

            result["context"] = context



        return result
class AssistantCoreService:


    def __init__(
        self,
        orchestrator_service,
        memory_service=None
    ):

        self.orchestrator_service = (
            orchestrator_service
        )

        self.memory_service = (
            memory_service
        )



    def ask(
        self,
        text
    ):

        result = (
            self.orchestrator_service
            .process(
                text
            )
        )


        if self.memory_service:

            result["memory"] = (
                self.memory_service
                .all()
            )


        return result
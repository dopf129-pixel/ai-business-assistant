class AssistantCoreService:


    def __init__(
        self,
        orchestrator_service
    ):

        self.orchestrator_service = (
            orchestrator_service
        )


    def ask(
        self,
        text
    ):

        return (
            self.orchestrator_service
            .process(
                text
            )
        )
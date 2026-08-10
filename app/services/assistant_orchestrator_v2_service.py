class AssistantOrchestratorV2Service:


    def __init__(
        self,
        entry_service
    ):

        self.entry_service = (
            entry_service
        )



    def process(
        self,
        text,
        context=None,
        user_id=None
    ):


        return (
            self.entry_service
            .handle(
                text,
                context,
                user_id
            )
        )
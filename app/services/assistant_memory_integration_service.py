class AssistantMemoryIntegrationService:


    def __init__(
        self,
        memory_service,
        intent_service
    ):

        self.memory_service = (
            memory_service
        )

        self.intent_service = (
            intent_service
        )


    def process(
        self,
        text
    ):

        intent = (
            self.intent_service
            .detect(
                text
            )
        )


        if intent.get(
            "error"
        ):

            return intent


        self.memory_service.save(
            "last_command",
            intent["command"]
        )


        self.memory_service.save(
            "last_text",
            text
        )


        return {
            "error": False,
            "intent": intent,
            "memory_saved": True
        }
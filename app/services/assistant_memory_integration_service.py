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

        command_save = (
            self.memory_service
            .save(
                "last_command",
                intent["command"]
            )
        )

        command_failure = (
            self._save_failure(
                command_save
            )
        )

        if command_failure:
            command_failure[
                "memory_saved"
            ] = False
            return command_failure

        text_save = (
            self.memory_service
            .save(
                "last_text",
                text
            )
        )

        text_failure = (
            self._save_failure(
                text_save
            )
        )

        if text_failure:
            text_failure[
                "memory_saved"
            ] = False
            text_failure[
                "partial_memory_saved"
            ] = True
            return text_failure

        return {
            "error": False,
            "intent": intent,
            "memory_saved": True
        }


    @staticmethod
    def _save_failure(
        result
    ):

        if (
            not isinstance(
                result,
                dict
            )
            or type(
                result.get(
                    "error"
                )
            )
            is not bool
        ):
            return {
                "error": True,
                "message":
                    "INVALID_MEMORY_SAVE_RESULT"
            }

        if result.get(
            "error"
        ) is True:
            return dict(
                result
            )

        return None

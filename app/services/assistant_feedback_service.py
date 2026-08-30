class AssistantFeedbackService:

    def __init__(
        self,
        memory_service=None
    ):

        self.experiences = []
        self.memory_service = (
            memory_service
        )


    def record(
        self,
        result
    ):

        experience = {
            "action": result.get(
                "action"
            ),
            "status": result.get(
                "status"
            ),
            "experience": self._analyze(
                result
            )
        }

        self.experiences.append(
            experience
        )

        if self.memory_service:

            try:
                memory_result = (
                    self.memory_service
                    .remember(
                        experience
                    )
                )
            except Exception:
                return {
                    "error": True,
                    "message":
                        "FEEDBACK_MEMORY_SAVE_FAILED",
                    "experience": experience,
                    "count": len(
                        self.experiences
                    ),
                    "feedback_recorded": True,
                    "memory_saved": False,
                    "persistence_state_unknown":
                        True
                }

            if (
                not isinstance(
                    memory_result,
                    dict
                )
                or type(
                    memory_result.get(
                        "error"
                    )
                )
                is not bool
            ):
                return {
                    "error": True,
                    "message":
                        "INVALID_FEEDBACK_MEMORY_RESULT",
                    "experience": experience,
                    "count": len(
                        self.experiences
                    ),
                    "feedback_recorded": True,
                    "memory_saved": False
                }

            if memory_result.get(
                "error"
            ) is True:
                failure = dict(
                    memory_result
                )
                failure[
                    "experience"
                ] = experience
                failure[
                    "count"
                ] = len(
                    self.experiences
                )
                failure[
                    "feedback_recorded"
                ] = True
                failure[
                    "memory_saved"
                ] = False
                return failure

        return {
            "error": False,
            "experience": experience,
            "count": len(
                self.experiences
            )
        }


    def _analyze(
        self,
        result
    ):

        status = result.get(
            "status"
        )

        if status == "DONE":
            return "successful execution"

        if status == "FAILED":
            return "failed execution"

        return "unknown result"

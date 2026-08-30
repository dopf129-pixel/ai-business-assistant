class AssistantMemoryService:

    def __init__(
        self,
        storage_service=None
    ):

        self.storage_service = (
            storage_service
        )

        if self.storage_service:
            self.context = (
                self.storage_service
                .load()
            )
        else:
            self.context = {}

        self.memory = (
            self.context.get(
                "memory",
                []
            )
        )


    def remember(
        self,
        experience
    ):

        item = {
            "action": experience.get(
                "action"
            ),
            "status": experience.get(
                "status"
            ),
            "experience": experience
        }

        memory_key_existed = (
            "memory" in self.context
        )
        previous_memory_value = (
            self.context.get(
                "memory"
            )
        )

        self.memory.append(
            item
        )
        self.context["memory"] = (
            self.memory
        )

        persistence = (
            self._persist_context()
        )

        if persistence.get(
            "error"
        ):

            if persistence.get(
                "_precommit_failure"
            ):
                self.memory.pop()

                if memory_key_existed:
                    self.context["memory"] = (
                        previous_memory_value
                    )
                else:
                    self.context.pop(
                        "memory",
                        None
                    )

            return self._persistence_failure(
                persistence
            )

        return {
            "error": False,
            "memory": item,
            "count": len(
                self.memory
            )
        }


    def recall(
        self,
        action=None
    ):

        if action is None:
            return self.memory

        results = []

        for item in self.memory:
            if item.get(
                "action"
            ) == action:
                results.append(
                    item
                )

        return results


    def save(
        self,
        key,
        value
    ):

        existed = key in self.context
        previous = (
            self.context.get(
                key
            )
        )

        self.context[key] = value

        persistence = (
            self._persist_context()
        )

        if persistence.get(
            "error"
        ):

            if persistence.get(
                "_precommit_failure"
            ):
                if existed:
                    self.context[key] = (
                        previous
                    )
                else:
                    self.context.pop(
                        key,
                        None
                    )

            return self._persistence_failure(
                persistence
            )

        return {
            "error": False,
            "saved": True
        }


    def get(
        self,
        key
    ):

        if key not in self.context:
            return {
                "error": True,
                "message": "Контекст не найден"
            }

        return {
            "error": False,
            "value": self.context[key]
        }


    def clear(
        self
    ):

        previous_context = self.context
        previous_memory = self.memory

        self.context = {}
        self.memory = []

        persistence = (
            self._persist_context()
        )

        if persistence.get(
            "error"
        ):

            if persistence.get(
                "_precommit_failure"
            ):
                self.context = (
                    previous_context
                )
                self.memory = (
                    previous_memory
                )

            return self._persistence_failure(
                persistence
            )

        return {
            "error": False,
            "cleared": True
        }


    def _persist_context(
        self
    ):

        if not self.storage_service:
            return {
                "error": False,
                "persisted": False
            }

        try:
            result = (
                self.storage_service
                .save(
                    self.context
                )
            )
        except Exception:
            return {
                "error": True,
                "message":
                    "MEMORY_STORAGE_SAVE_FAILED",
                "persistence_state_unknown":
                    True
            }

        if result is True:
            return {
                "error": False,
                "persisted": True
            }

        if result is False:
            return {
                "error": True,
                "message":
                    "MEMORY_STORAGE_SAVE_REJECTED",
                "_precommit_failure":
                    True
            }

        return {
            "error": True,
            "message":
                "INVALID_MEMORY_STORAGE_SAVE_RESULT",
            "persistence_state_unknown":
                True
        }


    @staticmethod
    def _persistence_failure(
        persistence
    ):

        result = {
            "error": True,
            "message": persistence.get(
                "message",
                "MEMORY_STORAGE_SAVE_FAILED"
            )
        }

        if persistence.get(
            "_precommit_failure"
        ):
            result["rolled_back"] = True

        if persistence.get(
            "persistence_state_unknown"
        ):
            result[
                "persistence_state_unknown"
            ] = True

        return result

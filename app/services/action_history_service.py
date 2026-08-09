class ActionHistoryService:

    def __init__(
        self,
        storage_service=None
    ):

        self.storage_service = (
            storage_service
        )


        if self.storage_service:

            self.actions = (
                self.storage_service
                .load()
            )

        else:

            self.actions = []


    def save_action(
        self,
        action
    ):

        self.actions.append(
            action
        )


        if self.storage_service:

            self.storage_service.save(
                self.actions
            )


        return {
            "error": False,
            "saved": True,
            "count": len(
                self.actions
            )
        }


    def get_action(
        self,
        index
    ):

        if (
            index < 0
            or
            index >= len(
                self.actions
            )
        ):

            return {
                "error": True,
                "message": "Действие не найдено"
            }


        return {
            "error": False,
            "action": (
                self.actions[index]
            )
        }


    def list_actions(
        self
    ):

        return {
            "error": False,
            "actions": (
                self.actions
            ),
            "count": len(
                self.actions
            )
        }
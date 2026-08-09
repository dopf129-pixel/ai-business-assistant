class ActionHistoryService:

    def __init__(
        self
    ):

        self.actions = []


    def save_action(
        self,
        action
    ):

        self.actions.append(
            action
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
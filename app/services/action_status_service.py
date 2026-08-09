class ActionStatusService:

    def update_status(
        self,
        action,
        status
    ):

        allowed_statuses = [
            "NEW",
            "IN_PROGRESS",
            "DONE"
        ]


        if status not in allowed_statuses:

            return {
                "error": True,
                "message": "Недопустимый статус"
            }


        action["status"] = status


        return {
            "error": False,
            "action": action
        }


    def complete(
        self,
        action
    ):

        return self.update_status(
            action,
            "DONE"
        )
class ActionWorkflowService:

    def __init__(
        self,
        history_service,
        status_service
    ):

        self.history_service = (
            history_service
        )

        self.status_service = (
            status_service
        )


    def update_status(
        self,
        index,
        status
    ):

        result = (
            self.history_service
            .get_action(
                index
            )
        )


        if result.get(
            "error"
        ):

            return result


        action = (
            result["action"]
        )


        updated = (
            self.status_service
            .update_status(
                action,
                status
            )
        )


        if updated.get(
            "error"
        ):

            return updated


        return (
            self.history_service
            .update_action(
                index,
                updated["action"]
            )
        )


    def complete(
        self,
        index
    ):

        return self.update_status(
            index,
            "DONE"
        )
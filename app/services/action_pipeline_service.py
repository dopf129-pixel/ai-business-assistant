class ActionPipelineService:

    def __init__(
        self,
        action_service,
        history_service
    ):

        self.action_service = (
            action_service
        )

        self.history_service = (
            history_service
        )


    def build_and_save(
        self,
        recommendations
    ):

        result = (
            self.action_service
            .build(
                recommendations
            )
        )


        if result.get(
            "error"
        ):

            return result


        actions = (
            result.get(
                "actions",
                []
            )
        )


        for action in actions:

            self.history_service.save_action(
                action
            )


        return {
            "error": False,
            "actions": actions
        }
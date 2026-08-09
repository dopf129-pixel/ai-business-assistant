class AssistantActionExecutionService:


    def __init__(
        self,
        history_service
    ):

        self.history_service = (
            history_service
        )



    def execute(
        self,
        actions
    ):

        saved = []


        for action in actions:

            result = (
                self.history_service
                .save_action(
                    action
                )
            )


            if not result["error"]:

                saved.append(
                    action
                )


        return {
            "error": False,
            "executed": saved,
            "count": len(
                saved
            )
        }